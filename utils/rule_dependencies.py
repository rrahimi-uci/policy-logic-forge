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
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = [
    "RELATION_KINDS",
    "UNREPRESENTABLE_KINDS",
    "Relation",
    "RelationRefusal",
    "normalise",
    "rule_writes",
    "rule_reads",
    "rule_passages",
    "derive_dataflow",
    "derive_conflicts",
    "derive_associations",
    "classify_gating",
    "relation_holds",
    "revalidate",
    "refusal_for_declared_kind",
    "derive_relations",
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


def _declared(rule: Mapping[str, Any]) -> dict[str, str]:
    """Declared variable name -> role."""
    out: dict[str, str] = {}
    for variable in _mappings(rule.get("variables")):
        name = normalise(variable.get("name"))
        if name:
            out.setdefault(name, normalise(variable.get("role")))
    return out


def rule_writes(rule: Mapping[str, Any]) -> set[str]:
    """Symbols this rule assigns.

    Outcome targets plus anything declared ``role: output``.  The contract
    validator already requires an outcome's variable to be declared output, so
    these agree on a valid rule; taking the union keeps a partially-repaired
    rule from silently losing an edge.
    """
    symbols = {normalise(item.get("variable")) for item in _mappings(rule.get("outcomes"))}
    symbols |= {name for name, role in _declared(rule).items() if role == "output"}
    return {symbol for symbol in symbols if symbol}


def rule_reads(rule: Mapping[str, Any]) -> set[str]:
    """Symbols this rule consumes.

    Condition predicates, exception predicates, and -- a channel the previous
    structural check missed entirely -- the operands of any outcome expressed
    as a ``feel_expression``.  A rule computing ``a / b`` genuinely consumes
    ``a`` and ``b``, and an edge feeding either of them is real.
    """
    symbols = {normalise(item.get("variable")) for item in _mappings(rule.get("condition_predicates"))}
    symbols |= {normalise(item.get("variable")) for item in _mappings(rule.get("exceptions"))}

    declared = _declared(rule)
    for outcome in _mappings(rule.get("outcomes")):
        if normalise(outcome.get("value_type")) != "feel_expression":
            continue
        expression = str(outcome.get("value") or "")
        if not expression:
            continue
        found = {normalise(token) for token in _IDENT.findall(expression)}
        # A declared name may contain spaces, which the identifier scan cannot
        # see; fall back to a containment test for those.
        for name in declared:
            if " " in name and name in expression.lower():
                found.add(name)
        symbols |= found & set(declared)

    # Predicates may compare one variable against another; the right-hand side
    # is consumed too.
    for predicate in _mappings(rule.get("condition_predicates")):
        if normalise(predicate.get("value_type")) == "variable_reference":
            symbols.add(normalise(predicate.get("value")))

    return {symbol for symbol in symbols if symbol}


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

    def key(self) -> tuple[str, str, str]:
        return (self.source_rule_id, self.target_rule_id, self.kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_rule_id": self.source_rule_id,
            "target_rule_id": self.target_rule_id,
            "kind": self.kind,
            "symbols": list(self.symbols),
            "directed": self.directed,
            "basis": self.basis,
            "rationale": self.rationale,
        }


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


def derive_dataflow(graph_or_rules: Any) -> list[Relation]:
    """Every ``A writes s`` / ``B reads s`` pair, exhaustively.

    A hash join over ``(symbol, rule)`` entries rather than a pass over rule
    pairs, so cost is linear in the number of declared symbols instead of
    quadratic in the rule count -- which is what makes exhaustive coverage
    affordable where sampled LLM proposal was not.
    """
    rules = _rules_of(graph_or_rules)
    writers, readers = _index(rules)
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for symbol, producing in writers.items():
        for target in readers.get(symbol, ()):  # noqa: B007 - explicit for clarity
            for source in producing:
                if source != target:            # a self-loop is not a dependency
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
    writers, _ = _index(rules)
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for symbol, producing in writers.items():
        ordered_ids = sorted(producing)
        for i, first in enumerate(ordered_ids):
            for second in ordered_ids[i + 1:]:
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
        writers, readers = _index(rules)
        for symbol, consuming in readers.items():
            if writers.get(symbol):
                continue                        # produced somewhere: that is dataflow, not association
            ordered_ids = sorted(consuming)
            if len(ordered_ids) > max_passage_fanout:
                continue
            for i, first in enumerate(ordered_ids):
                for second in ordered_ids[i + 1:]:
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
                f"{relation.target_rule_id} cannot be evaluated unless "
                f"{relation.source_rule_id}'s outcome holds."
            ),
        ))
    return sorted(out, key=lambda r: r.key())


# ---------------------------------------------------------------------------
# validation / re-validation
# ---------------------------------------------------------------------------

def relation_holds(relation: Relation, graph_or_rules: Any) -> bool:
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
        return bool(rule_writes(source) & rule_reads(target) & set(relation.symbols))
    if relation.kind == "conflict":
        return bool(rule_writes(source) & rule_writes(target) & set(relation.symbols))
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


def revalidate(relations: Iterable[Relation], graph_or_rules: Any) -> tuple[list[Relation], list[Relation]]:
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
        (held if relation_holds(relation, graph_or_rules) else dropped).append(relation)
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
