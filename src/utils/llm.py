"""Build the CrewAI LLM from the settings (T-01). The only place an LLM is created.

Creating the LLM makes no network call. All values come from LLMSettings, so
no model name or limit is hard-coded. Warning: CrewAI LLM objects show the API
key in their repr; never print or log them (the log formatter redacts keys as
a safety net).
"""

from __future__ import annotations

from crewai import LLM

from src.utils.config import ConfigError, LLMSettings


def build_llm(settings: LLMSettings, use_fallback: bool = False) -> LLM:
    """The configured OpenAI model (or the fallback model) with the cost controls applied."""
    model = settings.fallback_model if use_fallback else settings.model
    if not model:
        name = "OPENAI_FALLBACK_MODEL" if use_fallback else "OPENAI_MODEL"
        raise ConfigError(f"{name} is not set; add it to your local .env (see .env.example)")
    return LLM(
        model=model,
        api_key=settings.api_key.reveal(),
        temperature=settings.temperature,
        timeout=settings.timeout_seconds,
        max_tokens=settings.max_output_tokens,
        max_retries=settings.max_retries,
    )
