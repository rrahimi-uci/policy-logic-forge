#!/usr/bin/env python3
"""Agent 12: build the Business Information Model from the certified graph.

The pipeline's earlier stages produce rules whose variables are already typed,
united, bounded, and cited.  This stage turns that into the canonical UML
picture of the *business data* those rules operate on -- the bridge from policy
knowledge to schemas, APIs, and executable code.

The division of labour is deliberate and matches the rest of the pipeline:

* **Deterministic** (``utils/information_model.py``) -- business types,
  enumerations, multiplicity, optionality, constraints, and source references.
  All of it derives from what the rule contract declares, so none of it is a
  model's opinion.  On a real 614-rule mortgage graph this types 2,546
  attributes and leaves only 24 as a generic ``String``.
* **Judgment** (this module, via one prompt) -- what each attribute actually
  describes, whether a group of attributes is really a value object, and which
  concepts deserve to be classes.  That cannot be read off a contract.

The model may never invent, retype, or rename anything.  Its proposals are
checked against the deterministic facts before being applied, and an assignment
naming an unknown symbol or an unknown class is discarded rather than trusted.
An attribute the model cannot place stays unassigned and is reported, because a
misfiled attribute silently corrupts the model while an unplaced one is merely
reviewed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.config import get_config
from utils.information_model import Klass, build_model, pascal_case, validate_model
from utils.linkml_schema import (
    catalog_rows,
    dump_yaml,
    to_json_schema,
    to_linkml,
    to_mermaid,
    to_plantuml,
    validate_schema,
)
from utils.llm_client import create_llm_client
from utils.prompt_manager import get_prompt_manager

OUTPUT_DIR_NAME = "agent_12-business-information-model"
#: The canonical artifact. Every other file in the directory is generated from
#: it, so none of them can drift from the model or from each other.
SCHEMA_FILE = "business_information_model.yaml"
JSON_SCHEMA_FILE = "business_information_model.schema.json"
MERMAID_FILE = "business_information_model.mmd"
PLANTUML_FILE = "business_information_model.puml"
CATALOG_FILE = "class_attribute_catalog.json"
CATALOG_MARKDOWN = "class_attribute_catalog.md"
VALIDATION_FILE = "information_model_validation.json"

_CONFIDENCE = {"clear", "probable", "unclear"}


class InformationModelSynthesiser:
    """Asks the model where attributes belong, and refuses anything else."""

    def __init__(self, api_key: str, model: str, reasoning_effort: str) -> None:
        concurrency = max(1, int(os.getenv("KG_INFORMATION_MODEL_LLM_CONCURRENCY", "8")))
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.client = create_llm_client(api_key=api_key, model=model, concurrency=concurrency)
        self.prompts = get_prompt_manager()

    @staticmethod
    def _parse(content: str) -> dict[str, Any]:
        content = (content or "").strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            value = json.loads(content)
        except json.JSONDecodeError as original:
            try:
                from json_repair import repair_json

                value = repair_json(content, return_objects=True, strict=True)
            except Exception:
                raise original
        if not isinstance(value, dict):
            raise ValueError("agent_12 response must be a JSON object")
        return value

    def assign(self, batch: Sequence[Mapping[str, Any]], classes: Sequence[str]) -> list[dict[str, Any]]:
        prompt = self.prompts.format_prompt(
            "information_model_synthesis",
            existing_classes="\n".join(f"- {name}" for name in classes) or "- (none yet)",
            attributes_json="\n".join(
                f"- {item['symbol']} | {item['type']} | {item['multiplicity']} | "
                f"rules: {', '.join(item['source_rule_ids'][:3]) or 'n/a'}"
                for item in batch
            ),
        )
        attempts = max(1, int(os.getenv("KG_INFORMATION_MODEL_PARSE_ATTEMPTS", "3")))
        error: Exception | None = None
        for attempt in range(1, attempts + 1):
            response = self.client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=max(4000, int(os.getenv("KG_INFORMATION_MODEL_MAX_TOKENS", "12000"))),
                response_format={"type": "json_object"},
                reasoning_effort=self.reasoning_effort,
            )
            try:
                payload = self._parse(response.choices[0].message.content or "")
                items = payload.get("assignments")
                if not isinstance(items, list):
                    raise ValueError("response lacks an 'assignments' list")
                return [dict(item) for item in items if isinstance(item, Mapping)]
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                error = exc
                prompt += "\n\nReturn a complete valid JSON object only, with every symbol exactly once."
                print(f"⚠️ agent_12 JSON retry {attempt}/{attempts}: {exc}", flush=True)
        assert error is not None
        raise error


def _apply_assignments(
    model,
    assignments: Sequence[Mapping[str, Any]],
    *,
    concept_of: Mapping[str, str],
) -> dict[str, Any]:
    """Apply accepted proposals; discard anything that does not check out.

    Every proposal is validated against the deterministic model before it is
    allowed to change anything: the symbol must be one that was actually left
    unassigned, and the destination must already exist or be a genuinely new
    class the batch supports. Rejections are counted and reported rather than
    silently dropped, so the stage can say how much of the model rests on
    judgment that did not survive checking.
    """
    by_symbol = {attribute.symbol: attribute for attribute in model.unassigned}
    by_class = {klass.name: klass for klass in model.classes}
    proposed_new: dict[str, list[Any]] = {}
    proposed_value_objects: dict[str, list[Any]] = {}
    stats = {"accepted": 0, "unclear": 0, "rejected_unknown_symbol": 0,
             "rejected_unknown_class": 0, "rejected_bad_shape": 0,
             "rejected_flag_class": 0, "value_objects": 0}
    placed: set[str] = set()

    for item in assignments:
        symbol = str(item.get("symbol") or "").strip().lower()
        attribute = by_symbol.get(symbol)
        if attribute is None or symbol in placed:
            stats["rejected_unknown_symbol"] += 1
            continue
        confidence = str(item.get("confidence") or "").strip().lower()
        if confidence not in _CONFIDENCE:
            stats["rejected_bad_shape"] += 1
            continue
        if confidence == "unclear":
            attribute.needs_review = True
            attribute.review_reasons = attribute.review_reasons + (
                str(item.get("reasoning") or "the model could not place this attribute"),
            )
            stats["unclear"] += 1
            continue

        owner = str(item.get("owner") or "").strip()
        new_class = str(item.get("new_class") or "").strip()
        value_object = str(item.get("value_object") or "").strip()

        if value_object:
            proposed_value_objects.setdefault(pascal_case(value_object), []).append(attribute)

        if owner and owner in by_class:
            by_class[owner].attributes.append(attribute)
            placed.add(symbol)
            stats["accepted"] += 1
        elif new_class:
            proposed_new.setdefault(pascal_case(new_class), []).append(attribute)
            placed.add(symbol)
        elif owner:
            stats["rejected_unknown_class"] += 1
        else:
            stats["unclear"] += 1

    # A proposed class only becomes real once enough attributes back it, and
    # once those attributes describe business state rather than rule outcomes.
    #
    # The prompt already forbids modelling a class out of compliance flags, and
    # on a real run the model did it anyway -- proposing a `Lender` whose eight
    # attributes were all booleans recording whether a policy had been met.
    # Those are evaluation results, not what a lender *is*. A prompt cannot be
    # relied on for a rule that matters, so it is enforced here: a proposed
    # class needs at least two attributes that are not booleans, which any real
    # business entity has (an identifier, an amount, a date, a category).
    # Rejected attributes go back to unassigned with the reason, never silently.
    for name, members in proposed_new.items():
        substantive = [a for a in members if a.type != "Boolean"]
        if len(members) >= 3 and len(substantive) >= 2 and name not in by_class:
            model.classes.append(Klass(
                name=name,
                concept_id=concept_of.get(name.lower(), name),
                description="",
                stereotype="entity",
                attributes=sorted(members, key=lambda a: a.name),
                needs_review=True,
                review_reasons=("class proposed during modelling; confirm it is a real business entity",),
            ))
            stats["accepted"] += len(members)
        else:
            reason = (
                f"proposed class {name!r} carried only compliance flags, not business state"
                if len(members) >= 3 and len(substantive) < 2
                else f"proposed class {name!r} was not supported by enough attributes"
            )
            if len(members) >= 3 and len(substantive) < 2:
                stats["rejected_flag_class"] += 1
            for attribute in members:
                placed.discard(attribute.symbol)
                attribute.needs_review = True
                attribute.review_reasons = attribute.review_reasons + (reason,)

    # Materialise value objects: a composite with no identity of its own, whose
    # components are always handled together (a money-with-currency pair, an
    # address, a date range). Two components are the minimum -- a "value object"
    # wrapping one attribute is just that attribute with an extra hop.
    for name, members in proposed_value_objects.items():
        if len(members) < 2 or name in by_class:
            for attribute in members:
                attribute.needs_review = True
                attribute.review_reasons = attribute.review_reasons + (
                    f"proposed value object {name!r} had too few components to stand alone",
                )
            continue
        model.classes.append(Klass(
            name=name,
            concept_id=name,
            description="",
            stereotype="value_object",
            attributes=sorted(members, key=lambda a: a.name),
            needs_review=True,
            review_reasons=("value object proposed during modelling; confirm it has no identity of its own",),
        ))
        for attribute in members:
            placed.add(attribute.symbol)
        stats["value_objects"] += 1

    model.unassigned = [a for a in model.unassigned if a.symbol not in placed]
    for klass in model.classes:
        klass.attributes.sort(key=lambda a: a.name)
    model.classes.sort(key=lambda k: k.name)
    return stats


def _catalog_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    header = (
        "| Class | Attribute | Type | Unit | Multiplicity | Required | Constraints | Source rules |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )
    lines = []
    for row in rows:
        constraints = "; ".join(row["constraints"])[:80] or "—"
        if row["allowed_values"]:
            constraints = (constraints + "; " if constraints != "—" else "") + \
                f"one of {len(row['allowed_values'])} values"
        sources = (row["source_rules"] or "—").split(", ")
        lines.append(
            f"| {row['class']} | {row['attribute']} | {row['type']} | {row['unit'] or '—'} | "
            f"{row['multiplicity']} | {'yes' if row['required'] else 'no'} | {constraints} | "
            f"{', '.join(sources[:2])} |"
        )
    return (
        "# Class and attribute catalog\n\n"
        "Generated from `business_information_model.yaml`, which is the canonical model.\n\n"
        + header + "\n".join(lines) + "\n"
    )


def generate(
    graph_file: Path,
    models_dir: Path | None,
    output_dir: Path,
    *,
    use_model: bool = True,
) -> dict[str, Any]:
    """Build, refine, validate, and emit the business information model."""
    graph = json.loads(graph_file.read_text(encoding="utf-8"))
    if not isinstance(graph, Mapping):
        raise ValueError("optimized graph must be a JSON object")

    profile: Mapping[str, Any] = {}
    if models_dir:
        profile_path = Path(models_dir) / "semantic_vocabulary_profile.json"
        if profile_path.exists():
            loaded = json.loads(profile_path.read_text(encoding="utf-8"))
            profile = loaded if isinstance(loaded, Mapping) else {}

    model = build_model(graph, profile)
    print(
        f"▶ agent_12 deterministic model: {len(model.classes)} classes, "
        f"{sum(len(k.attributes) for k in model.classes)} attributes, "
        f"{len(model.enumerations)} enumerations, {len(model.unassigned)} unassigned",
        flush=True,
    )

    synthesis = {"accepted": 0, "unclear": 0, "batches": 0, "skipped": True}
    if use_model and model.unassigned:
        config = get_config()
        api_key = config.get_api_key()
        if api_key:
            synthesiser = InformationModelSynthesiser(
                api_key=api_key,
                model=config.get_reasoning_model(),
                reasoning_effort=config.get_reasoning_effort(),
            )
            batch_size = max(10, int(os.getenv("KG_INFORMATION_MODEL_ATTRS_PER_REQUEST", "60")))
            payload = [
                {"symbol": a.symbol, "type": a.type, "multiplicity": a.multiplicity,
                 "source_rule_ids": list(a.source_rule_ids)}
                for a in model.unassigned
            ]
            batches = [payload[i:i + batch_size] for i in range(0, len(payload), batch_size)]
            # A bounded run is genuinely useful beyond testing: it lets a smoke
            # check exercise the real modelling path without paying for the whole
            # corpus, and lets a large graph be modelled incrementally.
            cap = int(os.getenv("KG_INFORMATION_MODEL_MAX_BATCHES", "0") or 0)
            if cap > 0 and len(batches) > cap:
                print(f"   modelling capped at {cap} of {len(batches)} batches "
                      f"(KG_INFORMATION_MODEL_MAX_BATCHES)", flush=True)
                batches = batches[:cap]
            concept_of = {pascal_case(k).lower(): k for k in (graph.get("entity_types") or {})}
            assignments: list[dict[str, Any]] = []
            for index, batch in enumerate(batches, 1):
                names = [k.name for k in model.classes]
                try:
                    assignments.extend(synthesiser.assign(batch, names))
                except Exception as exc:  # a batch failure must not lose the model
                    print(f"⚠️ agent_12 batch {index}/{len(batches)} failed: {exc}", flush=True)
                print(f"   modelled batch {index}/{len(batches)}", flush=True)
            synthesis = _apply_assignments(model, assignments, concept_of=concept_of)
            synthesis["batches"] = len(batches)
            synthesis["skipped"] = False
        else:
            print("⚠️ agent_12: no API key; emitting the deterministic model only", flush=True)

    # LinkML is the canonical form; everything below is generated from it.
    schema = to_linkml(model, domain=os.getenv("KG_DOMAIN", "") or "")
    schema_problems = validate_schema(schema)
    if schema_problems:
        print(f"⚠️ agent_12: emitted schema did not validate: {schema_problems[0]}", flush=True)

    json_schema = to_json_schema(schema)

    report = validate_model(model, graph, profile)
    report["synthesis"] = synthesis
    report["schema_validation"] = {
        "valid": not schema_problems,
        "problems": schema_problems,
        "checked_with": "linkml-runtime SchemaView",
        "json_schema_generated_by": json_schema.get("x-generated-by", "unknown"),
    }
    if json_schema.get("x-fallback-reason"):
        print("⚠️ agent_12: LinkML's JSON Schema generator was unavailable "
              f"({json_schema['x-fallback-reason']}); used the direct translation",
              flush=True)
    # Everything the model could not settle lives with the validation report
    # rather than in a parallel model file, so there is exactly one canonical
    # description of the model itself.
    report["unassigned_attributes"] = [a.as_dict() for a in model.unassigned]
    report["type_conflicts"] = model.type_conflicts

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / SCHEMA_FILE).write_text(dump_yaml(schema), encoding="utf-8")
    (output_dir / JSON_SCHEMA_FILE).write_text(
        json.dumps(json_schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / MERMAID_FILE).write_text(to_mermaid(schema) + "\n", encoding="utf-8")
    (output_dir / PLANTUML_FILE).write_text(to_plantuml(schema) + "\n", encoding="utf-8")
    rows = catalog_rows(schema)
    (output_dir / CATALOG_FILE).write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / CATALOG_MARKDOWN).write_text(_catalog_markdown(rows), encoding="utf-8")
    (output_dir / VALIDATION_FILE).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = {
        "classes": len(schema["classes"]),
        "attributes": sum(len(k.get("attributes") or {}) for k in schema["classes"].values()),
        "enumerations": len(schema["enums"]),
        "relationships": len(model.relationships),
        "unassigned_attributes": len(model.unassigned),
        "validation": report["counts"],
        "schema_valid": not schema_problems,
        "output_dir": str(output_dir),
    }
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--models-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--batch-name")
    parser.add_argument("--domain")
    parser.add_argument("--no-model", action="store_true",
                        help="emit the deterministic model only, with no LLM modelling pass")
    args = parser.parse_args(argv)

    if args.batch_name:
        os.environ["KG_BATCH_NAME"] = args.batch_name
    if args.domain:
        os.environ["KG_DOMAIN"] = args.domain

    config = get_config()
    graph = args.graph or (config.get_optimized_dir() / "optimized_compliance_knowledge_graph.json")
    models = args.models_dir or config.get_executable_models_dir()
    getter = getattr(config, "get_information_model_dir", None)
    output = args.output_dir or (getter() if getter else config.get_pipeline_base_path() / OUTPUT_DIR_NAME)

    if not graph.exists():
        print(f"ERROR: required upstream artifact missing: {graph}", flush=True)
        return 2
    try:
        manifest = generate(graph, models, output, use_model=not args.no_model)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: business information model generation failed: {exc}", flush=True)
        return 2

    print(
        f"Generated business information model: {manifest['classes']} classes, "
        f"{manifest['attributes']} attributes, {manifest['enumerations']} enumerations, "
        f"{manifest['relationships']} relationships: {output}",
        flush=True,
    )
    severity = manifest["validation"]["by_severity"]
    print(
        f"Validation: {severity.get('error', 0)} error(s), {severity.get('review', 0)} for review; "
        f"{manifest['unassigned_attributes']} attribute(s) left unassigned",
        flush=True,
    )
    return 3 if severity.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
