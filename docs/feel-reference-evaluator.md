# BE-1 reference evaluator

`utils/feel.py` is the bounded reference evaluator for the declared LExec IR
v1 subset.  It is deliberately independent from the lowering implementation:
it evaluates the IR document, not v2 extraction fields, and returns a
structured result with `status`, matched/unknown rule IDs, outputs, and
diagnostics.

The evaluator implements Kleene three-valued formulas, explicit null checks,
rule exceptions as defeaters, literal/symbol assignments, and `UNIQUE`/`ANY`
table dispatch.  A rule condition that is false is a no-match; a missing input
or unknown exception is `unknown`, never false.  A table with a proof status
other than `proved` is refused before evaluation.  `COLLECT` output semantics,
priority ordering, contextual jurisdiction/party/date metadata, and any
unsupported hit policy are refused or unknown rather than silently treated as
universal.

This is a reference semantics for the bounded IR subset, not source
correctness, legal interpretation, a complete FEEL engine, or an SMT backend.
The evaluator is intended to be compared with later DMN/SMT backends; its
agreement with another implementation alone cannot establish compiler
correctness.
