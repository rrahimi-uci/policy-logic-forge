# LExec IR v1 semantics

This document freezes the meaning of the supported compiler subset.  The
JSON Schema in [`plan/lexec-ir-v1.schema.json`](../plan/lexec-ir-v1.schema.json)
defines shape; it does not, by itself, define evaluation or prove that a
lowering preserved meaning.

## Boundary and provenance

`utils.lexec_ir.lower_graph` accepts the pipeline's v2 rule graph and returns
one `lexec-ir/1.0` document unit.  A rule is either emitted completely or is
omitted from `rules` and represented by a refusal with
`requires_review: true`.  There is no partial rule output.  This is the
fail-closed boundary used by later backends.

Every emitted symbol, rule, effect, exception, and refusal carries a source
span.  v2 currently records word positions and quoted evidence rather than
character offsets.  Until the source index supplies document-local character
offsets, the lowering uses offsets within the quoted evidence and preserves
the source digest supplied by the graph (or a deterministic digest of the
quoted evidence when none is supplied).  These spans are therefore suitable
for audit and mutation tests, but are not a claim that the excerpt offset is a
whole-document offset.  A future source-index adapter must replace these
excerpt-local spans before making a document-level localization claim.

The envelope also contains `ignored_fields`.  This is a required accounting
ledger, not a discard bin: fields that are annotations rather than executable
semantics are listed with a stable reason.  `NON_EXECUTABLE_METADATA` covers
descriptions, examples, dependency prose, derived DMN/BPMN projections, and
other redundant annotations.  `AUDIT_STATUS_NOT_EXECUTABLE` covers readiness,
grounding, contract-issue, and source-verification status.  Unknown fields are
refused.  A downstream certification step must inspect this ledger before
calling a rule executable.

## Types and supported predicates

v2 `boolean`, `number`, `enum`, and justified `string` variables lower to IR
`bool`, `real`, `enum`, and `string`.  v2 `number` is conservatively `real`;
the IR does not infer an integer theory from an integral-looking value.
Enums require a non-empty `allowed_values` list.  Strings require
`free_text: true` and expose the predicates observed for that symbol.

The supported atomic predicates are:

| v2 form | IR form |
| --- | --- |
| `==`, `!=`, `>`, `>=`, `<`, `<=` | `eq`, `ne`, `gt`, `ge`, `lt`, `le` |
| `in` over a list | an `or` of equality formulas |
| `in`/`not_in` with `range` | `in_binned_range` (the canonical range is a string literal) |
| `in`/`not_in` over a string | `contains` / `not contains` |
| `contains` | `contains` |
| `is_null` | `is_null` |

Unknown operators, unsupported value types, undefined variable references,
empty membership sets, and type mismatches are refusals.  No date, duration,
list, free-form range, or implicit string coercion is performed.  A
`variable_reference` becomes a symbol operand only when its target is
declared.

## Formula evaluation model

Formula evaluation uses Kleene three-valued logic: `true`, `false`, and
`unknown`.  Missing/null operands evaluate to `unknown` for comparisons and
`is_null` is the only predicate that can test null explicitly.  `not` maps
`unknown` to `unknown`; `and` is false if any child is false, true only when
all children are true, and unknown otherwise; `or` is true if any child is
true, false only when all children are false, and unknown otherwise.  This
prevents a missing source value from silently satisfying a compliance rule.

Condition logic is lowered recursively from v2 `all`, `any`, and
`predicate_ref` nodes.  Flat `AND`/`OR` is retained for legacy v2 fixtures.

## Scope, exceptions, and effects

Scope metadata retains jurisdictions, responsible/counterparties, authority,
effective dates, and version status.  These are recorded but never
themselves resolved by the bounded evaluator (`utils/feel.py`): any rule
whose metadata is non-empty in one of these dimensions evaluates as
`unknown`, because the evaluator has no jurisdiction/party/date runtime
context.  This is a deliberate, tested safety property (see
`tests/test_feel.py::test_contextual_scope_and_collect_are_not_silently_executed`)
and out of scope for the differential-execution engine described in
`plan/regdelta-product-plan.md`, which evaluates one whole compiled document
against another rather than asking whether a rule is in force for a given
real-world date/party/jurisdiction.

`applicability_scope`'s `loan_types`, `transaction_types`, and
`occupancy_types` fields are, by contrast, lowered into a genuinely checkable
`scope.predicate` formula: each populated field becomes a dedicated free-text
string symbol (`loan_type`, `transaction_type`, `occupancy_type`) compared by
equality against the field's listed values (an implicit "or" across values,
an implicit "and" across the up-to-three fields).  A rule with none of these
three fields populated -- and no other applicability field populated -- has
a null scope predicate, i.e. is genuinely unscoped.  Every *other* structured
scope field without an IR representation, unresolved/inferred scope, and any
other non-empty unsupported applicability field are still refused rather
than dropped or silently treated as universal.

Exceptions use `semantics.exception_reading = defeater_or`: if any exception
condition is true, the rule is defeated; false exceptions do not affect the
rule, and unknown exception conditions remain unknown.  The empty exception
set is represented by no exception nodes.  Later conflict/exception work may
replace this with a proven composition, but it must update this document and
the schema version together.

An outcome assignment becomes an `assignment` effect.  Modality is derived
deterministically from existing v2 metadata: rule types containing
`prohibit`, `restriction`, or `forbidden` are `prohibition`; definition and
calculation rules are `definition`; otherwise `mandatory=true` is
`obligation`, `mandatory=false` is `permission`, and missing metadata is
`none`.  This inference is deliberately visible in the IR and is not a claim
that prose deontic force was independently validated.

## Tables and proof status

Rules are grouped into tables by output-target signature and hit policy.  A
table's policy proof starts as `unknown`/`unproved`; the lowering does not
claim disjointness, equal outputs on overlap, source precedence, or solver
validation.  Unknown at a table boundary is configured as `refuse`.

The provider-free `utils/smt.py` core can prove pairwise disjointness for
complete finite domains (booleans, enums, and small closed integer intervals)
and can find counterexamples for overlaps.  It never discretizes a continuous
real interval or ignores open integer endpoints.  It reports `unknown` for
open strings, real/unbounded intervals, malformed or type-incompatible
queries, and any invalid resource bound; a search that exceeds a valid bound
is `timeout`.  `PRIORITY` without an explicit precedence is refused, and
`COLLECT` remains unknown until a later backend freezes its overlap semantics.
Every proof record contains a query hash and witnesses where applicable.  The
explicit satisfiability, overlap, coverage, conflict, counterexample, and
witness query contract is documented in
[`docs/smt-query-protocol.md`](smt-query-protocol.md).  A real SMT backend
may replace this bounded core, but no backend may convert `unknown`, `timeout`,
or `refused` into a pass.

## What this implementation does not establish

Passing structural validation or the independent lowering oracle does not
establish corpus coverage, source truth, rule recall, table correctness, or
backend equivalence.  The current implementation is a G0 compiler boundary;
the scientific claims remain conditional on the corpus census, independent
annotations, solver proofs, and later mutation/equivalence experiments.
