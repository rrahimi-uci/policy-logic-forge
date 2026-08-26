# Source-grounded perturbation annotation protocol

Relations are generated from source text alone. Candidate and gold artifacts
are not inputs to relation generation or annotation. Each relation carries a
source SHA-256, source span, transformation kind, and expected invariance.
Two independent annotators label the invariant flag; disagreements are
adjudicated and percent agreement/Cohen kappa are retained. A run with a
leakage canary or candidate/gold-derived relation is invalid.
