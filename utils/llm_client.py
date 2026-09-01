"""
LLM Client — OpenAI SDK for OpenAI models, litellm for everything else.

Provides a consistent chat-completion interface for the pipeline, with support
for both standard chat models (gpt-4o, gpt-4o-mini, …) and reasoning models
(o1/o3/o4, gpt-5.x), plus token/cost accounting emitted for the UI runner.

Two call paths, selected purely by `self.model`'s name (see
`is_anthropic_model`), not a separate provider flag:

- OpenAI models: the official `openai` SDK, exactly as before this module
  supported a second provider — same client, same TCP-keepalive transport,
  same watchdog thread. Zero behavior change for existing OpenAI runs.
- Anthropic (Claude) models: routed through `litellm.completion()`, which
  accepts and returns the same OpenAI-shaped request/response, so the rest of
  this module (usage/cost tracking, error handling, the watchdog wrapper)
  applies unchanged. `reasoning_effort` is passed straight through; litellm
  translates it into Claude's own extended-thinking controls (the exact
  mechanism is Claude-generation-dependent — see
  https://docs.litellm.ai/docs/providers/anthropic_effort).

Known gap, worth knowing about rather than silently trusting the number: as
of writing, litellm does not normalize Anthropic's `cache_read_input_tokens`
into the OpenAI-shaped `usage.prompt_tokens_details.cached_tokens` field
(https://github.com/BerriAI/litellm/issues/27763). This module reads the
Anthropic-native field directly as a fallback so cache-hit tracking still
works, but confirm against a real response if precision matters here.

Corrected assumption, worth knowing about because it was wrong once
already: Claude's extended-thinking tokens are NOT a separate allowance on
top of `max_tokens` — they're drawn from the same ceiling as the visible
completion (Anthropic's own API semantics for the legacy budget_tokens
mechanism). An earlier version of this module assumed otherwise and left
Claude's `max_tokens` uninflated; confirmed via a real call
(`max_tokens=12000`, `reasoning_effort="high"`) that came back with
`finish_reason="length"` and empty content — the entire budget went to
thinking. Both provider families now get the same generous 4x/32768-floor
headroom in `chat_completion`; only the resulting parameter name differs.
"""

import json
import os
import re
import sys
import threading
import time
from typing import Dict, Any, List, Mapping, Optional

from openai import OpenAI

from utils.adaptive_limiter import AdaptiveRequestLimiter


class LLMCompletionError(Exception):
    """Preserve provider failure metadata across the pipeline boundary.

    Agents intentionally catch a normal ``Exception`` so this remains
    backwards-compatible, but retaining the original error/status lets retry
    and backpressure policy distinguish transport failures from prompt or
    validation failures instead of parsing a lossy string wrapper.
    """

    def __init__(self, message: str, *, original: BaseException) -> None:
        super().__init__(message)
        self.original = original
        self.status_code = getattr(original, "status_code", None)
        self.error_type = type(original).__name__


def _build_keepalive_http_client(timeout):
    """Build an httpx client with TCP keep-alive enabled.

    Without keep-alive, a connection that dies silently — the machine sleeps,
    a NAT/router drops the flow, the peer vanishes — leaves a blocking socket
    read parked in ``poll()`` indefinitely, well past the SDK's own timeout.
    With keep-alive the OS probes the idle connection and surfaces the dead
    peer (here within ~2 min: idle 60s, then 4 probes 15s apart), so the read
    fails fast and the SDK can retry or error instead of hanging forever.

    Returns ``None`` (so the SDK uses its default client) if httpx or the
    needed socket options aren't available — keeping this strictly best-effort.
    """
    try:
        import socket
        import httpx
    except Exception:
        return None

    opts = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    # macOS uses TCP_KEEPALIVE for the idle time; Linux uses TCP_KEEPIDLE.
    # Whichever exists is applied; absent constants are simply skipped.
    for const, value in (
        ("TCP_KEEPALIVE", 60),
        ("TCP_KEEPIDLE", 60),
        ("TCP_KEEPINTVL", 15),
        ("TCP_KEEPCNT", 4),
    ):
        num = getattr(socket, const, None)
        if num is not None:
            opts.append((socket.IPPROTO_TCP, num, value))

    try:
        connect = min(30, timeout) if timeout else 30
        return httpx.Client(
            timeout=httpx.Timeout(timeout, connect=connect),
            transport=httpx.HTTPTransport(retries=0, socket_options=opts),
        )
    except Exception:
        # Older httpx without socket_options support, etc. — fall back cleanly.
        return None


