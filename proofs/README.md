# Machine-checked properties

Six properties of this system are stated precisely enough to be *proved* rather
than tested. Each is discharged by **exhaustive enumeration over a finite
domain**, so within that domain the result is a proof, not a sample.

Run them with:

```bash
.venv/bin/python proofs/check_properties.py
```

| # | Property | Domain | Method |
| --- | --- | --- | --- |
| 1 | `(T, ⊏)` is a strict partial order — irreflexive, asymmetric, transitive | all 15 business types | all 3,615 tuples |
| 2 | `reconcile_types(S)` returns the unique ⊏-least element of `S`, or ⊥ when none exists | all subsets up to size 4 | 1,940 subsets |
| 3 | `Money ∦ Percentage` — incomparable, so neither silently coerces to the other | the pair | direct |
| 4 | Prover **soundness**: `sat(w) ⟹ w ⊨ φ`, and `unsat ⟹ φ unsatisfiable over D` | 212 formulas × 48 assignments | cross-validated against brute force |
| 5 | Prover **decidability** on a fully-bounded signature: never returns `unknown`, and agrees with brute force both ways | same | same |
| 6 | The DAG set is a **partition** of the rule set — covering, pairwise disjoint, non-empty | a real 832-rule run | direct |

## What these do and do not establish

They are statements about the *implementation against its specification*, over
bounded domains. Theorems 4 and 5 hold **for the signature enumerated**; they do
not extend to unbounded reals, open intervals, or free text, where the prover is
designed to return `unknown` rather than guess. Theorem 6 is checked on one real
run, not proved for all inputs.

None of them says anything about whether a rule is a **correct reading of the
regulation**. That is not a mathematical property and cannot be one.
