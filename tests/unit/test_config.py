"""Tests for settings, secret handling, log redaction and the LLM factory. No network calls."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from src.utils.config import (
    ConfigError,
    Secret,
    load_llm_settings,
    load_settings,
    read_env,
    secret_values,
)
from src.utils.llm import build_llm
from src.utils.logging_setup import MASK, redact, setup_logging

FAKE_KEY = "sk-fake-test-key-0123456789"  # not a real key
LLM_ENV = {
    "OPENAI_API_KEY": FAKE_KEY,
    "OPENAI_MODEL": "test-model",
    "OPENAI_FALLBACK_MODEL": "test-fallback",
    "LLM_TEMPERATURE": "0",
    "LLM_MAX_RETRIES": "2",
    "LLM_TIMEOUT_SECONDS": "60",
    "LLM_MAX_OUTPUT_TOKENS": "2000",
    "LLM_MAX_CALLS_PER_RUN": "100",
    "LLM_MAX_TOKENS_PER_RUN": "200000",
}


@pytest.fixture(autouse=True)
def _remove_our_log_handlers():
    """Leave the root logger as it was, so other tests are not affected."""
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_retailai", False):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(logging.WARNING)


def env(**changes) -> dict[str, str]:
    values = dict(LLM_ENV)
    values.update({k: v for k, v in changes.items() if v is not None})
    for k, v in changes.items():
        if v is None:
            values.pop(k, None)
    return values


# ---------------------------------------------------------------- settings


def test_general_settings_defaults():
    s = load_settings({})
    assert (s.log_level, s.repository_backend, s.random_seed) == ("INFO", "local", None)


def test_general_settings_do_not_need_openai():
    assert load_settings({"LOG_LEVEL": "debug", "RANDOM_SEED": "42"}).random_seed == 42


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"LOG_LEVEL": "LOUD"}, "LOG_LEVEL"),
        ({"REPOSITORY_BACKEND": "mongo"}, "REPOSITORY_BACKEND"),
        ({"REPOSITORY_BACKEND": "supabase"}, "SUPABASE_URL"),
        ({"RANDOM_SEED": "abc"}, "RANDOM_SEED"),
        ({"RANDOM_SEED": "-1"}, "RANDOM_SEED"),
    ],
)
def test_general_settings_invalid(values, message):
    with pytest.raises(ConfigError, match=message):
        load_settings(values)


def test_llm_settings_load():
    s = load_llm_settings(LLM_ENV)
    assert s.model == "test-model" and s.fallback_model == "test-fallback"
    assert (s.temperature, s.max_retries, s.timeout_seconds) == (0.0, 2, 60.0)
    assert (s.max_output_tokens, s.max_calls_per_run, s.max_tokens_per_run) == (2000, 100, 200000)
    assert s.api_key.reveal() == FAKE_KEY


@pytest.mark.parametrize(
    "name",
    [
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "LLM_TEMPERATURE",
        "LLM_MAX_RETRIES",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_MAX_CALLS_PER_RUN",
        "LLM_MAX_TOKENS_PER_RUN",
    ],
)
def test_llm_settings_missing_value(name):
    """No hard-coded fallback for the key, model or any limit."""
    with pytest.raises(ConfigError, match=name):
        load_llm_settings(env(**{name: None}))


def test_empty_value_counts_as_missing():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_llm_settings(env(OPENAI_API_KEY="  "))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_MAX_RETRIES", "two"),
        ("LLM_MAX_RETRIES", "-1"),
        ("LLM_TIMEOUT_SECONDS", "0"),
        ("LLM_MAX_CALLS_PER_RUN", "0"),
        ("LLM_TEMPERATURE", "3"),
    ],
)
def test_llm_settings_invalid_value(name, value):
    with pytest.raises(ConfigError, match=name):
        load_llm_settings(env(**{name: value}))


def test_error_messages_never_contain_the_key():
    with pytest.raises(ConfigError) as info:
        load_llm_settings(env(OPENAI_MODEL=None))
    assert FAKE_KEY not in str(info.value)


def test_inline_comment_is_ignored():
    assert load_llm_settings(env(OPENAI_MODEL="test-model   # proposed")).model == "test-model"


def test_fallback_model_is_optional():
    assert load_llm_settings(env(OPENAI_FALLBACK_MODEL=None)).fallback_model is None


# ------------------------------------------------------------------ secrets


def test_secret_is_hidden_everywhere():
    s = load_llm_settings(LLM_ENV)
    for text in (repr(s), str(s), f"{s.api_key}", repr(s.api_key), str(s.api_key)):
        assert FAKE_KEY not in text


def test_secret_values_lists_present_secrets():
    assert secret_values({"OPENAI_API_KEY": FAKE_KEY, "SUPABASE_KEY": ""}) == [FAKE_KEY]


def test_secret_equality():
    assert Secret("a") == Secret("a") and Secret("a") != Secret("b")


# --------------------------------------------------------------------- .env


def test_read_env_uses_dotenv_and_environment_wins(tmp_path: Path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENAI_MODEL=from-file\nLOG_LEVEL=DEBUG\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_MODEL", "from-environment")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    values = read_env(dotenv)
    assert values["OPENAI_MODEL"] == "from-environment"
    assert values["LOG_LEVEL"] == "DEBUG"
    assert "LOG_LEVEL" not in os.environ  # os.environ is not modified


def test_read_env_without_file(tmp_path: Path):
    assert isinstance(read_env(tmp_path / "missing.env"), dict)


def test_env_example_is_consistent():
    """.env.example works for general settings and has no real key (LLM settings fail)."""
    values = {k: v or "" for k, v in dotenv_values(".env.example").items()}
    assert load_settings(values).repository_backend == "local"
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_llm_settings(values)


# ------------------------------------------------------------------ logging


def test_redact_masks_keys_and_known_secrets():
    text = f"key={FAKE_KEY} other=sk-abcdefgh123 token=supersecretvalue short=abc"
    out = redact(text, ["supersecretvalue", "abc"])
    assert FAKE_KEY not in out and "sk-abcdefgh123" not in out and "supersecretvalue" not in out
    assert out.count(MASK) == 3
    assert "short=abc" in out  # too short to redact safely


def test_logs_are_redacted_including_tracebacks(tmp_path: Path):
    log_file = tmp_path / "run.log"
    setup_logging("INFO", log_file, secrets=["my-supabase-secret"])
    log = logging.getLogger("test.redaction")
    log.info("calling with %s and my-supabase-secret", FAKE_KEY)
    try:
        raise RuntimeError(f"failed with key {FAKE_KEY}")
    except RuntimeError:
        log.exception("boom")
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = log_file.read_text(encoding="utf-8")
    assert FAKE_KEY not in text and "my-supabase-secret" not in text
    assert text.count(MASK) >= 3


def test_logging_a_crewai_llm_object_does_not_leak_the_key(tmp_path: Path):
    """CrewAI LLM objects include the key in their repr; the formatter must mask it."""
    llm = build_llm(load_llm_settings(LLM_ENV))
    assert FAKE_KEY in repr(llm)  # the risk exists in CrewAI itself
    log_file = tmp_path / "run.log"
    setup_logging("INFO", log_file)
    logging.getLogger("test.llm").info("llm=%r", llm)
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert FAKE_KEY not in log_file.read_text(encoding="utf-8")


def test_setup_logging_twice_does_not_duplicate_handlers(tmp_path: Path):
    setup_logging("INFO")
    setup_logging("WARNING")
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_retailai", False)]
    assert len(ours) == 1
    assert logging.getLogger().level == logging.WARNING


# ---------------------------------------------------------------------- LLM


def test_build_llm_applies_settings_without_network():
    llm = build_llm(load_llm_settings(LLM_ENV))
    assert llm.model == "test-model"
    assert (llm.temperature, llm.timeout, llm.max_tokens, llm.max_retries) == (0.0, 60.0, 2000, 2)


def test_build_llm_fallback():
    assert build_llm(load_llm_settings(LLM_ENV), use_fallback=True).model == "test-fallback"


def test_build_llm_fallback_missing():
    settings = load_llm_settings(env(OPENAI_FALLBACK_MODEL=None))
    with pytest.raises(ConfigError, match="OPENAI_FALLBACK_MODEL"):
        build_llm(settings, use_fallback=True)
