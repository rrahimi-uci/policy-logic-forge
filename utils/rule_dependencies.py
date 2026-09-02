"""Deterministic, typed derivation of relationships between business rules.

Replaces a narrative dependency model in which an LLM proposed edges and a
single structural check screened them.  That arrangement had three measured
defects:

* **Recall.**  Proposal ran over batched rule summaries with a hard cap on
  cross-batch comparisons, so on a real 613-rule run roughly 96% of rule pairs
  were never examined at all.  Four edges were asserted where sixty were
  derivable from the same contracts.
* **Unenforced typing.**  Six ``dependency_type`` values were accepted
  (``prerequisite``/``conditional``/``sequential``/``complementary``/
  ``override``/``validation``) but never defined anywhere, and all six were
  validated by one check -- source outcome name intersects target predicate
  name.  That check is correct for ``conditional``, insufficient for
  ``prerequisite``, and irrelevant to the other four.  Nothing downstream ever
  branched on the value.
* **Staleness.**  The check ran once, in the optimizer.  Later stages rewrite
  variables in place, so an edge could keep ``structurally_supported: true``
  after the variable that justified it had been renamed.

The model here is that every relation kind carries a *decidable acceptance
condition*, and a kind the rule contract cannot express is refused rather than
emitted as an unenforced label -- the same posture ``utils/lexec_ir.py`` takes
toward constructs it cannot lower.

Relation kinds
--------------
``dataflow``     the target reads a symbol the source assigns.  Deterministic.
``gating``       dataflow, *and* the target provably cannot fire unless the
                 source's outcome holds.  Requires an entailment oracle; in its
                 absence a relation stays ``dataflow`` rather than being
                 promoted on faith.
``conflict``     both rules assign the same symbol.  Whether they can actually
                 co-fire is a solver question layered on top; this module emits
                 the candidate surface only.
``association``  the two rules share an input symbol or a source passage.
                 **Symmetric, and deliberately not a dependency** -- it asserts
                 co-sensitivity to a change, never that one rule feeds another,
                 and it must stay out of any topological ordering.

Everything here is pure: no I/O, no LLM, no solver import.  The solver-backed
promotion in :func:`classify_gating` is injected by the caller so this module
stays unit-testable without one.
"""
from __future__ import annotations

import re
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from utils.scope import scopes_may_overlap

__all__ = [
    "RELATION_KINDS",
    "UNREPRESENTABLE_KINDS",
    "Relation",
    "RelationRefusal",
    "normalise",
    "rule_writes",
    "rule_reads",
    "rule_passages",
    "build_fact_registry",
    "derive_dataflow",
    "derive_conflicts",
    "derive_associations",
    "classify_gating",
    "relation_holds",
    "revalidate",
    "refusal_for_declared_kind",
    "derive_relations",
    "revalidate_graph",
    "prune_dangling_related_rules",
]


#: Kinds this module will emit.  Each has an acceptance condition below.
RELATION_KINDS = ("dataflow", "gating", "conflict", "association")

