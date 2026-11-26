"""The language models that can write the stage 1 question.

Pick one with DEBUGGER_PROVIDER:

* claude (default): Anthropic's Claude, needs ANTHROPIC_API_KEY.
  Model from DEBUGGER_MODEL (default claude-opus-5-5, or claude-haiku-5-5 for
  a cheaper option), effort from DEBUGGER_EFFORT (low | medium | high),
  thinking from DEBUGGER_THINKING (on, the default, or off). Lower effort and
  thinking off are faster but can make the hints worse: compare them with
  `python -m evals.compare_speed` before changing them.
* gemini: Google's Gemini API, needs GEMINI_API_KEY. Has a free tier.
  Model from GEMINI_MODEL (default gemini-3.5-flash).

Both get the same prompt and must return the same structured HintDraft, so the
guardrails, retry and rule-based fallback in hints.py work the same for both.
"""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, Field

from .analysis import ErrorReport
from .prompts import SYSTEM_PROMPT, build_user_message

log = logging.getLogger(__name__)

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


class HintDraft(BaseModel):
    """What the model returns. Only `question` is shown to the student."""

    root_cause: str = Field(description="One sentence for teachers and later stages. Never shown to the student.")
    misconception: str = Field(description="The wrong belief the student most likely holds.")
    cause_line: int = Field(description="Line number the student should look at.")
    concept: str = Field(description="Short lowercase concept tag.")
    giveaways: list[str] = Field(description="Words or identifiers that would give away the fix.")
    question: str = Field(description="The single stage 1 leading question shown to the student.")


T = TypeVar("T", bound=BaseModel)


class HintModel(Protocol):
    name: str  # e.g. "claude:claude-opus-5-5", recorded with each hint

    def draft(self, code: str, report: ErrorReport, feedback: str | None) -> HintDraft: ...

    def structured(self, system: str, user: str, schema: type[T]) -> T: ...


class ClaudeHintModel:
    def __init__(self, client: Any, model: str = DEFAULT_CLAUDE_MODEL, effort: str = "medium",
                 thinking: bool = True):
        self.client = client
        self.model = model
        self.effort = effort
        self.thinking = _thinking_config(model, effort, thinking)
        self.name = f"claude:{model}"

    def draft(self, code: str, report: ErrorReport, feedback: str | None) -> HintDraft:
        return self.structured(SYSTEM_PROMPT, build_user_message(code, report, feedback), HintDraft)

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        """One request whose answer must fit `schema` (a pydantic model)."""
        # Server-side refusal fallback exists for Opus/Sonnet/Fable, not for Haiku.
        fallback = {} if "haiku" in self.model else {
            "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        started = time.perf_counter()
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            **fallback,
            thinking=self.thinking,
            output_config={"effort": self.effort},
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        _log_claude_call(self.name, schema.__name__, time.perf_counter() - started, response)
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("model output was cut off")
        if response.parsed_output is None:
            raise RuntimeError("model returned no structured output")
        return response.parsed_output


def _thinking_config(model: str, effort: str, thinking: bool) -> dict[str, str]:
    """Adaptive thinking, or thinking off where the model allows it. Thinking can't be
    turned off on Opus 5.5, Fable or Mythos, nor at effort xhigh or max on any model;
    there it stays on (with a warning). Sonnet 5.5 turns it off with between_tools."""
    if thinking:
        return {"type": "adaptive"}
    if any(m in model for m in ("opus-5-5", "fable", "mythos")) or effort in ("xhigh", "max"):
        log.warning("DEBUGGER_THINKING=off is not supported for %s at effort %s; thinking stays on",
                    model, effort)
        return {"type": "adaptive"}
    if "sonnet-5-5" in model:
        return {"type": "between_tools"}
    return {"type": "disabled"}


class GeminiHintModel:
    def __init__(self, client: Any, model: str = DEFAULT_GEMINI_MODEL):
        self.client = client
        self.model = model
        self.name = f"gemini:{model}"

    def draft(self, code: str, report: ErrorReport, feedback: str | None) -> HintDraft:
        return self.structured(SYSTEM_PROMPT, build_user_message(code, report, feedback), HintDraft)

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        from google.genai import types

        started = time.perf_counter()
        response = self.client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        _log_gemini_call(self.name, schema.__name__, time.perf_counter() - started, response)
        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed
        if response.text:  # some SDK versions leave parsing to the caller
            return schema.model_validate_json(response.text)
        raise RuntimeError("model returned no structured output (possibly blocked by a safety filter)")


def record_model_seconds(internal: dict[str, Any], started: float) -> None:
    """Adds how long one model call took (since `started`, a perf_counter value) to a hint's
    internal record, for the timing log. A draft rejected by the guardrails adds a second call."""
    internal.setdefault("model_seconds", []).append(round(time.perf_counter() - started, 3))


def _count(usage: Any, name: str) -> int:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) else 0


