"""Minimal logging helpers for the Python transition layer."""

from __future__ import annotations

import logging
import os
import sys

from . import github_actions


LOGGER = logging.getLogger("sst_container_factory")

if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    LOGGER.addHandler(handler)

configured_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), None)
if not isinstance(configured_level, int):
    configured_level = getattr(logging, "INFO")
LOGGER.setLevel(configured_level)



def log_info(message: str) -> None:
    """Log an informational message."""

    if github_actions.is_github_actions():
        github_actions.emit_annotation("notice", message)
    else:
        LOGGER.info(message)


def log_warning(message: str) -> None:
    """Log a warning message."""

    if github_actions.is_github_actions():
        github_actions.emit_annotation("warning", message)
    else:
        LOGGER.warning(message)


def log_error(message: str) -> None:
    """Log an error message."""

    if github_actions.is_github_actions():
        github_actions.emit_annotation("error", message)
    else:
        LOGGER.error(message)


def log_success(message: str) -> None:
    """Log a success-style informational message."""

    log_info(f"[SUCCESS] {message}")