#: Kinds the v2 rule contract provides no way to decide.  Emitting these as
#: labels is what the previous model did; refusing them is what this one does.
#: The refusal text is written for a reviewer reading a report, not a stack
#: trace -- it says what is missing, not merely that something failed.
UNREPRESENTABLE_KINDS: dict[str, tuple[str, str]] = {
    "sequential": (
        "NO_TEMPORAL_SEMANTICS",
        "the rule contract records no temporal ordering, so 'A happens before B' "
        "cannot be checked against anything",
    ),
    "override": (
        "NO_PRECEDENCE",
        "the rule contract has no rule-precedence field, so 'A defeats B' cannot "
        "be distinguished from an ordinary conflict",
    ),
    "complementary": (
        "NOT_A_DEPENDENCY",
        "co-usefulness is symmetric and directionless; it is emitted as an "
        "'association' relation and kept out of the dependency graph",
    ),
    "validation": (
        "NO_ACCEPTANCE_CONDITION",
        "no decidable condition was ever defined for this relation",
    ),
    "contradictory": (
        "BELONGS_TO_CONFLICT",
        "a contradiction between two rules is a conflict, not a directed dependency",
    ),
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: A passage cited by more rules than this is treated as a document-level
#: catch-all pointer rather than a real passage.  Associating every rule in
#: such a group with every other produces a blob, not a reviewable cluster.
DEFAULT_MAX_PASSAGE_FANOUT = 120


def normalise(value: Any) -> str:
    """The pipeline's canonical symbol identity: trimmed and lowercased.

    Kept identical to the normalisation the rule contract validator applies, so
    a symbol resolves the same way here as it does at validation time.
    """
    return str(value or "").strip().lower()


# ---------------------------------------------------------------------------
# symbol extraction
# ---------------------------------------------------------------------------

def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _declarations(rule: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Local variable name -> declaration."""
    out: dict[str, Mapping[str, Any]] = {}
    for variable in _mappings(rule.get("variables")):
        name = normalise(variable.get("name"))
        if name:
            out.setdefault(name, variable)
    return out


def _fact_id(declarations: Mapping[str, Mapping[str, Any]], local_name: Any) -> str:
    """Resolve a local variable onto a graph-wide fact identity.

    ``fact_id`` is the stable cross-rule contract.  Older graphs remain
    readable by falling back to their normalized local name, but new extractors
    can bind aliases without changing executable variable labels.
    """
    name = normalise(local_name)
    declaration = declarations.get(name, {})
    return normalise(declaration.get("fact_id")) or name


def _endpoint(
    declarations: Mapping[str, Mapping[str, Any]],
    local_name: Any,
    *,
    value: Any = None,
    value_type: Any = None,
) -> dict[str, Any]:
    name = normalise(local_name)
    declaration = declarations.get(name, {})
    return {
        "fact_id": _fact_id(declarations, name),
        "local_name": name,
        "type": normalise(declaration.get("type") or value_type),
        "unit": normalise(declaration.get("unit")),
        "value": value,
        "value_type": normalise(value_type),
    }


def _types_compatible(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_type, right_type = normalise(left.get("type")), normalise(right.get("type"))
    numeric = {"number", "integer"}
    if left_type and right_type and left_type != right_type and not ({left_type, right_type} <= numeric):
        return False
    left_unit, right_unit = normalise(left.get("unit")), normalise(right.get("unit"))
    return not (left_unit and right_unit and left_unit != right_unit)


def _bindings_compatible(
    writers: Iterable[Mapping[str, Any]], readers: Iterable[Mapping[str, Any]]
) -> bool:
    return any(_types_compatible(writer, reader) for writer in writers for reader in readers)


def _read_bindings(rule: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    declarations = _declarations(rule)
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(local_name: Any, *, value: Any = None, value_type: Any = None) -> None:
        endpoint = _endpoint(declarations, local_name, value=value, value_type=value_type)
        if endpoint["fact_id"]:
            found[endpoint["fact_id"]].append(endpoint)

    for predicate in [*_mappings(rule.get("condition_predicates")), *_mappings(rule.get("exceptions"))]:
        add(predicate.get("variable"), value=predicate.get("value"), value_type=predicate.get("value_type"))
        if normalise(predicate.get("value_type")) == "variable_reference":
            add(predicate.get("value"))

    for outcome in _mappings(rule.get("outcomes")):
        if normalise(outcome.get("value_type")) != "feel_expression":
            continue
        expression = str(outcome.get("value") or "")
        found_names = {normalise(token) for token in _IDENT.findall(expression)}
        for name in declarations:
            if name in found_names or (" " in name and name in expression.lower()):
                add(name)
    return found


def _write_bindings(rule: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Actual assignments only; declaring an output is not producing a fact."""
    declarations = _declarations(rule)
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in _mappings(rule.get("outcomes")):
        if normalise(outcome.get("operator")) not in {"=", "==", "assign", "set"}:
            continue
        endpoint = _endpoint(
            declarations,
            outcome.get("variable"),
            value=outcome.get("value"),
            value_type=outcome.get("value_type"),
        )
        if endpoint["fact_id"]:
            found[endpoint["fact_id"]].append(endpoint)
    return found


def rule_writes(rule: Mapping[str, Any]) -> set[str]:
    """Symbols this rule assigns.

    Only outcome assignments count. A declaration says what a variable could
    hold; it does not prove that this rule produces a value for it.
    """
    return set(_write_bindings(rule))


def rule_reads(rule: Mapping[str, Any]) -> set[str]:
    """Symbols this rule consumes.

    Condition predicates, exception predicates, and -- a channel the previous
    structural check missed entirely -- the operands of any outcome expressed
    as a ``feel_expression``.  A rule computing ``a / b`` genuinely consumes
    ``a`` and ``b``, and an edge feeding either of them is real.
    """
    return set(_read_bindings(rule))


def rule_passages(rule: Mapping[str, Any]) -> set[tuple[str, str]]:
    """``(chunk_path, section_id)`` pointers this rule was extracted from."""
    found: set[tuple[str, str]] = set()

    def add(value: Any) -> None:
        for ref in _mappings(value):
            pointer = (
                normalise(ref.get("chunk_path") or ref.get("document")),
                normalise(ref.get("section_id") or ref.get("section")),
            )
            if any(pointer):
                found.add(pointer)

    add(rule.get("source_reference"))
    evidence = rule.get("field_evidence")
    if isinstance(evidence, Mapping):
        for value in evidence.values():
            add(value)
    return found


def build_fact_registry(graph_or_rules: Any) -> dict[str, dict[str, Any]]:
    """Build a deterministic graph-wide index of declared semantic facts.

    The registry makes aliasing, type/unit drift, and producer/consumer
    provenance visible to later agents. It never guesses aliases: only an
    explicit ``fact_id`` (or the normalized-name compatibility fallback)
    binds local declarations.
    """
    registry: dict[str, dict[str, Any]] = {}
    for rule in _rules_of(graph_or_rules):
        rule_id = _rule_id(rule)
        declarations = _declarations(rule)
        writes, reads = _write_bindings(rule), _read_bindings(rule)
        for local_name, declaration in declarations.items():
            fact_id = _fact_id(declarations, local_name)
            if not fact_id:
                continue
            entry = registry.setdefault(fact_id, {
                "fact_id": fact_id,
                "aliases": set(),
                "types": set(),
                "units": set(),
                "producer_rule_ids": set(),
                "consumer_rule_ids": set(),
            })
            entry["aliases"].add(local_name)
            if normalise(declaration.get("type")):
                entry["types"].add(normalise(declaration.get("type")))
            if normalise(declaration.get("unit")):
                entry["units"].add(normalise(declaration.get("unit")))
            if fact_id in writes and rule_id:
                entry["producer_rule_ids"].add(rule_id)
            if fact_id in reads and rule_id:
                entry["consumer_rule_ids"].add(rule_id)

    output: dict[str, dict[str, Any]] = {}
    for fact_id, entry in sorted(registry.items()):
        types, units = sorted(entry["types"]), sorted(entry["units"])
        issues = []
        if len(types) > 1 and not set(types) <= {"integer", "number"}:
            issues.append("incompatible declared types")
        if len(units) > 1:
            issues.append("incompatible declared units")
        output[fact_id] = {
            "fact_id": fact_id,
            "aliases": sorted(entry["aliases"]),
            "types": types,
            "units": units,
            "producer_rule_ids": sorted(entry["producer_rule_ids"]),
            "consumer_rule_ids": sorted(entry["consumer_rule_ids"]),
            "contract_issues": issues,
        }
    return output


# ---------------------------------------------------------------------------
# relations
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Relation:
    """One derived relationship, carrying the evidence that justifies it.

    ``symbols`` is the set that produced the relation, so a reviewer (and
    :func:`relation_holds`) can re-check the claim against the graph rather
    than trusting a stored flag.
    """

    source_rule_id: str
    target_rule_id: str
    kind: str
    symbols: tuple[str, ...]
    directed: bool
    basis: str
    rationale: str
    proof: Mapping[str, Any] | None = None

    def key(self) -> tuple[str, str, str]:
        return (self.source_rule_id, self.target_rule_id, self.kind)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "source_rule_id": self.source_rule_id,
            "target_rule_id": self.target_rule_id,
            "kind": self.kind,
            "symbols": list(self.symbols),
            "directed": self.directed,
            "basis": self.basis,
            "rationale": self.rationale,
        }
        if self.proof is not None:
            payload["proof"] = dict(self.proof)
        return payload


def relation_contract_sha256(
    source: Mapping[str, Any], target: Mapping[str, Any], symbols: Iterable[str]
) -> str:
    """Fingerprint the exact contract slice on which a directed proof depends."""
    payload = {
        "source_rule_id": _rule_id(source),
        "source_outcomes": source.get("outcomes"),
        "source_variables": source.get("variables"),
        "source_scope": source.get("applicability_scope"),
        "target_rule_id": _rule_id(target),
        "target_predicates": target.get("condition_predicates"),
        "target_logic": target.get("condition_logic"),
        "target_variables": target.get("variables"),
        "target_scope": target.get("applicability_scope"),
        "symbols": sorted(set(symbols)),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RelationRefusal:
    """A relation kind that was requested but cannot be decided."""

    code: str
    kind: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "kind": self.kind, "detail": self.detail}


@dataclass
class RelationSet:
    """Everything derived from one graph, kept separate by kind on purpose.

    ``dependencies`` is the only collection safe to topologically order:
    associations are symmetric and conflicts are undirected, so folding either
    into a DAG would invent an ordering the evidence does not support.
    """

    dependencies: list[Relation] = field(default_factory=list)
    conflicts: list[Relation] = field(default_factory=list)
    associations: list[Relation] = field(default_factory=list)
    refusals: list[RelationRefusal] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dependencies": [r.as_dict() for r in self.dependencies],
            "conflicts": [r.as_dict() for r in self.conflicts],
            "associations": [r.as_dict() for r in self.associations],
            "refusals": [r.as_dict() for r in self.refusals],
            "counts": {
                "dependencies": len(self.dependencies),
                "conflicts": len(self.conflicts),
                "associations": len(self.associations),
                "refusals": len(self.refusals),
            },
        }


