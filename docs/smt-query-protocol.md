# Bounded SMT-shaped query protocol

`utils/smt.py` exposes a provider-free query interface for the LExec IR v1
subset. It has the shape of an SMT service, but the current implementation is
a bounded enumerator; it is not a complete SMT backend and does not require a
solver package at runtime.

## Queries

The public functions are:

- `query_satisfiable(formula, symbols)` — search for a satisfying assignment.
- `query_overlap(left_rule, right_rule, symbols)` — search for an assignment
  satisfying both rule conditions.
- `query_coverage(rules, symbols)` — require every enumerated assignment to
  satisfy at least one rule condition and return a coverage-gap witness when it
  does not.
- `query_conflicts(rules, symbols)` — search pairwise condition overlaps whose
  concrete effect maps differ.
- `query_counterexample(formula, symbols)` — search for a satisfying
  assignment to a caller-supplied violation formula.
- `query_witness(formula, symbols)` — named witness search for callers that do
  not want to describe the result as a counterexample.

Every result includes `query_type`, `status`, `witness`, `explored`, `reason`,
and a deterministic `query_sha256`. Query hashes include the query kind,
formula/rule payload, symbol declarations, and the `max_assignments` bound.
Changing a domain or search budget therefore invalidates the old query
identity. A witness is only returned for a concrete `sat` result; `unknown`
and `timeout` never become negative proofs.

## Status contract

Satisfiability and overlap use the solver statuses `sat`, `unsat`, `unknown`,
and `timeout`. Counterexample and witness queries preserve those same statuses;
`sat` means a witness was found and `unsat` means no witness was found in a
complete finite search. Coverage uses `proved` for a complete covered domain,
`counterexample` for a concrete uncovered assignment, and `unknown` or
`timeout` when coverage cannot be established. Conflict queries use `proved`,
`conflict`, `unknown`, or `timeout`.

An assignment whose condition evaluates to Kleene `unknown` prevents a
coverage proof. This is intentional: missing/null values cannot silently
satisfy a compliance rule. A concrete false coverage assignment is still a
valid gap even if the domain also contains unexplored values.

## Completeness boundary

The bounded core can exhaust booleans, enums, and small closed integer
intervals. Real intervals are continuous and are never discretized into an
integer approximation. Strings, open integer intervals, and unbounded numeric
intervals are incomplete; they may produce a useful satisfying witness, but
failure to find one is `unknown`. Searches above `max_assignments` are
`timeout`; a negative, non-integral, or boolean resource bound is malformed and
returns `unknown`. Malformed declarations, incompatible operand types, and
out-of-domain enum literals also return `unknown` rather than becoming
unsatisfiable proofs. A future native SMT backend may replace the enumerator,
but it must preserve the result schema and must not convert `unknown`,
`timeout`, or an IR refusal into a pass.
