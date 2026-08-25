# A1B anchor replay and aggregation recipe

## Pinned release

Replay the upstream evaluator from commit
`6a4844fb235d4f958d0810bba7089a2e9078099e` of
`https://github.com/opengov-lab/legal-text-to-decision-model`. Do not copy the
upstream source, gold, generated, or result artifacts into this repository.
Use a temporary checkout and retain only hashes, counts, and aggregate outputs.

```bash
tmp_root="$(mktemp -d)"
git clone https://github.com/opengov-lab/legal-text-to-decision-model "$tmp_root/anchor"
git -C "$tmp_root/anchor" checkout 6a4844fb235d4f958d0810bba7089a2e9078099e
python -m venv "$tmp_root/venv"
"$tmp_root/venv/bin/pip" install -r "$tmp_root/anchor/requirements.txt"
```

The upstream evaluator currently needs a NumPy compatibility shim before
importing GraKeL. Run it in a small wrapper (as the upstream entry point does):

```bash
cat >"$tmp_root/run_replay.py" <<'PY'
import numpy as np
if not hasattr(np, "ComplexWarning"):
    np.ComplexWarning = DeprecationWarning
if not hasattr(np, "string_"):
    np.string_ = np.bytes_
if not hasattr(np, "unicode_"):
    np.unicode_ = np.str_
from evaluation.run_evaluation import run_evaluation
from pathlib import Path

run_evaluation(
    Path("gold_models"),
    Path("generated_models"),
    Path("/tmp/anchor-replay-metrics.csv"),
)
PY
(cd "$tmp_root/anchor" && "$tmp_root/venv/bin/python" "$tmp_root/run_replay.py")
```

Compare the replay with the released CSV without treating representation
differences as scientific mismatches:

```bash
.venv/bin/python -m bench.anchor_replay \
  --released "$tmp_root/anchor/results/metrics.csv" \
  --replayed /tmp/anchor-replay-metrics.csv \
  --output results/aggregates/a1_replay.json
```

The command returns zero only for an exact semantic match. A non-zero return
with `status: "mismatch_reported"` is an expected, retained outcome when the
upstream release does not reproduce under its pinned evaluator. It must not be
changed by hand to make the headline result agree.

## Observation and aggregation contract

The row is one `activity × condition × run × dmn_type` generation. The pinned
release contains 95 activities, four conditions (`baseline`, `srl`,
`conditions`, `srl_conditions`), and five runs, for 1,900 rows. The validator
rejects duplicate or missing keys before comparing metrics.

For outcome aggregates, include only rows with
`generation_success == true` and `outcome_testable == true`. Report both:

- `row_macro_agreement`: the unweighted mean of per-generation agreements;
- `test_input_weighted_agreement`: total agreed test inputs divided by total
  test inputs.

These are descriptive replay summaries, not a confidence interval or a claim
that the historical paper's headline aggregation has been recovered. The
retained report records the release/replay SHA-256 digests, row-level mismatch
fields, and representative mismatch examples so an owner can inspect the
upstream cause before any paper number is reused.