def _rules_of(graph_or_rules: Any) -> list[Mapping[str, Any]]:
    if isinstance(graph_or_rules, Mapping):
        candidates = graph_or_rules.get("business_rules") or []
    else:
        candidates = graph_or_rules or []
    return [rule for rule in candidates if isinstance(rule, Mapping)]


def _rule_id(rule: Mapping[str, Any]) -> str:
    return str(rule.get("rule_id") or "").strip()


def _index(rules: Sequence[Mapping[str, Any]]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """symbol -> writers, symbol -> readers."""
    writers: dict[str, set[str]] = defaultdict(set)
    readers: dict[str, set[str]] = defaultdict(set)
    for rule in rules:
        rid = _rule_id(rule)
        if not rid:
            continue
        for symbol in rule_writes(rule):
            writers[symbol].add(rid)
        for symbol in rule_reads(rule):
            readers[symbol].add(rid)
    return writers, readers


def _binding_index(
    rules: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, dict[str, list[dict[str, Any]]]]]:
    writers: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    readers: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    for rule in rules:
        rid = _rule_id(rule)
        if not rid:
            continue
        for fact_id, endpoints in _write_bindings(rule).items():
            writers[fact_id][rid] = endpoints
        for fact_id, endpoints in _read_bindings(rule).items():
            readers[fact_id][rid] = endpoints
    return writers, readers


