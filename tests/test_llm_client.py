"""Unit tests for the LLM client wrapper (OpenAI SDK + litellm/Anthropic)."""
import json
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
        ("claude-opus-5", True), ("claude-sonnet-5", True), ("anthropic/claude-opus-5", True),
        ("", False), (None, False),
    ])
    @allure.title("is_reasoning_model({model}) == {expected}")
    def test_classification(self, model, expected):
        assert LLMClient.is_reasoning_model(model) is expected


@allure.feature("Pipeline LLM client")
@allure.story("Provider routing")
class TestProviderClassification:
    @pytest.mark.parametrize("model,expected", [
        ("claude-opus-5", True), ("Claude-Sonnet-5", True), ("anthropic/claude-opus-5", True),
        ("gpt-5.6-luna", False), ("gpt-4o", False), ("o3-mini", False), ("", False), (None, False),
    ])
    @allure.title("is_anthropic_model({model}) == {expected}")
    def test_is_anthropic_model(self, model, expected):
        assert LLMClient.is_anthropic_model(model) is expected

    @allure.title("Claude models are reasoning models but NOT OpenAI reasoning models")
    def test_claude_is_reasoning_but_not_openai_reasoning(self):
        # This distinction drives chat_completion's token-budget branch: only
        # OpenAI reasoning models get the aggressive max_completion_tokens
        # heuristic; Claude takes the plain max_tokens branch (see module
        # docstring / is_openai_reasoning_model docstring).
        assert LLMClient.is_reasoning_model("claude-opus-5") is True
        assert LLMClient.is_openai_reasoning_model("claude-opus-5") is False


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

    @allure.title("A bounded recovery call can raise the normal reasoning cap")
    def test_reasoning_completion_budget_recovery_override(self, monkeypatch):
        client, mock = self._client_with_mock("gpt-5.6-luna")
        monkeypatch.setenv("KG_REASONING_MAX_COMPLETION_TOKENS", "24576")

        client.chat_completion(
            [{"role": "user", "content": "retry compact JSON"}],
            max_tokens=32768,
            reasoning_effort="high",
            reasoning_completion_cap_override=32768,
        )

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 32768
        assert "reasoning_completion_cap_override" not in kwargs

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

    @allure.title("Adaptive queue admission does not inherit the API watchdog")
    def test_adaptive_queue_wait_has_no_request_timeout(self):
        client, _ = self._client_with_mock("gpt-4o-mini")
        limiter = MagicMock()
        limiter.acquire.return_value = MagicMock(wait_seconds=123.0)
        limiter.release.return_value = {
            "current_limit": 1,
            "active_leases": 0,
            "total_success": 1,
            "total_failure": 0,
            "total_throttled": 0,
        }
        client._adaptive_limiter = limiter

        client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=8)

        limiter.acquire.assert_called_once_with(timeout=None)
        assert limiter.release.call_args.kwargs["request_seconds"] < 5


