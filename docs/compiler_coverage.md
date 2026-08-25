# Compiler/backend coverage gate

CI enforces at least 85% line coverage for the executable compiler/backend
surface:

- LExec IR lowering and validation (`utils/lexec_ir.py`)
- the bounded FEEL evaluator (`utils/feel.py`)
- bounded SMT queries and policy proofs (`utils/smt.py`)
- DMN construction and XML validation (`utils/dmn_builder.py`, `utils/dmn_emit.py`)
- the optional DMN engine cross-check harness (`bench/dmn_engine_harness.py`)

Run the same gate locally with:

```bash
python -m coverage erase
python -m coverage run -m pytest -q
python -m coverage report
```

This is intentionally a scoped compiler/backend contract. It is not a claim
that the unrelated provider-backed agent orchestration modules have 85%
coverage; those modules require a separate evaluation and fixture strategy.