def derive_dataflow(graph_or_rules: Any) -> list[Relation]:
    """Every ``A writes s`` / ``B reads s`` pair, exhaustively.

    A hash join over ``(symbol, rule)`` entries rather than a pass over rule
    pairs, so cost is linear in the number of declared symbols instead of
    quadratic in the rule count -- which is what makes exhaustive coverage
    affordable where sampled LLM proposal was not.
    """
    rules = _rules_of(graph_or_rules)
    writers, readers = _binding_index(rules)
    by_id = {_rule_id(rule): rule for rule in rules}
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for symbol, producing in writers.items():
        for target, read_endpoints in readers.get(symbol, {}).items():
            for source, write_endpoints in producing.items():
                if (
                    source != target
                    and _bindings_compatible(write_endpoints, read_endpoints)
                    and scopes_may_overlap(
                        by_id[source].get("applicability_scope"),
                        by_id[target].get("applicability_scope"),
                    )
                ):
                    grouped[(source, target)].add(symbol)

    relations = []
    for (source, target), symbols in grouped.items():
        ordered = tuple(sorted(symbols))
        shown = ", ".join(ordered[:3]) + (" …" if len(ordered) > 3 else "")
        relations.append(Relation(
            source_rule_id=source,
            target_rule_id=target,
            kind="dataflow",
            symbols=ordered,
            directed=True,
            basis="deterministic",
            rationale=f"{source} assigns {shown}; {target} reads it as an input.",
        ))
    return sorted(relations, key=lambda r: r.key())


