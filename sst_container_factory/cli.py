"""Command-line entry points for the Python transition layer."""

from __future__ import annotations

import argparse
import sys

from .logging_utils import log_error
from .orchestration import (
    experiment_build_from_env,
    OrchestrationError,
    prepare_image_config_from_env,
    validate_container_from_env,
    validate_custom_inputs_from_env,
    validate_experiment_inputs_from_env,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""

    parser = argparse.ArgumentParser(prog="sst-container-factory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("experiment-build")
    subparsers.add_parser("prepare-image-config")
    subparsers.add_parser("validate-container")
    subparsers.add_parser("validate-custom-inputs")
    subparsers.add_parser("validate-experiment-inputs")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the requested orchestration command."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "experiment-build":
            experiment_build_from_env()
        elif args.command == "prepare-image-config":
            prepare_image_config_from_env()
        elif args.command == "validate-container":
            validate_container_from_env()
        elif args.command == "validate-custom-inputs":
            validate_custom_inputs_from_env()
        elif args.command == "validate-experiment-inputs":
            validate_experiment_inputs_from_env()
        else:
            parser.error(f"Unsupported command: {args.command}")
    except OrchestrationError as error:
        for line in str(error).splitlines():
            log_error(line)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
