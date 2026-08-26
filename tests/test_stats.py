from bench.stats import clustered_bootstrap, spearman_correlation


def _rows():
    return [{"model_id": f"m{i}", "afs": i / 10, "oe": i / 10, "system": "ours", "run_id": "1"} for i in range(1, 9)]


def test_spearman_handles_ties():
    assert spearman_correlation([1, 1, 2], [1, 2, 2]) == 0.5


def test_clustered_bootstrap_keeps_model_cluster_unit():
    report = clustered_bootstrap(_rows(), replicates=100, seed=7)
    assert report["estimand"] == "spearman(afs,oe)"
    assert report["clusters"] == 8
    assert report["status"] == "valid"


def test_few_clusters_are_underpowered():
    rows = [{"model_id": f"m{i}", "afs": i / 5, "oe": i / 5} for i in range(1, 5)]
    assert clustered_bootstrap(rows, replicates=100)["status"] == "underpowered"