def derive_conflicts(graph_or_rules: Any) -> list[Relation]:
    """Rule pairs assigning the same symbol -- the conflict candidate surface.

    Emitted undirected (as an ordered pair for stability).  Whether a candidate
    is a real conflict depends on the two conditions being co-satisfiable and
    the assigned values differing, which is a solver question this module does
    not answer.
    """
    rules = _rules_of(graph_or_rules)
    writer_bindings, _ = _binding_index(rules)
    by_id = {_rule_id(rule): rule for rule in rules}
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for symbol, producing in writer_bindings.items():
        ordered_ids = sorted(producing)
        for i, first in enumerate(ordered_ids):
            for second in ordered_ids[i + 1:]:
                if (
                    _bindings_compatible(producing[first], producing[second])
                    and scopes_may_overlap(
                        by_id[first].get("applicability_scope"),
                        by_id[second].get("applicability_scope"),
                    )
                ):
                    grouped[(first, second)].add(symbol)

    relations = []
    for (first, second), symbols in grouped.items():
        ordered = tuple(sorted(symbols))
        shown = ", ".join(ordered[:3]) + (" …" if len(ordered) > 3 else "")
        relations.append(Relation(
            source_rule_id=first,
            target_rule_id=second,
            kind="conflict",
            symbols=ordered,
            directed=False,
            basis="deterministic",
            rationale=f"{first} and {second} both assign {shown}.",
        ))
    return sorted(relations, key=lambda r: r.key())


def derive_associations(
    graph_or_rules: Any,
    *,
    shared_input: bool = True,
    shared_passage: bool = True,
    max_passage_fanout: int = DEFAULT_MAX_PASSAGE_FANOUT,
) -> list[Relation]:
    """Symmetric co-sensitivity: same input symbol, or same source passage.

    This is the relation the previous prompt explicitly forbade -- "do not emit
    an edge merely because rules share an input" -- on the reasonable grounds
    that thematic similarity is not dependency.  It is not dependency, and it
    is not emitted as one.  It is still the dominant real structure in
    catalogue-shaped corpora, where rules read external facts no other rule
    produces, and it is what answers "this passage changed, what moves?"
    """
    rules = _rules_of(graph_or_rules)
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)

    if shared_input:
        writer_bindings, reader_bindings = _binding_index(rules)
        by_id = {_rule_id(rule): rule for rule in rules}
        for symbol, consuming in reader_bindings.items():
            if writer_bindings.get(symbol):
                continue                        # produced somewhere: that is dataflow, not association
            ordered_ids = sorted(consuming)
            if len(ordered_ids) > max_passage_fanout:
                continue
            for i, first in enumerate(ordered_ids):
                for second in ordered_ids[i + 1:]:
                    if (
                        _bindings_compatible(consuming[first], consuming[second])
                        and scopes_may_overlap(
                            by_id[first].get("applicability_scope"),
                            by_id[second].get("applicability_scope"),
                        )
                    ):
                        grouped[(first, second)].add(f"input:{symbol}")

    if shared_passage:
        by_passage: dict[tuple[str, str], set[str]] = defaultdict(set)
        for rule in rules:
            rid = _rule_id(rule)
            if not rid:
                continue
            for pointer in rule_passages(rule):
                by_passage[pointer].add(rid)
        for pointer, citing in by_passage.items():
            ordered_ids = sorted(citing)
            if len(ordered_ids) > max_passage_fanout:
                continue                        # document-level catch-all, not a passage
            label = "#".join(part for part in pointer if part)
            for i, first in enumerate(ordered_ids):
                for second in ordered_ids[i + 1:]:
                    grouped[(first, second)].add(f"passage:{label}")

    relations = []
    for (first, second), symbols in grouped.items():
        ordered = tuple(sorted(symbols))
        kinds = sorted({symbol.split(":", 1)[0] for symbol in ordered})
        relations.append(Relation(
            source_rule_id=first,
            target_rule_id=second,
            kind="association",
            symbols=ordered,
            directed=False,
            basis="deterministic",
            rationale=(
                f"{first} and {second} share {' and '.join(kinds)}; "
                "a change to it may affect both. This is co-sensitivity, not dependency."
            ),
        ))
    return sorted(relations, key=lambda r: r.key())


