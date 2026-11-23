"""Logging setup with secret redaction (CLAUDE.md: never print secrets or put them in logs).

Every formatted log line, including tracebacks, passes through RedactingFormatter,
which masks OpenAI-style keys (`sk-...`) and the exact values of known secrets.
CrewAI LLM objects include the API key in their repr, so this also protects
against logging such an object by mistake. Rule: still never log LLM objects.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path

MASK = "***REDACTED***"
KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MIN_SECRET_LENGTH = 6  # shorter values are too likely to match ordinary text


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Mask known secret values and anything shaped like an OpenAI key."""
    for value in sorted({s for s in secrets if len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True):
        text = text.replace(value, MASK)
    return KEY_PATTERN.sub(MASK, text)


class RedactingFormatter(logging.Formatter):
    """A formatter whose output (message and traceback) is redacted."""

    def __init__(self, fmt: str = LOG_FORMAT, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt)
        self.secrets = tuple(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self.secrets)


def setup_logging(
    level: str = "INFO", log_file: Path | None = None, secrets: Iterable[str] = ()
) -> logging.Logger:
    """Configure the root logger: console (and optional file), all output redacted.

    Replaces the handlers it added earlier, so calling it twice does not duplicate
    lines; handlers added by other tools (for example pytest) are left alone.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_retailai", False):
            root.removeHandler(handler)
            handler.close()
    formatter = RedactingFormatter(secrets=secrets)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(formatter)
        handler._retailai = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level)
    return root


def setup_from_env(log_file: Path | None = None) -> logging.Logger:
    """setup_logging with LOG_LEVEL and the secrets taken from the environment / .env."""
    from src.utils.config import load_settings, read_env, secret_values

    env = read_env()
    return setup_logging(load_settings(env).log_level, log_file, secret_values(env))
