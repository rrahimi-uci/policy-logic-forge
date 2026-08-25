# Restricted P3-prime comparison protocol

`utils/p3_prime.py` implements the restricted P3-prime comparison theorem
described in the proposal.  `compare_ir_tables(left_ir, right_ir,
thresholds=...)` compares two **known** LExec IR tables on representative cells
induced by an explicit finite threshold set that the caller supplies for both
tables.

The comparator includes missing values, finite boolean/enum values, numeric
threshold ties, immediate open/closed neighbors, and one representative point
for each interval cell.  Multiple dimensions use the Cartesian product of
these per-symbol choices.  Numeric literals in either table must be contained
in the declared threshold set; otherwise the precondition fails closed.

The supported comparison class is the interval/finite-domain subset:
conjunction/disjunction/negation, numeric comparisons, `in_binned_range`,
`is_null`, and boolean/enum equality.  String predicates, unsupported
operators, unproved policies, `COLLECT`, mismatched declarations, and invalid
threshold sets return `status: "refused"`.  A representative suite larger
than `max_cases` returns `status: "timeout"`.

Results use:

- `equivalent`: all generated representative assignments have the same
  observable status and output map;
- `different`: at least one assignment differs, with the assignment and both
  projections retained;
- `refused`/`timeout`: the theorem's preconditions or resource bound were not
  met.

This is a comparison theorem for two known artifacts.  It is not exhaustive
instrument validation, a certificate against an unknown reference, or a
replacement for the 13,080-case anchor protocol.
