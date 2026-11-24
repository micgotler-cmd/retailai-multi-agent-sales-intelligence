"""Build the CrewAI LLM from the settings (T-01). The only place an LLM is created.

Creating the LLM makes no network call. All values come from LLMSettings, so
no model name or limit is hard-coded. Warning: CrewAI LLM objects show the API
key in their repr; never print or log them (the log formatter redacts keys as
a safety net).
"""

from __future__ import annotations

import os

from crewai import LLM

from src.utils.config import ConfigError, LLMSettings

# CrewAI sends anonymous telemetry and offers tracing by default. Both send data to an
# outside service, so the project always turns them off; only OpenAI calls leave the machine.
TELEMETRY_OFF = {
    "CREWAI_DISABLE_TELEMETRY": "true",
    "OTEL_SDK_DISABLED": "true",
    "CREWAI_TRACING_ENABLED": "false",
}


def disable_crewai_telemetry() -> None:
    """Turn off CrewAI telemetry and tracing for this process (always, not a default)."""
    os.environ.update(TELEMETRY_OFF)


def build_llm(settings: LLMSettings, use_fallback: bool = False) -> LLM:
    """The configured OpenAI model (or the fallback model) with the cost controls applied."""
    model = settings.fallback_model if use_fallback else settings.model
    if not model:
        name = "OPENAI_FALLBACK_MODEL" if use_fallback else "OPENAI_MODEL"
        raise ConfigError(f"{name} is not set; add it to your local .env (see .env.example)")
    disable_crewai_telemetry()
    return LLM(
        model=model,
        api_key=settings.api_key.reveal(),
        temperature=settings.temperature,
        timeout=settings.timeout_seconds,
        max_tokens=settings.max_output_tokens,
        max_retries=settings.max_retries,
    )