def classify_gating(
    relations: Iterable[Relation],
    graph_or_rules: Any,
    *,
    entails: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool | None] | None = None,
) -> list[Relation]:
    """Promote ``dataflow`` to ``gating`` where the target genuinely depends.

    ``dataflow`` says only that the target reads a symbol the source assigns.
    ``gating`` is the stronger claim the old ``prerequisite`` label gestured at
    without ever testing: the target *cannot fire* unless the source's outcome
    holds -- i.e. ``cond(target) ∧ ¬outcome(source)`` is unsatisfiable.

    ``entails`` receives ``(source_rule, target_rule, symbol)`` and returns
    ``True`` (entailed), ``False`` (not entailed), or ``None`` (undecided --
    the rules did not compile, or the solver timed out).  Only ``True``
    promotes.  With no oracle supplied nothing is promoted, so the default is
    fail-closed: an unchecked relation is reported as the weaker claim rather
    than the stronger one.
    """
    rules = {_rule_id(rule): rule for rule in _rules_of(graph_or_rules)}
    out: list[Relation] = []
    for relation in relations:
        if relation.kind != "dataflow" or entails is None:
            out.append(relation)
            continue
        source = rules.get(relation.source_rule_id)
        target = rules.get(relation.target_rule_id)
        if source is None or target is None:
            out.append(relation)
            continue
        promoted = False
        for symbol in relation.symbols:
            try:
                verdict = entails(source, target, symbol)
            except Exception:                   # an oracle failure must not lose the relation
                verdict = None
            if verdict is True:
                promoted = True
                break
        if not promoted:
            out.append(relation)
            continue
        out.append(Relation(
            source_rule_id=relation.source_rule_id,
            target_rule_id=relation.target_rule_id,
            kind="gating",
            symbols=relation.symbols,
            directed=True,
            basis="solver",
            rationale=(
                f"{relation.target_rule_id}'s condition entails a value assigned "
                f"by {relation.source_rule_id}; this proves logical gating on the "
                "fact, not real-world temporal order."
            ),
            proof={
                "method": "smt_unsat",
                "status": "proved",
                "contract_sha256": relation_contract_sha256(source, target, relation.symbols),
            },
        ))
    return sorted(out, key=lambda r: r.key())


# ---------------------------------------------------------------------------
# validation / re-validation
# ---------------------------------------------------------------------------

def relation_holds(
    relation: Relation,
    graph_or_rules: Any,
    *,
    entails: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool | None] | None = None,
) -> bool:
    """Does this relation's acceptance condition still hold against the graph?

    The condition checked is the one the relation's own kind asserts, not a
    single shared test standing in for all of them.  Stages downstream of
    derivation rewrite variables in place, so a relation is only as true as its
    last re-check -- see :func:`revalidate`.
    """
    rules = {_rule_id(rule): rule for rule in _rules_of(graph_or_rules)}
    source = rules.get(relation.source_rule_id)
    target = rules.get(relation.target_rule_id)
    if source is None or target is None:
        return False

    if relation.kind in ("dataflow", "gating"):
        surviving = rule_writes(source) & rule_reads(target) & set(relation.symbols)
        if not surviving or not scopes_may_overlap(
            source.get("applicability_scope"), target.get("applicability_scope")
        ):
            return False
        source_bindings, target_bindings = _write_bindings(source), _read_bindings(target)
        compatible = {
            symbol for symbol in surviving
            if _bindings_compatible(source_bindings.get(symbol, ()), target_bindings.get(symbol, ()))
        }
        if not compatible:
            return False
        if relation.kind == "dataflow":
            return True
        if entails is None:
            return False
        return any(entails(source, target, symbol) is True for symbol in compatible)
    if relation.kind == "conflict":
        surviving = rule_writes(source) & rule_writes(target) & set(relation.symbols)
        if not surviving or not scopes_may_overlap(
            source.get("applicability_scope"), target.get("applicability_scope")
        ):
            return False
        source_bindings, target_bindings = _write_bindings(source), _write_bindings(target)
        return any(
            _bindings_compatible(source_bindings.get(symbol, ()), target_bindings.get(symbol, ()))
            for symbol in surviving
        )
    if relation.kind == "association":
        inputs = {s.split(":", 1)[1] for s in relation.symbols if s.startswith("input:")}
        if inputs and (rule_reads(source) & rule_reads(target) & inputs):
            return True
        passages = {s.split(":", 1)[1] for s in relation.symbols if s.startswith("passage:")}
        if passages:
            shared = rule_passages(source) & rule_passages(target)
            labels = {"#".join(part for part in pointer if part) for pointer in shared}
            return bool(labels & passages)
        return False
    return False


