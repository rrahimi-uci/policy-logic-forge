# A2 fresh-generation preregistration

`A2` is optional from a research-scope standpoint, but its implementation
contract is now complete in-repo. A paid fresh-generation rerun still requires
explicit approval before any provider-backed execution.

If activated, the run must freeze before generation:

- the exact provider, model, reasoning effort, and decoding parameters;
- the benchmark split, release revision, and manifest hashes;
- the target estimator, equivalence margin, and invalidation rules;
- the retry, timeout, and refusal-handling policy;
- the cost ceiling and approval record; and
- the retained artifact schema and publication boundary.

The activation PR must also record:

- why the released-anchor replay in `A1B` is insufficient for the question at
  hand;
- how prompt or environment drift from the original anchor release will be
  bounded and disclosed; and
- how fresh generations will remain separated from gold or otherwise
  leakage-prone views.

Until that approval exists, `A2` remains a blocked retained-run contract rather
than an executed fresh-generation result.
