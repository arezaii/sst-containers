"""Command-line entry points for the Python transition layer."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from .adapters import (
    prepare_image_config_from_env,
    prepare_workflow_build_from_env,
    validate_container_from_env,
    validate_custom_inputs_from_env,
    validate_experiment_inputs_from_env,
)

from .logging_utils import log_error
from .orchestration import (
    custom_build,
    CustomBuildRequest,
    DEFAULT_BUILD_NCPUS,
    DEFAULT_SST_CORE_REPO,
    DEFAULT_MPICH_VERSION,
    DEFAULT_SST_VERSION,
    detect_host_platform,
    download_tarballs,
    experiment_build,
    ExperimentBuildRequest,
    local_build,
    LocalBuildRequest,
    require_host_platform,
    require_single_host_platform,
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


def _handle_custom_build(args: argparse.Namespace) -> None:
    """Dispatch the explicit custom-build CLI."""

    custom_build(
        CustomBuildRequest(
            target_platform=args.platform,
            tag_suffix=args.tag_suffix,
            sst_core_repo=args.core_repo,
            sst_core_path=args.core_path,
            sst_core_ref=args.core_ref,
            sst_elements_repo=args.elements_repo,
            sst_elements_ref=args.elements_ref,
            mpich_version=args.mpich_version,
            build_ncpus=args.build_ncpus,
            registry=args.registry,
            enable_perf_tracking=args.enable_perf_tracking,
            no_cache=args.no_cache,
            cleanup=args.cleanup,
            validation_mode=args.validation,
            container_engine=args.engine,
            github_actions_mode=args.github_actions_mode,
        )
    )


def _handle_download_tarballs(args: argparse.Namespace) -> None:
    """Dispatch the tarball downloader CLI."""

    explicit_download_selection = any(
        [
            args.sst_version is not None,
            args.sst_elements_version is not None,
            args.mpich_version is not None,
        ]
    )
    download_tarballs(
        sst_version=args.sst_version or args.sst_version_arg or DEFAULT_SST_VERSION,
        sst_elements_version=args.sst_elements_version,
        mpich_version=args.mpich_version or args.mpich_version_arg or DEFAULT_MPICH_VERSION,
        download_mpich=(args.mpich_version is not None) if explicit_download_selection else True,
        download_sst_core=(args.sst_version is not None) if explicit_download_selection else True,
        download_sst_elements=(args.sst_elements_version is not None) if explicit_download_selection else True,
        force_mode=args.force,
    )


def _handle_experiment_build(args: argparse.Namespace) -> None:
    """Dispatch the explicit experiment-build CLI."""

    experiment_build(
        ExperimentBuildRequest(
            experiment_name=args.experiment_name,
            base_image=args.base_image,
            build_platforms=args.platforms,
            registry=args.registry,
            tag_suffix=args.tag_suffix,
            validation_mode=args.validation,
            no_cache=args.no_cache,
            container_engine=args.engine,
            build_args=tuple(args.build_arg),
        )
    )


def _handle_local_build(args: argparse.Namespace) -> None:
    """Dispatch the explicit local-build CLI."""

    local_build(
        LocalBuildRequest(
            container_type=args.container_type,
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
    """Add options shared by all local-build subcommands."""

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
    """Add local-build options for build resources and dependency versions."""

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
    """Add release-style local-build options."""

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
    """Add custom-build-specific options to a local-build subcommand."""

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
    """Add experiment-build-specific options to a local-build subcommand."""

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

    custom_build_parser = _add_parser(
        subparsers,
        "custom-build",
        _handle_custom_build,
        description="Build SST containers from arbitrary repositories and refs.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Validation modes:
  full      Complete validation including runtime checks
  quick     Fast validation without full runtime coverage
  metadata  Validate image metadata without executing the container
  none      Skip validation

Examples:
  %(prog)s --core-ref main
  %(prog)s --core-path /path/to/sst-core --tag-suffix local-core
  %(prog)s --core-ref v15.1.0 --elements-repo https://github.com/custom/sst-elements.git --elements-ref develop
  %(prog)s --core-ref main --enable-perf-tracking --validation quick""",
    )
    required_group = custom_build_parser.add_argument_group("Required options")
    custom_source_group = required_group.add_mutually_exclusive_group()
    custom_source_group.add_argument(
        "--core-path",
        default="",
        metavar="PATH",
        help="Local SST-core checkout to copy into the build context",
    )
    custom_source_group.add_argument(
        "--core-ref",
        default="",
        metavar="REF",
        help="SST-core branch, tag, or commit SHA",
    )
    custom_options_group = custom_build_parser.add_argument_group("Options")
    custom_options_group.add_argument(
        "--core-repo",
        default=DEFAULT_SST_CORE_REPO,
        metavar="URL",
        help=f"SST-core repository URL (default: {DEFAULT_SST_CORE_REPO})",
    )
    custom_options_group.add_argument(
        "--elements-repo",
        default="",
        metavar="URL",
        help="SST-elements repository URL",
    )
    custom_options_group.add_argument(
        "--elements-ref",
        default="",
        metavar="REF",
        help="SST-elements branch, tag, or commit SHA",
    )
    custom_options_group.add_argument(
        "--mpich-version",
        default=DEFAULT_MPICH_VERSION,
        metavar="VERSION",
        help=f"MPICH version to use (default: {DEFAULT_MPICH_VERSION})",
    )
    custom_options_group.add_argument(
        "--engine",
        choices=container_engine_choices(),
        default=None,
        metavar="ENGINE",
        help="Container engine to use (docker/podman)",
    )
    custom_options_group.add_argument(
        "--platform",
        type=_argument_type_with_standard_errors(require_host_platform),
        default=detect_host_platform(),
        metavar="PLATFORM",
        help="Target platform (host platform only; default: auto-detected)",
    )
    custom_options_group.add_argument(
        "--build-ncpus",
        default=DEFAULT_BUILD_NCPUS,
        metavar="NUMBER",
        help=f"Number of CPU cores for build (default: {DEFAULT_BUILD_NCPUS})",
    )
    custom_options_group.add_argument(
        "--registry",
        default="localhost:5000",
        metavar="REGISTRY",
        help="Registry for image tags (default: localhost:5000)",
    )
    custom_options_group.add_argument(
        "--tag-suffix",
        default="",
        metavar="SUFFIX",
        help="Tag suffix for generated image tags",
    )
    custom_options_group.add_argument(
        "--validation",
        choices=validation_mode_choices(),
        default="none",
        metavar="MODE",
        help="Validation mode: full, quick, metadata, or none (default: none)",
    )
    custom_options_group.add_argument(
        "--enable-perf-tracking",
        action="store_true",
        help="Enable SST performance tracking",
    )
    custom_options_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable build cache",
    )
    custom_options_group.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove built images and temporary state after success",
    )
    custom_options_group.add_argument("--github-actions-mode", action="store_true", help=argparse.SUPPRESS)

    download_parser = _add_parser(subparsers, "download-tarballs", _handle_download_tarballs)
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

    experiment_build_parser = _add_parser(
        subparsers,
        "experiment-build",
        _handle_experiment_build,
        description="Build experiment containers for SST with optional custom Containerfiles.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Validation modes:
  full      Complete validation including size check and functionality tests
  quick     Basic validation without execution tests
  metadata  Validate image metadata without executing the container
  none      Skip validation entirely

Performance tracking:
  Experiment containers inherit SST performance tracking from their base image.
  Use a performance-tracking-enabled base image when you need those capabilities.

Examples:
  %(prog)s phold-example
  %(prog)s --base-image sst-core:latest tcl-test-experiment
  %(prog)s --registry myregistry.io/user --no-cache ahp-graph""",
    )
    experiment_build_parser.add_argument(
        "--base-image",
        default="sst-core:latest",
        metavar="IMAGE",
        help="Base image for experiment builds",
    )
    experiment_build_parser.add_argument(
        "--engine",
        choices=container_engine_choices(),
        default=None,
        metavar="ENGINE",
        help="Container engine to use (docker/podman)",
    )
    experiment_build_parser.add_argument(
        "--registry",
        default="localhost:5000",
        metavar="REGISTRY",
        help="Registry for image tags (default: localhost:5000)",
    )
    experiment_build_parser.add_argument(
        "--tag-suffix",
        default="latest",
        metavar="SUFFIX",
        help="Tag suffix for generated image tags (default: latest)",
    )
    experiment_build_parser.add_argument(
        "--platforms",
        type=_argument_type_with_standard_errors(require_single_host_platform),
        default=detect_host_platform(),
        metavar="PLATFORMS",
        help="Build platform (single host platform only; default: auto-detected)",
    )
    experiment_build_parser.add_argument("--no-cache", action="store_true", help="Disable build cache")
    experiment_build_parser.add_argument(
        "--build-arg",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional build argument (repeatable)",
    )
    experiment_build_parser.add_argument(
        "--validation",
        choices=validation_mode_choices(),
        default="full",
        metavar="MODE",
        help="Validation mode: full, quick, metadata, or none (default: full)",
    )
    experiment_build_parser.add_argument(
        "experiment_name",
        metavar="EXPERIMENT_NAME",
        help="Experiment name (required) - must match existing directory",
    )

    local_build_parser = _add_parser(
        subparsers,
        "local-build",
        lambda _args: None,
        description=(
            "Build SST images locally using subcommands for the supported build types."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Container types:
  core        Build SST-core only
  full        Build SST-core + SST-elements
  dev         Build the development image
  custom      Build from custom repositories and refs
  experiment  Build an experiment container

Examples:
  %(prog)s core
  %(prog)s full --sst-version 15.1.0
  %(prog)s full --sst-version 15.1.2 --elements-version 15.1.0
  %(prog)s core --enable-perf-tracking
  %(prog)s custom --core-repo https://github.com/sstsimulator/sst-core.git --core-ref main
  %(prog)s custom --core-path /path/to/sst-core --tag-suffix local-core
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
        _handle_local_build,
        help="Build SST-core only",
        description="Build an SST-core release image locally.",
    )
    _add_local_common_options(local_core_parser)
    _add_local_release_options(local_core_parser, include_elements_version=False)

    local_full_parser = _add_parser(
        local_build_subparsers,
        "full",
        _handle_local_build,
        help="Build SST-core + SST-elements",
        description="Build an SST full release image locally.",
    )
    _add_local_common_options(local_full_parser)
    _add_local_release_options(local_full_parser, include_elements_version=True)

    local_dev_parser = _add_parser(
        local_build_subparsers,
        "dev",
        _handle_local_build,
        help="Build the development image",
        description="Build the development image locally.",
    )
    _add_local_common_options(local_dev_parser)
    _add_local_build_resource_options(local_dev_parser)

    local_custom_parser = _add_parser(
        local_build_subparsers,
        "custom",
        _handle_local_build,
        help="Build from custom repositories and refs",
        description="Build a local custom SST image.",
    )
    _add_local_common_options(local_custom_parser)
    _add_local_custom_options(local_custom_parser)

    local_experiment_parser = _add_parser(
        local_build_subparsers,
        "experiment",
        _handle_local_build,
        help="Build an experiment container",
        description="Build an experiment image through the local-build entry point.",
    )
    _add_local_common_options(local_experiment_parser)
    _add_local_experiment_options(local_experiment_parser)

    local_build_parser.add_argument("--download-script", help=argparse.SUPPRESS)

    prepare_image_config_parser = _add_parser(
        subparsers,
        "prepare-image-config",
        lambda _args: prepare_image_config_from_env(),
    )
    del prepare_image_config_parser

    prepare_workflow_build_parser = _add_parser(
        subparsers,
        "prepare-workflow-build",
        lambda _args: prepare_workflow_build_from_env(),
    )
    del prepare_workflow_build_parser

    validate_container_parser = _add_parser(
        subparsers,
        "validate-container",
        lambda _args: validate_container_from_env(),
    )
    del validate_container_parser

    validate_custom_inputs_parser = _add_parser(
        subparsers,
        "validate-custom-inputs",
        lambda _args: validate_custom_inputs_from_env(),
    )
    del validate_custom_inputs_parser

    validate_experiment_inputs_parser = _add_parser(
        subparsers,
        "validate-experiment-inputs",
        lambda _args: validate_experiment_inputs_from_env(),
    )
    del validate_experiment_inputs_parser

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
