from training.coverage_inventory import build_inventory, coverage_score
from training.held_out_signals import build_signals
from training.reward import compose_reward
from training.frontier import build_frontier


def test_inventory_and_held_out_signals_are_independent():
    inventory = build_inventory([{"unit_id": "u1", "category": "rule"}, {"unit_id": "u2", "required": False}])
    assert coverage_score(inventory, ["u1"]) == 1
    signals = build_signals([{"case_id": "c1", "grounding": 1, "behavior": 0.5}])
    assert signals["self_generated_reward"] is False


def test_reward_is_composed_from_explicit_components():
    result = compose_reward(coverage=1, grounding=0.8, behavior=0.7, omission_rate=0.1)
    assert result["source_grounded"] is True
    assert 0 < result["score"] < 1


def test_frontier_is_provider_gated():
    blocked = build_frontier([])
    assert blocked["status"] == "blocked"
    completed = build_frontier([{"coverage": 1, "grounding": 1, "behavior": 1, "omission_rate": 0, "model_size": 1}], authorization=True)
    assert completed["claimable"] is True
