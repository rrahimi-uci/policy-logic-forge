# Aggregate release boundary

`bench/run_bundle.py` validates retained benchmark bundles before an aggregate
is released. Every bundle must include a validated run manifest and
`requirements-lock.txt`; every listed artifact is checked for path safety,
byte size, and SHA-256 equality.

Release is an explicit allowlist, not an inference from a directory. The
allowlist may contain `aggregate_only` and `redistributable` artifacts, but it
must reject source documents, gold labels, raw outputs, restricted files, and
local-only artifacts. Failed and refused run records remain in the run
manifest even when they have no publishable output.

This directory contains aggregate metadata only. It does not authorize
redistribution of any benchmark corpus or gold artifact, and no benchmark run
bundle is claimed or retained by this contract implementation.
