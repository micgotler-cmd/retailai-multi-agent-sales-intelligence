"""Project settings from environment variables (and an optional local `.env`).

One place for configuration (CLAUDE.md, architecture.md). Nothing secret or
model-specific is hard-coded: the OpenAI key, model names and LLM limits come
only from the environment. Only two documented defaults exist:
REPOSITORY_BACKEND=local and LOG_LEVEL=INFO (architecture.md).

The LLM settings are loaded separately (load_llm_settings), so data steps and
tests run without an OpenAI key. The key is held in a Secret that never shows
its value in repr, str or f-strings.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_DOTENV = Path(".env")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
BACKENDS = ("local", "supabase")


class ConfigError(Exception):
    """Raised when a setting is missing or invalid. Messages never contain secret values."""


class Secret:
    """A secret string that hides its value everywhere except reveal()."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """The real value. Pass it only to the client that needs it; never log it."""
        return self._value

    def __repr__(self) -> str:
        return "Secret('***')"

    def __str__(self) -> str:
        return "***"

    def __format__(self, spec: str) -> str:
        return "***"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True)
class Settings:
    """General settings needed by every part of the pipeline."""

    log_level: str
    repository_backend: str
    random_seed: int | None


@dataclass(frozen=True)
class LLMSettings:
    """OpenAI settings and cost controls (T-01). Required only when an LLM is used."""

    api_key: Secret
    model: str
    fallback_model: str | None
    temperature: float
    max_retries: int
    timeout_seconds: float
    max_output_tokens: int
    max_calls_per_run: int
    max_tokens_per_run: int


def read_env(dotenv_path: Path | None = DEFAULT_DOTENV) -> dict[str, str]:
    """Environment variables, with values from `.env` filling in missing ones.

    Real environment variables win over `.env`. os.environ is not modified.
    """
    values: dict[str, str] = {}
    if dotenv_path is not None and Path(dotenv_path).is_file():
        values.update({k: v for k, v in dotenv_values(dotenv_path).items() if v is not None})
    values.update(os.environ)
    return values


def _get(env: Mapping[str, str], name: str, default: str | None = None) -> str | None:
    """A trimmed value; empty strings count as missing. Inline comments are removed."""
    raw = env.get(name)
    if raw is not None:
        raw = raw.split(" #", 1)[0].strip()
    return raw if raw else default


def _required(env: Mapping[str, str], name: str) -> str:
    value = _get(env, name)
    if value is None:
        raise ConfigError(f"{name} is not set; add it to your local .env (see .env.example)")
    return value


def _number(env: Mapping[str, str], name: str, kind: type, minimum: float, required: bool = True):
    raw = _required(env, name) if required else _get(env, name)
    if raw is None:
        return None
    try:
        value = kind(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a {kind.__name__}, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {value}")
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """General settings. Pass `env` in tests; by default reads the environment and `.env`."""
    env = read_env() if env is None else env
    level = (_get(env, "LOG_LEVEL", "INFO") or "INFO").upper()
    if level not in LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}, got {level!r}")
    backend = (_get(env, "REPOSITORY_BACKEND", "local") or "local").lower()
    if backend not in BACKENDS:
        raise ConfigError(f"REPOSITORY_BACKEND must be 'local' or 'supabase', got {backend!r}")
    if backend == "supabase":
        _required(env, "SUPABASE_URL")
        _required(env, "SUPABASE_KEY")
    return Settings(
        log_level=level,
        repository_backend=backend,
        random_seed=_number(env, "RANDOM_SEED", int, 0, required=False),
    )


def load_llm_settings(env: Mapping[str, str] | None = None) -> LLMSettings:
    """OpenAI settings and limits; every value must be set (no hard-coded model or limit)."""
    env = read_env() if env is None else env
    key = _required(env, "OPENAI_API_KEY")
    temperature = _number(env, "LLM_TEMPERATURE", float, 0.0)
    if temperature > 2:
        raise ConfigError(f"LLM_TEMPERATURE must be between 0 and 2, got {temperature}")
    return LLMSettings(
        api_key=Secret(key),
        model=_required(env, "OPENAI_MODEL"),
        fallback_model=_get(env, "OPENAI_FALLBACK_MODEL"),
        temperature=temperature,
        max_retries=_number(env, "LLM_MAX_RETRIES", int, 0),
        timeout_seconds=_number(env, "LLM_TIMEOUT_SECONDS", float, 1),
        max_output_tokens=_number(env, "LLM_MAX_OUTPUT_TOKENS", int, 1),
        max_calls_per_run=_number(env, "LLM_MAX_CALLS_PER_RUN", int, 1),
        max_tokens_per_run=_number(env, "LLM_MAX_TOKENS_PER_RUN", int, 1),
    )


def secret_values(env: Mapping[str, str] | None = None) -> list[str]:
    """Secret values present in the environment, for the log redaction filter."""
    env = read_env() if env is None else env
    names = ("OPENAI_API_KEY", "SUPABASE_KEY")
    return [v for n in names if (v := _get(env, n))]