# Approximate OpenAI pricing in USD per 1M tokens (input, output). Used only to
# emit a best-effort cost estimate for the UI; unknown models report cost 0 but
# still report token usage. Update as pricing changes.
_PRICING_PER_1M = {
    "gpt-4o":       (2.50, 10.00),
    "gpt-4o-mini":  (0.15, 0.60),
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "o1":           (15.00, 60.00),
    "o1-mini":      (1.10, 4.40),
    "o3":           (2.00, 8.00),
    "o3-mini":      (1.10, 4.40),
    "o4-mini":      (1.10, 4.40),
    "gpt-5.6-luna": (0.20, 1.20),
}


def _get_config_value(getter_name: str, fallback):
    """Safely get a config value, returning fallback if config is not available."""
    try:
        from utils.config import get_config
        config = get_config()
        return getattr(config, getter_name)()
    except Exception:
        return fallback


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Best-effort USD cost estimate; 0.0 when the model's pricing is unknown."""
    key = (model or "").lower()
    rates = _PRICING_PER_1M.get(key)
    if not rates:
        # Try a prefix match (e.g. "gpt-4o-2024-08-06" -> "gpt-4o"). Match the
        # LONGEST prefix first so "gpt-4o-mini-..." resolves to "gpt-4o-mini",
        # not the pricier "gpt-4o".
        for name, r in sorted(_PRICING_PER_1M.items(), key=lambda kv: -len(kv[0])):
            if key.startswith(name):
                rates = r
                break
    if not rates:
        return 0.0
    in_rate, out_rate = rates
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000


