# Analysis plan

This preregistration freezes the primary instrument estimand before inspecting
instrument outcomes. The observation unit is `model × system × run`; repeated
runs are retained and model-clustered bootstrap resampling is used for
intervals.

- Primary estimand: Spearman correlation between artifact-free signal (AFS)
  and oracle execution (OE).
- Null: `H0: population rho <= 0.30`; alpha `0.05`.
- Useful signal: point estimate `rho >= 0.60` and lower clustered 95% bound
  above `0.30`.
- Bootstrap: 2,000 replicates, seed `2027`, resample model clusters with all
  associated system/run rows retained.
- Missingness: refused, failed, invalid, and underpowered runs remain in the
  manifest and are never silently removed from denominators.
- Controls: positive, random, stratified, biased, leakage-canary, and
  permutation controls. Canary access or predictive permutation controls
  invalidate the run.

The sensitivity curve in `bench/power.py` is an approximate Fisher-z planning
tool only. It is not an iid power claim and cannot replace the clustered
bootstrap report.
