from bench.power import approximate_power, build_power_curve


def test_power_curve_is_monotone_for_more_clusters():
    low = approximate_power(8, 0.6)
    high = approximate_power(32, 0.6)
    assert high > low


def test_power_report_is_explicitly_non_claiming():
    report = build_power_curve([8, 16], [0.4, 0.6])
    assert report["claimable"] is False
    assert len(report["points"]) == 4