class LLMClient:
    """Unified chat-completion client. OpenAI models use the OpenAI SDK
    directly; Claude models are routed through litellm -- see this module's
    docstring and `is_anthropic_model`."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
        timeout: int = None,
        max_retries: int = None,
        concurrency: int = None,
    ):
        """
        Initialize the client.

        Args:
            api_key: Provider API key (defaults to config / OPENAI_API_KEY or
                ANTHROPIC_API_KEY env var, chosen by whether `model` is a
                Claude model -- see `is_anthropic_model`).
            model: Model identifier (e.g. 'gpt-4o', 'o3-mini', 'gpt-5.6-luna').
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts (handled by the SDK).
        """
        self.model = model or _get_config_value('get_default_model', 'gpt-5.6-luna')
        self.timeout = timeout if timeout is not None else _get_config_value('get_timeout', 300)
        self.max_retries = max_retries if max_retries is not None else _get_config_value('get_max_retries', 3)

        # Hard watchdog margin (seconds) added on top of the SDK's own worst-case
        # (timeout × attempts). The watchdog only ever fires when the socket-level
        # timeout fails to — e.g. a connection killed mid-flight by a machine sleep.
        # Keep the default bounded for long-running 40-worker runs while allowing
        # operators to tune it with the same environment-based configuration path.
        try:
            self.watchdog_margin = max(0.0, float(os.getenv("KG_LLM_WATCHDOG_MARGIN", "30")))
        except (TypeError, ValueError):
            self.watchdog_margin = 30.0

        self._api_key = api_key
        self._client: Optional[OpenAI] = None
        # Worker pools in the pipeline can be intentionally large (for example
        # MAX_WORKERS=80), but allowing every worker to open an API request at
        # once causes connection-pool exhaustion and transient rate-limit
        # failures.  Keep executor parallelism independent from bounded
        # in-flight API concurrency; callers can tune the latter per run.
        try:
            gate_size = max(1, int(concurrency if concurrency is not None else os.getenv("KG_LLM_CONCURRENCY", "32")))
        except (TypeError, ValueError):
            gate_size = 32
        self._adaptive_limiter = AdaptiveRequestLimiter.from_environment()
        self._request_gate = threading.BoundedSemaphore(gate_size)

    def _get_client(self) -> OpenAI:
        """Lazily build the OpenAI client on first use.

        Deferring construction means simply instantiating an LLMClient (e.g. to
        read its configured model) does not require an API key to be present.
        """
        if self._client is None:
            api_key = self._api_key or _get_config_value('get_openai_api_key', None)
            # The SDK falls back to OPENAI_API_KEY in the env when api_key is None;
            # pass it explicitly when we have it (without mutating the environment).
            client_kwargs: Dict[str, Any] = dict(
                api_key=api_key,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
            http_client = _build_keepalive_http_client(self.timeout)
            if http_client is not None:
                client_kwargs["http_client"] = http_client
            self._client = OpenAI(**client_kwargs)
        return self._client

    def _create_with_watchdog(self, params: Dict[str, Any]) -> Any:
        """Run the SDK call under a hard wall-clock deadline.

        The OpenAI SDK's per-request timeout normally bounds a call, but a
        connection that dies silently can leave the underlying blocking socket
        read parked indefinitely past that timeout (observed: a call hung for
        hours after the machine slept). This backstop runs the request on a
        daemon thread and refuses to wait past ``timeout × attempts + margin``,
        so control always returns in finite time. A stranded thread (still
        blocked on the dead socket) is a daemon and never blocks process exit;
        TCP keep-alive tears its socket down shortly after.
        """
        box: Dict[str, Any] = {}

        if self.is_anthropic_model(self.model):
            def _call():
                try:
                    box["resp"] = self._litellm_completion(params)
                except BaseException as e:  # propagate any failure to the caller
                    box["err"] = e
        else:
            client = self._get_client()

            def _call():
                try:
                    box["resp"] = client.chat.completions.create(**params)
                except BaseException as e:  # propagate any failure to the caller
                    box["err"] = e

        worker = threading.Thread(target=_call, name="llm-call", daemon=True)
        worker.start()
        deadline = self.timeout * (self.max_retries + 1) + self.watchdog_margin
        # Poll against an absolute monotonic deadline instead of relying on a
        # single long Thread.join(timeout).  A stalled TLS read has previously
        # left the parent waiting far beyond the configured watchdog window on
        # Python 3.14/macOS, even though the worker remained a daemon thread.
        expires_at = time.monotonic() + max(0.0, float(deadline))
        while worker.is_alive():
            remaining = expires_at - time.monotonic()
            if remaining <= 0:
                break
            worker.join(min(1.0, remaining))

        if worker.is_alive():
            # Closing the transport is essential before returning.  Otherwise
            # the daemon thread can remain blocked in an SSL read and every
            # subsequent batch can leak another socket. ``close`` itself can
            # block when another request is concurrently inside httpx, so run
            # cleanup on a daemon thread with a short join bound. The caller
            # must regain control even if the transport is irrecoverably stuck.
            self._reset_client()
            raise TimeoutError(
                f"LLM call exceeded the hard watchdog deadline ({deadline:.0f}s) — "
                f"the connection is likely stalled or dead; aborting so the pipeline "
                f"fails fast instead of hanging indefinitely."
            )
        if "err" in box:
            raise box["err"]
        return box["resp"]

    def _litellm_model_name(self) -> str:
        """litellm requires a provider-prefixed model string for non-OpenAI models."""
        model = self.model or ""
        if model.startswith("anthropic/"):
            return model
        return f"anthropic/{model}"

    def _litellm_completion(self, params: Dict[str, Any]) -> Any:
        """Anthropic call path: litellm.completion() with the same OpenAI-shaped
        params chat_completion() already built, so callers/response handling
        downstream don't need to know which transport served the request."""
        import litellm  # deferred: keeps this an optional path, not an import-time cost

        call_params = dict(params)
        call_params["model"] = self._litellm_model_name()
        api_key = self._api_key or _get_config_value('get_anthropic_api_key', None)
        if api_key:
            call_params["api_key"] = api_key
        call_params.setdefault("max_retries", self.max_retries)
        call_params.setdefault("timeout", self.timeout)
        return litellm.completion(**call_params)

    def _reset_client(self) -> None:
        """Discard a failed transport without blocking the caller on close."""
        client = self._client
        self._client = None
        if client is None:
            return
        close = getattr(client, "close", None)
        if not callable(close):
            return
        close_thread = threading.Thread(
            target=close,
            name="llm-client-close",
            daemon=True,
        )
        close_thread.start()
        close_thread.join(timeout=min(5, max(1, self.timeout)))

    @staticmethod
    def is_openai_reasoning_model(model: str) -> bool:
        """Detect OpenAI reasoning models that need max_completion_tokens instead of max_tokens.

        Covers current and future OpenAI reasoning series (o1, o3, o4, …)
        as well as gpt-5.x models. `chat_completion`'s generous 4x/32768-
        floor token-budget heuristic applies to every reasoning model
        (OpenAI's and Claude's alike — both draw their internal reasoning/
        thinking tokens from the same ceiling as the visible completion,
        not a separate allowance on top of it); this narrower check exists
        only to pick the right *parameter name* for that budget
        (`max_completion_tokens` here vs. plain `max_tokens` for Claude via
        litellm) — see `is_reasoning_model` and `chat_completion` below.
        """
        model = model or ""
        return bool(
            re.match(r'^o\d', model, re.IGNORECASE)
            or 'gpt-5' in model.lower()
        )

    @staticmethod
    def is_anthropic_model(model: str) -> bool:
        """Detect Claude models, routed through litellm instead of the OpenAI SDK."""
        model = (model or "").lower()
        return model.startswith("claude") or model.startswith("anthropic/")

    @staticmethod
    def is_reasoning_model(model: str) -> bool:
        """True for any model that takes `reasoning_effort` instead of a plain
        `temperature` — OpenAI's o-series/gpt-5.x models, and Claude models
        (litellm maps `reasoning_effort` onto Claude's own extended-thinking
        controls)."""
        return LLMClient.is_openai_reasoning_model(model) or LLMClient.is_anthropic_model(model)

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Any:
        """
        Create a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature (ignored for reasoning models).
            max_tokens: Maximum tokens to generate.
            response_format: e.g. {"type": "json_object"} for JSON mode.
            **kwargs: Additional parameters (e.g. reasoning_effort), passed
                to the OpenAI SDK or litellm depending on `self.model`.

        Returns:
            The OpenAI ChatCompletion response object.
        """
        is_reasoning = self.is_reasoning_model(self.model)
        is_openai_reasoning = self.is_openai_reasoning_model(self.model)
        uses_reasoning_effort = bool(kwargs.get("reasoning_effort"))

        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        # Reasoning models reject `temperature` but accept `reasoning_effort`.
        if not is_reasoning:
            params["temperature"] = temperature
            kwargs.pop('reasoning_effort', None)
        elif 'reasoning_effort' in kwargs:
            params["reasoning_effort"] = kwargs.pop('reasoning_effort')

        # ── Token budget strategy ──
        # Reasoning models need generous headroom: an internal reasoning/
        # thinking budget is drawn from the same ceiling as the visible
        # completion, not a separate allowance on top of it. This was
        # originally believed to be OpenAI-only -- Claude was assumed to
        # size its thinking budget separately via litellm's reasoning_effort
        # translation (a plain max_tokens, uninflated, was passed through).
        # That assumption was wrong: a real remediation call at
        # max_tokens=12000, reasoning_effort="high" against claude-sonnet-5
        # came back with finish_reason="length" and EMPTY content -- the
        # entire budget was consumed by thinking before any visible JSON
        # could be produced. Both provider families get the same 4x/32768-
        # floor headroom now; only the resulting parameter NAME differs,
        # since litellm/Anthropic don't recognize OpenAI's
        # max_completion_tokens.
        if is_openai_reasoning or (is_reasoning and uses_reasoning_effort):
            completion_budget = max(max_tokens * 4, 32768) if max_tokens else 32768
            # A bounded, compact extraction run can opt out of the historical
            # 32k minimum. The default remains unchanged for existing callers.
            cap = os.getenv("KG_REASONING_MAX_COMPLETION_TOKENS")
            cap_override = kwargs.pop("reasoning_completion_cap_override", None)
            if cap:
                completion_budget = min(completion_budget, int(cap))
            if cap_override is not None:
                # Recovery callers may deliberately raise the normal pipeline
                # ceiling for a bounded retry after finish_reason=length. This
                # is an explicit per-call cap, not permission for ordinary
                # requests to bypass the configured global ceiling.
                completion_budget = min(
                    max(max_tokens * 4, 32768) if max_tokens else 32768,
                    max(1, int(cap_override)),
                )
            if is_openai_reasoning:
                params["max_completion_tokens"] = completion_budget
            else:
                params["max_tokens"] = completion_budget
            kwargs.pop('max_completion_tokens', None)
            kwargs.pop('max_tokens', None)
        elif max_tokens:
            params["max_tokens"] = max_tokens
            kwargs.pop("reasoning_completion_cap_override", None)

        if response_format:
            params["response_format"] = response_format

        params.update(kwargs)

        lease = None
        request_started = None
        try:
            with self._request_gate:
                if self._adaptive_limiter is not None:
                    # Queue admission is not an API request and must not inherit
                    # the provider watchdog. When adaptive concurrency falls
                    # sharply (for example 32 -> 1 after a transport incident),
                    # healthy queued workers can legitimately wait longer than
                    # one request's retry window. Expired and dead-owner leases
                    # are reaped by AdaptiveRequestLimiter, so waiting here is
                    # bounded by actual capacity recovery rather than falsely
                    # failing an unissued request.
                    lease = self._adaptive_limiter.acquire(timeout=None)
                request_started = time.monotonic()
                response = self._create_with_watchdog(params)
        except Exception as e:
            if lease is not None and self._adaptive_limiter is not None:
                throttled, penalize = self._classify_backpressure_error(e)
                snapshot = self._adaptive_limiter.release(
                    lease, success=False, penalize=penalize, throttled=throttled,
                    request_seconds=(
                        time.monotonic() - request_started if request_started is not None else 0
                    ),
                )
                self._emit_request_metric(lease, snapshot, False, e)
            # A connection error can leave the keep-alive pool unusable. Reset
            # it before the caller's bounded batch retry constructs a fresh
            # transport; otherwise retries repeat the same dead socket.
            self._reset_client()
            raise LLMCompletionError(
                f"LLM completion failed: {str(e)}",
                original=e,
            ) from e

        if lease is not None and self._adaptive_limiter is not None:
            snapshot = self._adaptive_limiter.release(
                lease,
                success=True,
                request_seconds=(
                    time.monotonic() - request_started if request_started is not None else 0
                ),
            )
            self._emit_request_metric(lease, snapshot, True, None)

        # ── Safety check: warn on unexpected empty or truncated output ──
        content = (response.choices[0].message.content or "").strip()
        finish = getattr(response.choices[0], 'finish_reason', None)
        if not content:
            print(
                f"  ⚠️  Empty response from model (finish_reason={finish}).",
                file=sys.stderr, flush=True,
            )
        elif finish == 'length':
            print(
                f"  ⚠️  Response truncated (finish_reason=length, "
                f"{len(content)} chars). Output may contain incomplete JSON.",
                file=sys.stderr, flush=True,
            )

        # ── Cost & cache tracking (emitted for the UI run aggregator) ──
        usage = getattr(response, 'usage', None)
        if usage:
            cached = getattr(
                getattr(usage, 'prompt_tokens_details', None),
                'cached_tokens', 0,
            ) or 0
            if not cached:
                # litellm does not (yet) normalize Anthropic's own
                # cache_read_input_tokens into the OpenAI-shaped
                # prompt_tokens_details.cached_tokens field -- see this
                # module's docstring. Read the Anthropic-native field
                # directly so cache-hit tracking still works for Claude.
                cached = getattr(usage, 'cache_read_input_tokens', 0) or 0
            if cached:
                print(
                    f"  💾 Prompt cache hit: {cached} tokens cached "
                    f"(of {usage.prompt_tokens} prompt tokens)",
                    file=sys.stderr, flush=True,
                )
            cost = self._estimate_response_cost(response, usage)
            cost_entry = {
                "model": self.model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "cached_tokens": cached,
                "cost": round(cost, 6),
            }
            # Structured line — pipeline_runner parses lines starting with [LLM_COST]
            print(f"[LLM_COST]{json.dumps(cost_entry)}", flush=True)

        return response

    def _estimate_response_cost(self, response: Any, usage: Any) -> float:
        """Best-effort USD cost for one response.

        OpenAI models use this module's hand-maintained `_PRICING_PER_1M`
        table (unchanged behavior). Anthropic models use litellm's own
        maintained cost table (`litellm.completion_cost`), which already
        knows current Claude pricing -- covers the model without hand-adding
        entries here, and stays current with litellm upgrades. Falls back to
        0.0 (never raises) if litellm's calculator doesn't recognize the
        model or the response shape, matching `_estimate_cost`'s contract.
        """
        if self.is_anthropic_model(self.model):
            try:
                import litellm
                return float(litellm.completion_cost(completion_response=response))
            except Exception:
                return 0.0
        return _estimate_cost(self.model, usage.prompt_tokens, usage.completion_tokens)

    @staticmethod
    def _classify_backpressure_error(error: BaseException) -> tuple[bool, bool]:
        status_code = getattr(error, "status_code", None)
        value = f"{type(error).__name__}: {error}".lower()
        throttled = status_code == 429 or "429" in value or "rate limit" in value
        penalize = throttled or any(token in value for token in ("timeout", "timed out", "connection", "socket"))
        return throttled, penalize

    def _emit_request_metric(
        self, lease, snapshot: Mapping[str, Any], success: bool, error: BaseException | None
    ) -> None:
        metric = {
            "model": self.model, "success": success,
            "wait_seconds": round(float(lease.wait_seconds), 3),
            "current_limit": snapshot.get("current_limit"),
            "active_leases": snapshot.get("active_leases"),
            "total_success": snapshot.get("total_success"),
            "total_failure": snapshot.get("total_failure"),
            "total_throttled": snapshot.get("total_throttled"),
            "error_type": None if error is None else type(error).__name__,
        }
        print(f"[LLM_METRIC]{json.dumps(metric)}", flush=True)

    def get_text_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Return just the text content from a chat completion."""
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Empty response from model (content is None)")
        return content


def create_llm_client(
    api_key: Optional[str] = None,
    model: str = None,
    timeout: int = None,
    max_retries: int = None,
    concurrency: int = None,
) -> LLMClient:
    """Factory for an LLMClient. `model` picks the transport: an OpenAI model
    name uses the OpenAI SDK; a Claude model name (`claude-...`) is routed
    through litellm -- see LLMClient.is_anthropic_model."""
    return LLMClient(
        api_key=api_key,
        model=model,
        timeout=timeout,
        max_retries=max_retries,
        concurrency=concurrency,
    )