def _log_claude_call(name: str, schema: str, seconds: float, response: Any) -> None:
    """One line per model call: how long it took and where the output tokens went.
    output_tokens includes the model's thinking, which is never returned as text, so the
    thinking share is estimated as output_tokens minus the visible answer (~4 characters
    a token)."""
    usage = getattr(response, "usage", None)
    out = _count(usage, "output_tokens")
    visible = sum(len(getattr(b, "text", "") or "") for b in getattr(response, "content", None) or []
                  if getattr(b, "type", None) == "text") // 4
    log.info(
        "model call %s %s: %.2f s, input %d tokens (%d from cache), output %d tokens "
        "(answer ~%d, thinking ~%d), stop %s",
        name, schema, seconds,
        _count(usage, "input_tokens") + _count(usage, "cache_read_input_tokens")
        + _count(usage, "cache_creation_input_tokens"),
        _count(usage, "cache_read_input_tokens"), out, visible, max(out - visible, 0),
        getattr(response, "stop_reason", None),
    )


def _log_gemini_call(name: str, schema: str, seconds: float, response: Any) -> None:
    usage = getattr(response, "usage_metadata", None)
    log.info(
        "model call %s %s: %.2f s, input %d tokens (%d from cache), output %d tokens (answer %d, thinking %d)",
        name, schema, seconds, _count(usage, "prompt_token_count"), _count(usage, "cached_content_token_count"),
        _count(usage, "candidates_token_count") + _count(usage, "thoughts_token_count"),
        _count(usage, "candidates_token_count"), _count(usage, "thoughts_token_count"),
    )


def default_hint_model() -> HintModel | None:
    """The model chosen by the environment, or None when its API key is missing.

    The same model object (and so the same HTTP client) is reused for as long as the
    settings stay the same, so each hint reuses an open connection to the provider
    instead of setting up a new one (DNS, TCP and TLS) every time."""
    env = os.environ.get
    return _model_for(
        env("DEBUGGER_PROVIDER", "claude").strip().lower(),
        env("ANTHROPIC_API_KEY"), env("ANTHROPIC_AUTH_TOKEN"), env("DEBUGGER_MODEL", DEFAULT_CLAUDE_MODEL),
        env("DEBUGGER_EFFORT", "medium"),
        env("DEBUGGER_THINKING", "on").strip().lower() not in ("off", "0", "false", "no"),
        env("GEMINI_API_KEY") or env("GOOGLE_API_KEY"), env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
    )


@lru_cache(maxsize=4)
def _model_for(provider: str, anthropic_key: str | None, anthropic_token: str | None, claude_model: str,
               effort: str, thinking: bool, gemini_key: str | None, gemini_model: str) -> HintModel | None:
    if provider == "gemini":
        if not gemini_key:
            return None
        from google import genai

        return GeminiHintModel(genai.Client(api_key=gemini_key), gemini_model)
    if provider != "claude":
        raise ValueError(f"Unknown DEBUGGER_PROVIDER {provider!r}; use 'claude' or 'gemini'.")
    if not (anthropic_key or anthropic_token):
        return None
    import anthropic

    return ClaudeHintModel(anthropic.Anthropic(), claude_model, effort, thinking)
