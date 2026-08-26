from bench.instrument import assess_bundle


def _bundle():
    rows = [{"model_id": f"m{i}", "afs": i / 10, "oe": i / 10, "leakage_canary_accessible": False, "permuted_predictive": False} for i in range(1, 9)]
    return {"observations": rows, "controls": {name: [f"{name}-1"] for name in ("positive", "random", "stratified", "biased", "leakage_canary", "permuted")}}


def test_instrument_bundle_is_valid_with_required_controls():
    report = assess_bundle(_bundle(), bootstrap_replicates=100)
    assert report["status"] == "valid"
    assert report["claimable"] is True


def test_leakage_canary_invalidates_bundle():
    bundle = _bundle()
    bundle["observations"][0]["leakage_canary_accessible"] = True
    report = assess_bundle(bundle, bootstrap_replicates=100)
    assert report["status"] == "invalid"
    assert not report["claimable"]
