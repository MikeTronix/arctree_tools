"""Shared logging for the editor and CLI entry points."""
from __future__ import annotations

import logging
import sys

LOGGER_NAME = "passages_tool"


def get_logger(name: str = "") -> logging.Logger:
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)


class _BelowWarning(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


def configure_cli(level: int = logging.INFO) -> None:
    """INFO/DEBUG on stdout, WARNING+ on stderr; message-only (matches old prints)."""
    root = logging.getLogger(LOGGER_NAME)
    if root.handlers:
        return
    root.setLevel(level)
    root.propagate = False
    fmt = logging.Formatter("%(message)s")
    out = logging.StreamHandler(sys.stdout)
    out.setLevel(logging.DEBUG)
    out.addFilter(_BelowWarning())
    out.setFormatter(fmt)
    err = logging.StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING)
    err.setFormatter(fmt)
    root.addHandler(out)
    root.addHandler(err)


def configure_editor() -> None:
    configure_cli(level=logging.WARNING)
