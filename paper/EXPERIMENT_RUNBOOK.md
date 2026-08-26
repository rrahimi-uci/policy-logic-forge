# LEXEC experiment runbook

This runbook turns the paper plan into an executable release checklist. It is
part of the paper package, but it does not turn an absent observation into a
result. Every run must retain its manifest, input/output hashes, protocol
version, status, denominator, and exclusion reasons.

## Local, provider-free gates

Run these commands from the repository root before every paper freeze:

```bash
.venv/bin/python scripts/validate_neurips_plan.py --run-complete
.venv/bin/python scripts/validate_g0_evidence.py
.venv/bin/python scripts/validate_research_artifacts.py
.venv/bin/python -m pytest -q
paper/scripts/build_paper.sh
.venv/bin/python paper/scripts/validate_paper.py --source paper/main.tex --build-dir paper/build --check-build
```

The fixture evaluators are contract tests only:

```bash
.venv/bin/python scripts/rule_recall.py
.venv/bin/python scripts/dependency_audit.py
.venv/bin/python scripts/lowering_mutation.py --check
```

Their `fixture_only` status must remain visible in the generated paper
manifest. Do not replace the fixtures with hand-edited numbers.

## Evidence gates

| Gate | Inputs supplied by the study owner | Existing command/contract | Required retained output |
| --- | --- | --- | --- |
| M1 / PIPE-2B | Licensed stratified rule frame, explicit negatives, two independent annotator exports, adjudication | `scripts/rule_recall.py --fixture <frame> --output <artifact>` | Weighted precision/recall, Wilson or preregistered interval, IAA, exception/evidence error taxonomy |
| PIPE-4 | Same frame with typed positive and negative dependency edges | `scripts/dependency_audit.py --fixture <frame> --output <artifact>` | Edge precision/recall, typed-edge agreement, negative-edge denominator, adjudication log |
| M2 / IR-2 | Frozen full-corpus graph manifest and source license | `scripts/corpus_census.py <graphs> --run-label <id> --scope-note <note> --manifest-out <path>` | Type/operator/exception/table distributions, supported/refused/ignored denominators, refusal reasons |
| M3 / BE-4 | Pinned external DMN engine, conformance cases, generated models, environment lock | `tests/test_dmn_engine_crosscheck.py` plus the engine command recorded in the run manifest | Paired traces, agreement, timeout/unknown/refusal counts, root-caused disagreements |
| M4 / A1 | Pinned upstream checkout and released generated metrics/models | `bench/anchor_replay.py --released <path> --replayed <path> --output <artifact>` | Release audit, exact replay rows, mismatch taxonomy, corrected or explicitly unusable anchor |
| M5 / J1-J1B | Frozen source units, artifact-free query packet, baseline/model configurations | `bench/harness.py` and `bench/exception_reading.py` contracts | All model × system × run records, refusals, costs, outcome equivalence, exception readings |
| M6 / G3 | Preregistered human labels and positive/negative/permutation/leakage controls | `bench/instrument.py`, `results/aggregates/g3_instrument.json` | Model-clustered estimate, uncertainty, validity class, control results, reviewer protocol |
| M7 / BENCH-1B | ContractNLI license, supported-boundary split, independent assumption review | `bench/adapters/contract_nli.py`, `utils/assumptions.py` | Separate transfer result, unsupported denominator, assumption agreement |
| M8 / CEGIR | Frozen baseline, source-preserving edits, witnesses, deletion/no-op ablations | `compiler/cegir.py` | Paired repair gain, witness validity, provenance regression checks |
| M9 / RL | Approved provider/GPU budget and disjoint train/reward/audit/test data | `training/reward.py`, `training/frontier.py` | Held-out reward audit, exploit report, failed runs, cost/frontier table |

## Claim promotion rules

An artifact can move from `unrun` or `blocked` to `measured` only when all
declared inputs are available and the validator passes. `fixture_only`,
`exploratory`, `mismatch_reported`, `underpowered`, and `invalid` artifacts are
never positive evidence for a population claim. A changed model, prompt,
corpus, schema, engine, or estimator creates a new run ID. The paper generator
reads retained artifacts and fails if their source hashes or summary counts do
not agree.

## External access checklist

Before running a blocked gate, record the data-use agreement, license, privacy
review, annotator compensation and instructions, IRB/ethics determination,
provider/model identifier, compute budget, and deletion date. Restricted data
must remain outside Git; only metadata, hashes, sanitized examples, and derived
aggregates may enter the release. If any item is unavailable, retain an
explicitly non-claiming status and narrow the paper rather than substituting a
proxy.