def revalidate(
    relations: Iterable[Relation],
    graph_or_rules: Any,
    *,
    entails: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool | None] | None = None,
) -> tuple[list[Relation], list[Relation]]:
    """Split relations into those that still hold and those that no longer do.

    Exists because derivation and repair are different stages: the readiness
    and remediation stages rewrite variables in place (renaming an output to a
    list-typed ``allowed_*_values`` form, for instance), which can silently
    invalidate a relation derived before the rewrite.  Re-running the
    acceptance condition is cheap; trusting a stored flag is how a relation
    ends up asserting a symbol flow that no longer exists.
    """
    held, dropped = [], []
    for relation in relations:
        (held if relation_holds(relation, graph_or_rules, entails=entails) else dropped).append(relation)
    return held, dropped


def refusal_for_declared_kind(kind: Any) -> RelationRefusal | None:
    """Refusal for a legacy ``dependency_type`` this model will not decide."""
    name = normalise(kind)
    if name in UNREPRESENTABLE_KINDS:
        code, detail = UNREPRESENTABLE_KINDS[name]
        return RelationRefusal(code=code, kind=name, detail=detail)
    return None


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------

def derive_relations(
    graph_or_rules: Any,
    *,
    entails: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool | None] | None = None,
    include_associations: bool = True,
    max_passage_fanout: int = DEFAULT_MAX_PASSAGE_FANOUT,
    declared_kinds: Iterable[Any] = (),
) -> RelationSet:
    """Derive every relation kind from one graph, in one pass.

    ``declared_kinds`` lets a caller hand over legacy ``dependency_type``
    values so the ones this model refuses are reported explicitly rather than
    disappearing without trace.
    """
    dependencies = classify_gating(derive_dataflow(graph_or_rules), graph_or_rules, entails=entails)
    result = RelationSet(
        dependencies=dependencies,
        conflicts=derive_conflicts(graph_or_rules),
        associations=(
            derive_associations(graph_or_rules, max_passage_fanout=max_passage_fanout)
            if include_associations else []
        ),
    )
    seen: set[str] = set()
    for kind in declared_kinds:
        refusal = refusal_for_declared_kind(kind)
        if refusal is not None and refusal.kind not in seen:
            seen.add(refusal.kind)
            result.refusals.append(refusal)
    result.refusals.sort(key=lambda r: r.kind)
    return result


def prune_dangling_related_rules(graph: Mapping[str, Any], *, stage: str = "") -> dict[str, Any]:
    """Drop ``related_rules`` entries naming a rule the graph does not contain.

    ``related_rules`` is the one dependency channel nothing checks. It is
    written by the extraction model, which is asked to list "rule_ids that
    interact with this rule", and from then on it is carried untouched into the
    certified graph: no stage validates the targets, and no stage prunes it when
    optimization removes a rule.

    Both failure modes are real. On an 832-rule privacy run the shipped graph
    carried 18 references to 17 rule ids that do not exist -- 9 to rules that
    optimization deleted, and 8 that never existed in any graph at any stage,
    invented by the model outright. agent_10 discarded them while building DAGs
    and recorded ``dropped_edges: 0``, so the loss was invisible too.

    Targets are checked against the rule set only. A surviving entry still means
    no more than "the extraction model asserted these interact"; the decidable
    relations live in ``dependency_details`` and are checked by
    :func:`revalidate_graph`. ``divergent_from_typed`` counts the gap between
    the two so it cannot be mistaken for agreement.
    """
    rules = list(_rules_of(graph))
    known = {_rule_id(rule) for rule in rules if _rule_id(rule)}

    dropped: list[dict[str, Any]] = []
    kept_pairs: set[tuple[str, str]] = set()
    for rule in rules:
        related = rule.get("related_rules")
        if not isinstance(related, list) or not related:
            continue
        source = _rule_id(rule)
        surviving: list[Any] = []
        for entry in related:
            target = str(entry.get("rule_id") if isinstance(entry, Mapping) else entry or "")
            if target and target not in known:
                dropped.append({
                    "source_rule_id": source,
                    "target_rule_id": target,
                    "reason": "related_rules names a rule id that is not in the graph",
                })
                continue
            surviving.append(entry)
            if target:
                kept_pairs.add((source, target))
        rule["related_rules"] = surviving

    details = graph.get("dependency_details")
    typed_pairs = {
        (str(entry.get("source_rule_id") or ""), str(entry.get("target_rule_id") or ""))
        for entry in ((details or {}).get("dependencies") or [])
        if isinstance(entry, Mapping)
    } if isinstance(details, Mapping) else set()

    report = {
        "stage": stage,
        "checked": sum(
            len(rule.get("related_rules") or []) for rule in rules
        ) + len(dropped),
        "kept": len(kept_pairs),
        "dropped": dropped,
        "divergent_from_typed": len(kept_pairs - typed_pairs),
        "typed_relations": len(typed_pairs),
    }
    if isinstance(details, dict):
        details["related_rules_integrity"] = {
            key: (len(value) if isinstance(value, list) else value)
            for key, value in report.items()
        }
    return report


