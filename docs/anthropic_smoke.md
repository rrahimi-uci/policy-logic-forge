# Anthropic (Claude) provider smoke run

A provider-backed, one-document smoke test of `--provider anthropic`
(`feat/litellm-anthropic-support` / PR #118), run with a real
`ANTHROPIC_API_KEY` against Anthropic's live API — not mocked, not a
benchmark result or corpus-coverage claim. Mirrors
[`docs/pipeline_smoke.md`](pipeline_smoke.md)'s existing OpenAI smoke
pattern so the two are directly comparable. The source file and all
pipeline outputs remain local-only and are gitignored.

## Configuration verified

- provider: `anthropic` (`--provider anthropic`)
- model: `claude-opus-5` (config default, no override)
- reasoning effort: `high`
- optimizer skipped (`--skip-optimize`); no optimizer/grounding quality claim
- one deterministic privacy-policy source file (`1017_sci-news.com.txt`,
  3.3 KB), one pilot extraction batch, one worker

## Reproduction command

From the repository root, with `ANTHROPIC_API_KEY` set in `.env`:

```bash
.venv/bin/python cli/extract.py \
  --dir /path/to/one-file-privacy-policy-directory \
  --domain privacy_policy \
  --batch-name anthropic-smoke-20260901 \
  --target-rules 1 \
  --pilot-batch-limit 1 \
  --workers 1 \
  --skip-optimize \
  --provider anthropic
```

## Observed result

**Stage 01/12 (Document Organizer): PASS.** Real call to `claude-opus-5`,
35.4s, 4,727 tokens, $0.085. Confirms the full real call path end to end:
config resolves the right model/key for the selected provider, the
subprocess environment correctly propagates `KG_PROVIDER=anthropic` to
every agent, `response_format={"type":"json_object"}` was honored (valid
JSON came back), the `[LLM_COST]` line was emitted and captured correctly
by `run_metrics.json`, and litellm's usage object populated
`prompt_tokens_details.cached_tokens` for Anthropic directly (a field this
pipeline's own code has a documented fallback for, in case a future
litellm version regresses it — see `utils/llm_client.py`'s docstring).

**Stage 02/12 (Entity Extractor): FAIL, closed correctly, not a wiring
bug.** `agent_02`'s grounding validator requires every extracted entity to
carry a non-empty `source_evidence` list with a verbatim quote from the
source corpus. Across two independent real runs — the default 2-attempt
self-correction budget, then a repeat with `KG_ENTITY_EVIDENCE_ATTEMPTS=4`
giving Claude twice as many chances with increasingly explicit correction
feedback each time — the **exact same 5 entity types** failed the
**exact same way**, every single time (22 findings, unchanged):

```text
entity_types.FIRST_PARTY.source_evidence is required
entity_types.USER.source_evidence is required
entity_types.INFORMATION_TYPE.source_evidence is required
entity_types.COLLECTION_PRACTICE.source_evidence is required
entity_types.THIRD_PARTY.source_evidence is required
```

This is not intermittent model variance — a 4x retry budget with targeted
correction feedback produced an identical result. The likely cause:
`FIRST_PARTY`, `USER`, `INFORMATION_TYPE`, `COLLECTION_PRACTICE`, and
`THIRD_PARTY` are the domain's five predefined, schema-level entity
*categories* (see `domain-prompts/privacy_policy/entity_extraction.txt`,
e.g. `FIRST_PARTY — The operator of the site that collects the data`), not
document-specific named instances. Claude appears to consistently treat
these as category labels with no single canonical source quote and omits
`source_evidence` for them rather than attaching one, where GPT models
(the prompt's originally-tuned target) apparently do attach something. The
other 6 of 11 extracted entities (document-specific named instances) never
triggered this issue in either run.

This is a real, reproducible content/prompt-compatibility gap on this
specific extraction step, not a defect in the provider-selection, API
client, or CLI wiring added in PR #118 — those are confirmed working by
Stage 01's clean pass and by 6 of 11 Stage 02 entities extracting with
valid evidence on every attempt. Fixing Stage 02 for Claude specifically
would mean either relaxing `validate_catalog_evidence` for schema-level
category entities or reinforcing the extraction prompt — a deliberate
content/schema decision, not made in this smoke test.

## Cost of this smoke test

Two real runs while diagnosing: $0.404 (full pipeline attempt, stage 1
pass + stage 2 fail after 2 attempts) + $0.734 (stage-2-only retry with 4
attempts) = **$1.14 total**, entirely within Stages 01–02; no optimizer,
readiness, remediation, or grounding calls were made (`--skip-optimize`,
and the run never reached Stage 09+).
