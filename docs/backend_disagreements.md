# DMN backend cross-check protocol

`bench/dmn_engine_harness.py` defines the BE-4 boundary between this
repository and a pinned third-party DMN runtime. The repository does not
vendor an engine or treat the local reference evaluator as an independent
engine.

## Adapter contract

The harness invokes an engine adapter as an argv command. It sends one
newline-delimited JSON request per case on stdin and expects exactly one
newline-delimited JSON response per case on stdout. A request contains:

- `protocol`: `dmn-engine-crosscheck/1.0`;
- `case_id`, `table_id`, and JSON `inputs`;
- the emitted DMN 1.3 document as `dmn_xml` and its `dmn_sha256`.

Each response must repeat the same `protocol` version, `case_id`, `table_id`,
and `dmn_sha256` from its request, plus a status in
`matched`/`no_match`/`unknown`/`refused`, `outputs`, `matched_rule_ids`, and
`unknown_rule_ids`. Diagnostic text is retained separately and is not used to
declare behavioral agreement. The digest and table echo prevent an adapter
from returning a result computed for a different emitted artifact or table.

## Evidence and status

The run must include `engine_id`, `engine_version`, `source`, `revision`, and
`license`, plus either a SHA-256 of the engine artifact or a pinned
`sha256:<64-hex>` container digest.
Without a command the result is `unrun`; a missing executable is also
`unrun`. Adapter protocol failures are `invalid`, a timeout is `timeout`, and
any behavioral mismatch is `disagreement`. Only `completed` with all cases
agreeing is marked `claimable`.

The report compares the reference evaluator and the engine on status, output
map, matched rule IDs, and unknown rule IDs. It does not turn structural XML
validation into engine evidence, and it does not hide failed, refused, or
unrun cases. Adapter commands must receive engine metadata through a reviewed
configuration; secrets must not be placed in command arguments or retained
reports.

The harness also rejects non-positive, non-finite, or boolean timeout values
before launching an adapter. The current repository has no pinned third-party
engine installed, so BE-4 is implemented as an executable protocol harness
and remains `partial` until an approved engine job supplies the required
metadata and run artifact.
