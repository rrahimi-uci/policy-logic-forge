"""Unit tests for the OpenAI-backed LLM client wrapper."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import allure
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.llm_client import LLMClient, LLMCompletionError, create_llm_client  # noqa: E402
from utils import llm_client as lc  # noqa: E402


@allure.feature("Pipeline LLM client")
@allure.story("Cost estimation")
class TestEstimateCost:
    @allure.title("Known model is priced from its table entry")
    def test_known_model(self):
        cost = lc._estimate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost == pytest.approx(2.50 + 10.00)

    @allure.title("Dated/suffixed model resolves to the LONGEST matching prefix")
    def test_longest_prefix_wins(self):
        # gpt-4o-mini-* must price as gpt-4o-mini (0.15/0.60), NOT gpt-4o (2.50/10).
        mini = lc._estimate_cost("gpt-4o-mini-2024-07-18", 1_000_000, 0)
        base = lc._estimate_cost("gpt-4o-2024-08-06", 1_000_000, 0)
        assert mini == pytest.approx(0.15)
        assert base == pytest.approx(2.50)
        assert mini < base

    @allure.title("o1-mini snapshot is not priced as o1")
    def test_o1_mini_prefix(self):
        assert lc._estimate_cost("o1-mini-2024-09-12", 1_000_000, 0) == pytest.approx(1.10)
        assert lc._estimate_cost("o1", 1_000_000, 0) == pytest.approx(15.00)

    @allure.title("Unknown model returns 0.0 rather than crashing")
    def test_unknown_model(self):
        assert lc._estimate_cost("some-future-model", 1000, 1000) == 0.0
        assert lc._estimate_cost(None, 1000, 1000) == 0.0

    @allure.title("GPT-5.6 Luna uses its configured input/output rates")
    def test_gpt56_luna_cost(self):
        assert lc._estimate_cost("gpt-5.6-luna", 1_000_000, 1_000_000) == pytest.approx(1.40)


@allure.feature("Pipeline LLM client")
@allure.story("Reasoning-model detection")
class TestIsReasoningModel:
    @pytest.mark.parametrize("model,expected", [
        ("o1", True), ("o1-mini", True), ("o3-mini", True), ("o4-mini", True),
        ("gpt-5.6-luna", True), ("gpt-5", True),
        ("gpt-4o", False), ("gpt-4o-mini", False), ("gpt-4.1", False),
        ("", False), (None, False),
    ])
    @allure.title("is_reasoning_model({model}) == {expected}")
    def test_classification(self, model, expected):
        assert LLMClient.is_reasoning_model(model) is expected


@allure.feature("Pipeline LLM client")
@allure.story("Chat completion parameter building")
class TestChatCompletionParams:
    def _client_with_mock(self, model):
        client = create_llm_client(api_key="sk-test", model=model)
        mock_openai = MagicMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "ok"
        resp.choices[0].finish_reason = "stop"
        resp.usage = None
        mock_openai.chat.completions.create.return_value = resp
        client._client = mock_openai
        return client, mock_openai

    @allure.title("Default request gate uses the doubled throughput ceiling")
    def test_default_request_gate_matches_doubled_profile(self, monkeypatch):
        monkeypatch.delenv("KG_LLM_CONCURRENCY", raising=False)
        client = LLMClient(api_key="sk-test", model="gpt-4o")

        assert client._request_gate._value == 32

    @allure.title("Client uses the configured GPT-5.6 Luna default")
    def test_default_model(self):
        client = create_llm_client(api_key="sk-test")
        assert client.model == "gpt-5.6-luna"

    @allure.title("Non-reasoning models send temperature + max_tokens")
    def test_standard_model_params(self):
        client, mock = self._client_with_mock("gpt-4o-mini")
        client.chat_completion([{"role": "user", "content": "hi"}], temperature=0.3, max_tokens=100)
        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 100
        assert "max_completion_tokens" not in kwargs
        assert "reasoning_effort" not in kwargs

    @allure.title("Reasoning models drop temperature and use max_completion_tokens")
    def test_reasoning_model_params(self):
        client, mock = self._client_with_mock("o3-mini")
        client.chat_completion(
            [{"role": "user", "content": "hi"}],
            temperature=0.3, max_tokens=100, reasoning_effort="high",
        )
        kwargs = mock.chat.completions.create.call_args.kwargs
        assert "temperature" not in kwargs
        assert kwargs["reasoning_effort"] == "high"
        assert kwargs["max_completion_tokens"] >= 32768

    @allure.title("Reasoning completion budget can be bounded for compact runs")
    def test_reasoning_completion_budget_env_cap(self, monkeypatch):
        client, mock = self._client_with_mock("gpt-5.6-luna")
        monkeypatch.setenv("KG_REASONING_MAX_COMPLETION_TOKENS", "4096")
        client.chat_completion(
            [{"role": "user", "content": "hi"}],
            max_tokens=1024, reasoning_effort="medium",
        )
        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 4096

    @allure.title("Default pipeline cap bounds high-reasoning completions")
    def test_reasoning_completion_budget_default_pipeline_cap(self, monkeypatch):
        client, mock = self._client_with_mock("gpt-5.6-luna")
        monkeypatch.setenv("KG_REASONING_MAX_COMPLETION_TOKENS", "24576")
        client.chat_completion(
            [{"role": "user", "content": "extract compact JSON"}],
            max_tokens=32768,
            reasoning_effort="high",
        )
        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 24576

    @allure.title("get_text_response returns the message content")
    def test_get_text_response(self):
        client, _ = self._client_with_mock("gpt-4o-mini")
        assert client.get_text_response([{"role": "user", "content": "hi"}]) == "ok"

    @allure.title("Lazy client is not constructed until first call")
    def test_lazy_client(self):
        # Constructing with no key must not raise (no OpenAI() built yet).
        client = create_llm_client(model="gpt-4o-mini")
        assert client._client is None

    @allure.title("Provider failure metadata survives the wrapper")
    def test_completion_error_preserves_original_status(self):
        client, mock = self._client_with_mock("gpt-4o-mini")
        provider_error = RuntimeError("connection reset by peer")
        provider_error.status_code = 503
        mock.chat.completions.create.side_effect = provider_error

        with pytest.raises(LLMCompletionError) as caught:
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=8)

        assert caught.value.status_code == 503
        assert caught.value.error_type == "RuntimeError"
        assert caught.value.__cause__ is provider_error
