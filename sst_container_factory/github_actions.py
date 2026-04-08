"""Helpers for GitHub Actions integration."""

from __future__ import annotations

import os
from pathlib import Path


def is_github_actions() -> bool:
    """Return whether the current process is running in GitHub Actions."""

    return os.environ.get("GITHUB_ACTIONS") == "true"


def set_output(name: str, value: str) -> None:
    """Write a GitHub Actions step output when available."""

    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    path = Path(output_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def emit_annotation(level: str, message: str) -> None:
    """Emit a GitHub Actions annotation or plain text log line."""

    if is_github_actions():
        print(f"::{level}::{message}")
        return

    print(message)


def start_group(name: str) -> None:
    """Start a GitHub Actions log group when available."""

    if is_github_actions():
        print(f"::group::{name}")
    else:
        print(f"=== {name} ===")


def end_group() -> None:
    """End a GitHub Actions log group when available."""

    if is_github_actions():
        print("::endgroup::")
    else:
        print("")