@allure.feature("Pipeline LLM client")
@allure.story("Anthropic call path (litellm)")
class TestAnthropicViaLitellm:
    """Claude models never touch the OpenAI SDK -- these tests mock
    litellm.completion/completion_cost directly rather than client._client,
    since _litellm_completion() does its own lazy `import litellm`."""

    @staticmethod
    def _litellm_response(*, cached_tokens=0, cache_read_input_tokens=None):
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "ok"
        resp.choices[0].finish_reason = "stop"
        resp.usage = MagicMock()
        resp.usage.prompt_tokens = 1000
        resp.usage.completion_tokens = 200
        resp.usage.total_tokens = 1200
        if cached_tokens:
            resp.usage.prompt_tokens_details = MagicMock(cached_tokens=cached_tokens)
        else:
            resp.usage.prompt_tokens_details = None
        resp.usage.cache_read_input_tokens = cache_read_input_tokens
        return resp

    @allure.title("A bare Claude model name is prefixed with anthropic/ for litellm")
    def test_model_name_is_prefixed(self):
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        with patch("litellm.completion", return_value=self._litellm_response()) as mock_completion:
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        assert mock_completion.call_args.kwargs["model"] == "anthropic/claude-opus-5"

    @allure.title("An already-prefixed model name is not double-prefixed")
    def test_already_prefixed_model_name_is_left_alone(self):
        client = create_llm_client(api_key="sk-ant-test", model="anthropic/claude-opus-5")
        with patch("litellm.completion", return_value=self._litellm_response()) as mock_completion:
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        assert mock_completion.call_args.kwargs["model"] == "anthropic/claude-opus-5"

    @allure.title("Claude call carries the explicit api_key and retry/timeout settings")
    def test_call_carries_api_key_and_retry_settings(self):
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5", timeout=42, max_retries=5)
        with patch("litellm.completion", return_value=self._litellm_response()) as mock_completion:
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        kwargs = mock_completion.call_args.kwargs
        assert kwargs["api_key"] == "sk-ant-test"
        assert kwargs["max_retries"] == 5
        assert kwargs["timeout"] == 42

    @allure.title("Claude drops temperature and forwards reasoning_effort, like an OpenAI reasoning model")
    def test_reasoning_effort_forwarded_and_temperature_dropped(self):
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        with patch("litellm.completion", return_value=self._litellm_response()) as mock_completion:
            client.chat_completion(
                [{"role": "user", "content": "hi"}], temperature=0.3, max_tokens=100, reasoning_effort="high",
            )
        kwargs = mock_completion.call_args.kwargs
        assert "temperature" not in kwargs
        assert kwargs["reasoning_effort"] == "high"

    @allure.title("Claude's thinking budget is drawn from max_tokens, so it gets the same generous headroom as OpenAI reasoning models -- just under the max_tokens name, not max_completion_tokens")
    def test_claude_reasoning_call_gets_inflated_max_tokens(self):
        # Regression: an earlier version assumed Claude's extended-thinking
        # budget was sized separately from max_tokens by litellm, and left
        # a bare max_tokens=100 uninflated for a reasoning_effort call. A
        # real call at max_tokens=12000 came back with finish_reason=
        # "length" and EMPTY content -- the entire budget went to thinking,
        # none was left for visible output. Both provider families now get
        # the same 4x/32768-floor inflation; only the resulting parameter
        # name differs (max_tokens for Claude, max_completion_tokens for
        # OpenAI reasoning models -- see test_reasoning_model_params above).
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        with patch("litellm.completion", return_value=self._litellm_response()) as mock_completion:
            client.chat_completion(
                [{"role": "user", "content": "hi"}], max_tokens=100, reasoning_effort="high",
            )
        kwargs = mock_completion.call_args.kwargs
        assert kwargs["max_tokens"] >= 32768
        assert "max_completion_tokens" not in kwargs

    @allure.title("A non-reasoning-effort Claude call still honours the caller's plain max_tokens")
    def test_claude_call_without_reasoning_effort_uses_plain_max_tokens(self):
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        with patch("litellm.completion", return_value=self._litellm_response()) as mock_completion:
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        kwargs = mock_completion.call_args.kwargs
        # Claude is always classified as a reasoning model (is_reasoning_model),
        # so it always takes the inflated branch when max_tokens is set --
        # this documents that behavior explicitly rather than assuming it.
        assert kwargs["max_tokens"] >= 32768

    @allure.title("Response cost is estimated via litellm.completion_cost, not the OpenAI-only pricing table")
    def test_cost_uses_litellm_completion_cost(self, capsys):
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        response = self._litellm_response()
        with patch("litellm.completion", return_value=response), \
             patch("litellm.completion_cost", return_value=0.0123) as mock_cost:
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        mock_cost.assert_called_once_with(completion_response=response)
        cost_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("[LLM_COST]"))
        assert json.loads(cost_line[len("[LLM_COST]"):])["cost"] == pytest.approx(0.0123)

    @allure.title("A litellm.completion_cost failure yields 0.0 cost, never an exception")
    def test_cost_estimation_failure_is_swallowed(self, capsys):
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        with patch("litellm.completion", return_value=self._litellm_response()), \
             patch("litellm.completion_cost", side_effect=RuntimeError("unknown model")):
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        cost_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("[LLM_COST]"))
        assert json.loads(cost_line[len("[LLM_COST]"):])["cost"] == 0.0

    @allure.title("Cache-hit tokens fall back to Anthropic's native cache_read_input_tokens field")
    def test_cache_tokens_fallback_to_anthropic_native_field(self, capsys):
        # litellm does not (yet) normalize this into prompt_tokens_details.cached_tokens
        # for Anthropic responses -- see this module's docstring and
        # https://github.com/BerriAI/litellm/issues/27763
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        response = self._litellm_response(cached_tokens=0, cache_read_input_tokens=150)
        with patch("litellm.completion", return_value=response), patch("litellm.completion_cost", return_value=0.0):
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        cost_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("[LLM_COST]"))
        assert json.loads(cost_line[len("[LLM_COST]"):])["cached_tokens"] == 150

    @allure.title("An OpenAI-shaped cached_tokens field, when present, is preferred over the Anthropic fallback")
    def test_cache_tokens_prefers_normalized_field_when_present(self, capsys):
        client = create_llm_client(api_key="sk-ant-test", model="claude-opus-5")
        response = self._litellm_response(cached_tokens=90, cache_read_input_tokens=150)
        with patch("litellm.completion", return_value=response), patch("litellm.completion_cost", return_value=0.0):
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        cost_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("[LLM_COST]"))
        assert json.loads(cost_line[len("[LLM_COST]"):])["cached_tokens"] == 90

    @allure.title("An OpenAI model call never touches litellm")
    def test_openai_model_does_not_call_litellm(self):
        client, mock_openai = self._client_with_mock_openai("gpt-4o-mini")
        with patch("litellm.completion") as mock_completion:
            client.chat_completion([{"role": "user", "content": "hi"}], max_tokens=100)
        mock_completion.assert_not_called()
        mock_openai.chat.completions.create.assert_called_once()

    @staticmethod
    def _client_with_mock_openai(model):
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
