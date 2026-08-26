# G0 retained-evidence gate

`scripts/validate_g0_evidence.py` is the provider-free consistency gate for
the three currently executable G0 surfaces:

- PIPE-2B's semantic rule-recall fixture and retained JSON report;
- PIPE-4's dependency-audit fixture and retained JSON report; and
- the retained IR-2 pilot manifests and their content-addressed report files.

Run it from the repository root:

```bash
.venv/bin/python scripts/validate_g0_evidence.py
```

The gate recomputes both fixture reports, checks that their status remains
`fixture_only`, and verifies the hashes and byte counts recorded in the IR-2
manifests. The older NDA pilot manifest is validated under its historical
`exploratory_pilot` shape; newer IR-2 manifests use the `ir2-census-run/1.0`
contract.

A passing gate means the retained artifacts are internally consistent. It does
not supply a licensed stratified sample, human annotations, adjudication,
sampling weights, or a full-corpus IR-2 census. PIPE-2B, PIPE-4, and IR-2
therefore remain partial until those external evidence requirements are met.