def revalidate_graph(
    graph: Mapping[str, Any],
    *,
    stage: str = "",
    entails: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool | None] | None = None,
) -> dict[str, Any]:
    """Re-check stored relations against the graph as it now stands, in place.

    Derivation and repair are separate stages.  Readiness and remediation
    rewrite variables in place -- renaming an output into a list-typed
    ``allowed_*_values`` form, for instance -- which can invalidate a relation
    derived beforehand.  A real run shipped an edge asserting a rule produced
    ``transaction_type`` after that output had been renamed, carrying
    ``structurally_supported: true`` and a confidence of 98.6, because nothing
    re-checked it.

    Dropped relations are removed from the graph and returned, so the loss is
    visible in the stage report rather than silent.  A relation stored without
    ``symbols`` (from a graph produced before symbols were recorded) is checked
    for any surviving write/read overlap instead, which is the weaker condition
    the older model used.
    """
    details = graph.get("dependency_details")
    if not isinstance(details, Mapping):
        return {"stage": stage, "checked": 0, "held": 0, "dropped": []}

    stored = [entry for entry in (details.get("dependencies") or []) if isinstance(entry, Mapping)]
    rules = {_rule_id(rule): rule for rule in _rules_of(graph)}

    held_payload, dropped_payload, downgraded_payload = [], [], []
    for entry in stored:
        source = rules.get(str(entry.get("source_rule_id") or ""))
        target = rules.get(str(entry.get("target_rule_id") or ""))
        symbols = tuple(normalise(s) for s in (entry.get("symbols") or []) if normalise(s))
        if source is None or target is None:
            holds = False
        elif symbols:
            kind = normalise(entry.get("dependency_type")) or "dataflow"
            relation = Relation(
                source_rule_id=str(entry.get("source_rule_id")),
                target_rule_id=str(entry.get("target_rule_id")),
                kind=kind,
                symbols=symbols, directed=True, basis="", rationale="",
            )
            holds = relation_holds(relation, graph, entails=entails)
            if kind == "gating" and not holds:
                weaker = Relation(
                    relation.source_rule_id, relation.target_rule_id, "dataflow",
                    relation.symbols, True, "deterministic", "",
                )
                if relation_holds(weaker, graph):
                    downgraded = dict(entry)
                    downgraded["dependency_type"] = "dataflow"
                    downgraded["basis"] = "deterministic"
                    downgraded["downgraded_from"] = "gating"
                    downgraded.pop("proof", None)
                    downgraded["rationale"] = (
                        "The write/read channel still exists, but the solver proof "
                        "was not reproduced against the current graph."
                    )
                    held_payload.append(downgraded)
                    downgraded_payload.append(downgraded)
                    continue
        else:
            holds = bool(rule_writes(source) & rule_reads(target))
        (held_payload if holds else dropped_payload).append(entry)

    if isinstance(details, dict):
        details["dependencies"] = held_payload
        details["revalidation"] = {
            "stage": stage,
            "checked": len(stored),
            "held": len(held_payload),
            "dropped": len(dropped_payload),
            "downgraded": len(downgraded_payload),
        }
    return {
        "stage": stage,
        "checked": len(stored),
        "held": len(held_payload),
        "downgraded": [
            {
                "source_rule_id": entry.get("source_rule_id"),
                "target_rule_id": entry.get("target_rule_id"),
                "from": "gating",
                "to": "dataflow",
            }
            for entry in downgraded_payload
        ],
        "dropped": [
            {
                "source_rule_id": entry.get("source_rule_id"),
                "target_rule_id": entry.get("target_rule_id"),
                "dependency_type": entry.get("dependency_type"),
                "reason": "acceptance condition no longer holds after this stage rewrote the graph",
            }
            for entry in dropped_payload
        ],
    }
