"""Command-line entry points for the Python transition layer."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from .adapters import (
    prepare_workflow_build_from_env,
    validate_container_from_env,
)

from .logging_utils import log_error
from .orchestration import (
    DEFAULT_BUILD_NCPUS,
    DEFAULT_SST_CORE_REPO,
    DEFAULT_MPICH_VERSION,
    DEFAULT_SST_VERSION,
    detect_host_platform,
    download_sources,
    build,
    BuildRequest,
    require_host_platform,
)


def container_engine_choices() -> tuple[str, ...]:
    """Return the supported container engines for CLI choice declarations."""

    return ("docker", "podman")


def validation_mode_choices() -> tuple[str, ...]:
    """Return the supported validation modes for CLI choice declarations."""

    return ("full", "quick", "metadata", "none")


def _argument_type_with_standard_errors(
    validator: Callable[[str], str],
) -> Callable[[str], str]:
    """Adapt shared validators for cleaner argparse type errors."""

    def wrapped(value: str) -> str:
        try:
            return validator(value)
        except (ValueError, FileNotFoundError) as error:
            raise argparse.ArgumentTypeError(str(error)) from error

    return wrapped


def _handle_download_sources(args: argparse.Namespace) -> None:
    """Dispatch the source downloader CLI."""

    explicit_download_selection = any(
        [
            args.sst_version is not None,
            args.sst_elements_version is not None,
            args.mpich_version is not None,
        ]
    )
    download_sources(
        sst_version=args.sst_version or args.sst_version_arg or DEFAULT_SST_VERSION,
        sst_elements_version=args.sst_elements_version,
        mpich_version=args.mpich_version or args.mpich_version_arg or DEFAULT_MPICH_VERSION,
        download_mpich=(args.mpich_version is not None) if explicit_download_selection else True,
        download_sst_core=(args.sst_version is not None) if explicit_download_selection else True,
        download_sst_elements=(args.sst_elements_version is not None) if explicit_download_selection else True,
        force_mode=args.force,
    )


def _handle_build(args: argparse.Namespace) -> None:
    """Dispatch the explicit build CLI."""

    container_type = "custom" if args.container_type == "source" else args.container_type

    build(
        BuildRequest(
            container_type=container_type,
            target_platform=args.platform,
            validation_mode=args.validation,
            registry=args.registry,
            sst_version=args.sst_version,
            sst_elements_version=args.elements_version or args.sst_version,
            mpich_version=args.mpich_version,
            build_ncpus=args.build_ncpus,
            tag_suffix=args.tag_suffix or "latest",
            tag_suffix_set=args.tag_suffix is not None,
            validate_only=args.validate_only,
            cleanup=args.cleanup,
            enable_perf_tracking=args.enable_perf_tracking,
            no_cache=args.no_cache,
            container_engine=args.engine,
            experiment_name=args.experiment_name,
            base_image=args.base_image,
            sst_core_path=args.core_path,
            sst_core_repo=args.core_repo,
            sst_core_ref=args.core_ref,
            sst_elements_repo=args.elements_repo,
            sst_elements_ref=args.elements_ref,
            download_script=args.download_script or os.environ.get("DOWNLOAD_SCRIPT", ""),
        )
    )


def _add_parser(
    subparsers: Any,
    name: str,
    handler: Callable[[argparse.Namespace], object],
    **kwargs: Any,
) -> argparse.ArgumentParser:
    """Create a subparser and attach its handler."""

    parser = subparsers.add_parser(name, **kwargs)
    parser.set_defaults(handler=handler)
    return parser


def _add_local_common_options(parser: argparse.ArgumentParser) -> None:
    """Add options shared by all build subcommands."""

    parser.set_defaults(
        sst_version=DEFAULT_SST_VERSION,
        elements_version=None,
        mpich_version=DEFAULT_MPICH_VERSION,
        build_ncpus=DEFAULT_BUILD_NCPUS,
        enable_perf_tracking=False,
        experiment_name="",
        base_image="",
        core_path="",
        core_repo=DEFAULT_SST_CORE_REPO,
        core_ref="",
        elements_repo="",
        elements_ref="",
    )

    parser.add_argument(
        "--engine",
        choices=container_engine_choices(),
        default=None,
        metavar="ENGINE",
        help="Container engine to use (docker/podman)",
    )
    parser.add_argument(
        "--platform",
        type=_argument_type_with_standard_errors(require_host_platform),
        default=detect_host_platform(),
        metavar="PLATFORM",
        help="Target platform (host platform only; default: auto-detected)",
    )
    parser.add_argument(
        "--registry",
        default="localhost:5000",
        metavar="REGISTRY",
        help="Registry for image tags (default: localhost:5000)",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable build cache")
    parser.add_argument(
        "--validation",
        choices=validation_mode_choices(),
        default="full",
        metavar="MODE",
        help="Validation mode: full, quick, metadata, or none (default: full)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip the build and validate the last built image",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove built images and temporary state after success",
    )
    parser.add_argument(
        "--tag-suffix",
        default=None,
        metavar="SUFFIX",
        help="Tag suffix for generated image tags",
    )


def _add_local_build_resource_options(parser: argparse.ArgumentParser) -> None:
    """Add build options for build resources and dependency versions."""

    parser.add_argument(
        "--mpich-version",
        default=DEFAULT_MPICH_VERSION,
        metavar="VERSION",
        help=f"MPICH version to use (default: {DEFAULT_MPICH_VERSION})",
    )
    parser.add_argument(
        "--build-ncpus",
        default=DEFAULT_BUILD_NCPUS,
        metavar="NUMBER",
        help=f"Number of CPU cores for build (default: {DEFAULT_BUILD_NCPUS})",
    )


def _add_local_release_options(
    parser: argparse.ArgumentParser,
    *,
    include_elements_version: bool,
) -> None:
    """Add release-style build options."""

    parser.add_argument(
        "--sst-version",
        default=DEFAULT_SST_VERSION,
        metavar="VERSION",
        help=f"SST version to use (default: {DEFAULT_SST_VERSION})",
    )
    _add_local_build_resource_options(parser)
    if include_elements_version:
        parser.add_argument(
            "--elements-version",
            default=None,
            metavar="VERSION",
            help="SST-elements version override for full builds",
        )
    parser.add_argument(
        "--enable-perf-tracking",
        action="store_true",
        help="Enable SST performance tracking",
    )


def _add_local_custom_options(parser: argparse.ArgumentParser) -> None:
    """Add source-build-specific options to a build subcommand."""

    parser.add_argument(
        "--core-repo",
        default=DEFAULT_SST_CORE_REPO,
        metavar="URL",
        help=f"SST-core repository URL (default: {DEFAULT_SST_CORE_REPO})",
    )
    local_source_group = parser.add_mutually_exclusive_group()
    local_source_group.add_argument(
        "--core-path",
        default="",
        metavar="PATH",
        help="Local SST-core checkout to copy into the build context",
    )
    local_source_group.add_argument(
        "--core-ref",
        default="",
        metavar="REF",
        help="SST-core branch, tag, or commit SHA",
    )
    parser.add_argument(
        "--elements-repo",
        default="",
        metavar="URL",
        help="SST-elements repository URL",
    )
    parser.add_argument(
        "--elements-ref",
        default="",
        metavar="REF",
        help="SST-elements branch, tag, or commit SHA",
    )
    _add_local_build_resource_options(parser)
    parser.add_argument(
        "--enable-perf-tracking",
        action="store_true",
        help="Enable SST performance tracking",
    )


def _add_local_experiment_options(parser: argparse.ArgumentParser) -> None:
    """Add experiment-specific options to a build subcommand."""

    parser.add_argument(
        "--experiment-name",
        required=True,
        default="",
        metavar="NAME",
        help="Experiment name for experiment container builds",
    )
    parser.add_argument(
        "--base-image",
        default="",
        metavar="IMAGE",
        help="Base image for experiment builds",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""

    parser = argparse.ArgumentParser(prog="sst-container-factory", allow_abbrev=False)
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    download_parser = _add_parser(subparsers, "download-sources", _handle_download_sources)
    download_parser.add_argument("--sst-version", metavar="VERSION", help="SST-core version to download")
    download_parser.add_argument(
        "--sst-elements-version",
        metavar="VERSION",
        help="SST-elements version to download",
    )
    download_parser.add_argument("--mpich-version", metavar="VERSION", help="MPICH version to download")
    download_parser.add_argument("--force", "-f", action="store_true", help="Re-download existing files")
    download_parser.add_argument("sst_version_arg", nargs="?")
    download_parser.add_argument("mpich_version_arg", nargs="?")

    local_build_parser = _add_parser(
        subparsers,
        "build",
        lambda _args: None,
        description=(
            "Build SST images using subcommands for the supported source and image types."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Container types:
  core        Build SST-core only
  full        Build SST-core + SST-elements
  dev         Build the development image
  source      Build from a local checkout or selected repository/ref
  experiment  Build an experiment container

Examples:
  %(prog)s core
  %(prog)s full --sst-version 15.1.0
  %(prog)s full --sst-version 15.1.2 --elements-version 15.1.0
  %(prog)s core --enable-perf-tracking
  %(prog)s source --core-repo https://github.com/sstsimulator/sst-core.git --core-ref main
  %(prog)s source --core-path /path/to/sst-core --tag-suffix local-core
  %(prog)s experiment --experiment-name phold-example
  %(prog)s core --validation quick""",
    )
    local_build_subparsers = local_build_parser.add_subparsers(
        dest="container_type",
        required=True,
        metavar="CONTAINER_TYPE",
    )

    local_core_parser = _add_parser(
        local_build_subparsers,
        "core",
        _handle_build,
        help="Build SST-core only",
        description="Build an SST-core release image locally.",
    )
    _add_local_common_options(local_core_parser)
    _add_local_release_options(local_core_parser, include_elements_version=False)

    local_full_parser = _add_parser(
        local_build_subparsers,
        "full",
        _handle_build,
        help="Build SST-core + SST-elements",
        description="Build an SST full release image locally.",
    )
    _add_local_common_options(local_full_parser)
    _add_local_release_options(local_full_parser, include_elements_version=True)

    local_dev_parser = _add_parser(
        local_build_subparsers,
        "dev",
        _handle_build,
        help="Build the development image",
        description="Build the development image locally.",
    )
    _add_local_common_options(local_dev_parser)
    _add_local_build_resource_options(local_dev_parser)

    local_custom_parser = _add_parser(
        local_build_subparsers,
        "source",
        _handle_build,
        help="Build from a local checkout or selected repository/ref",
        description="Build an SST image from a local checkout or selected repository/ref.",
    )
    _add_local_common_options(local_custom_parser)
    _add_local_custom_options(local_custom_parser)

    local_experiment_parser = _add_parser(
        local_build_subparsers,
        "experiment",
        _handle_build,
        help="Build an experiment container",
        description="Build an experiment image through the build entry point.",
    )
    _add_local_common_options(local_experiment_parser)
    _add_local_experiment_options(local_experiment_parser)

    local_build_parser.add_argument("--download-script", help=argparse.SUPPRESS)

    prepare_workflow_build_parser = _add_parser(
        subparsers,
        "workflow-prepare-build",
        lambda _args: prepare_workflow_build_from_env(),
    )
    del prepare_workflow_build_parser

    validate_container_parser = _add_parser(
        subparsers,
        "workflow-validate-container",
        lambda _args: validate_container_from_env(),
    )
    del validate_container_parser

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the requested orchestration command."""

    normalized_argv = argv if argv is not None else sys.argv[1:]

    parser = build_parser()

    try:
        args = parser.parse_args(normalized_argv)
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.error(f"Unsupported command: {args.command}")
        handler(args)
    except SystemExit as error:
        if error.code == 0:
            return 0
        return 1
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        for line in str(error).splitlines():
            log_error(line)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
