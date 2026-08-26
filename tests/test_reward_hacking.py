from training.reward import audit_reward, compose_reward


def test_adversarial_attacks_must_score_worse_than_baseline():
    baseline = compose_reward(coverage=0.8, grounding=0.8, behavior=0.8, omission_rate=0.1)
    report = audit_reward(baseline, {"empty": {"score": 0.1}, "constant": {"score": 0.2}})
    assert report["status"] == "pass"
    assert report["claimable"] is True


def test_reward_exploit_fails_audit():
    baseline = {"score": 0.5}
    report = audit_reward(baseline, {"deletion": {"score": 0.6}})
    assert report["status"] == "fail"
    assert not report["claimable"]
