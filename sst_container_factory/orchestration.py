"""Workflow orchestration helpers backed by Python."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .github_actions import end_group, set_output, start_group
from .logging_utils import log_error, log_info, log_success, log_warning


DOCKER_LIBRARY_IMAGES = {
    "ubuntu",
    "alpine",
    "debian",
    "centos",
    "fedora",
    "rocky",
    "almalinux",
    "amazonlinux",
}

REPO_ROOT = Path(__file__).resolve().parent.parent


class OrchestrationError(RuntimeError):
    """Raised when orchestration validation fails."""


@dataclass(frozen=True)
class PrepareImageConfigResult:
    """Resolved image naming patterns for a build."""

    image_prefix: str
    core_full_pattern: str
    dev_custom_pattern: str
    experiment_pattern: str
    default_pattern: str


@dataclass(frozen=True)
class ValidateCustomInputsResult:
    """Resolved build settings for the custom workflow."""

    build_type: str
    tag_suffix: str


@dataclass(frozen=True)
class ValidateExperimentInputsResult:
    """Validated experiment workflow inputs."""

    experiment_exists: bool
    has_containerfile: bool
    resolved_base_image: str
    files_count: int


@dataclass(frozen=True)
class ValidateContainerResult:
    """Validated registry container metadata."""

    image_tag: str
    platform: str
    image_size_mb: int


@dataclass(frozen=True)
class ExperimentBuildResult:
    """Resolved experiment build outputs."""

    image_tag: str
    containerfile_type: str
    containerfile_path: str
    docker_context: str


def detect_container_engine(explicit_engine: str | None = None) -> str:
    """Return the most appropriate container engine available on the host."""

    requested = explicit_engine or os.environ.get("CONTAINER_ENGINE")
    if requested:
        if shutil.which(requested):
            return requested
        raise OrchestrationError(f"Container engine not found: {requested}")

    if os.environ.get("GITHUB_ACTIONS") == "true" and shutil.which("docker"):
        return "docker"

    system_name = platform.system()
    preferred = ["docker", "podman"] if system_name == "Darwin" else ["podman", "docker"]
    for candidate in preferred:
        if shutil.which(candidate):
            return candidate

    raise OrchestrationError("No container engine found")


def inspect_remote_manifest(engine: str, image_ref: str) -> bool:
    """Return whether the container manifest can be resolved."""

    result = subprocess.run(
        [engine, "manifest", "inspect", image_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def resolve_base_image_reference(base_image: str, default_owner: str) -> str:
    """Resolve a short image name into a concrete registry reference."""

    if not base_image:
        raise OrchestrationError("Base image cannot be empty")

    if "/" in base_image:
        return base_image

    library_image = re.split(r"[:@]", base_image, maxsplit=1)[0]
    if library_image in DOCKER_LIBRARY_IMAGES:
        return base_image

    return f"ghcr.io/{default_owner}/{base_image}"


def sanitize_tag_suffix(raw_value: str) -> str:
    """Sanitize a git ref into a container tag suffix."""

    sanitized = raw_value.replace("/", "-")
    return sanitized[:50]


def platform_to_arch(target_platform: str) -> str:
    """Convert a Linux platform string into a short architecture label."""

    mapping = {
        "linux/amd64": "amd64",
        "linux/arm64": "arm64",
    }
    try:
        return mapping[target_platform]
    except KeyError as error:
        raise OrchestrationError(f"Invalid platform: {target_platform}") from error


def generate_experiment_image_tag(
    registry: str, tag_suffix: str, arch: str, experiment_name: str
) -> str:
    """Generate the canonical experiment image tag."""

    return f"{registry}/{experiment_name}:{tag_suffix}-{arch}"


def prepare_image_config_from_env() -> PrepareImageConfigResult:
    """Compute workflow image naming outputs from environment variables."""

    container_type = os.environ.get("CONTAINER_TYPE", "")
    image_prefix = os.environ.get("IMAGE_PREFIX", "")
    tag_suffix = os.environ.get("TAG_SUFFIX", "")
    registry = os.environ.get("REGISTRY", "ghcr.io")
    enable_perf_tracking = os.environ.get("ENABLE_PERF_TRACKING", "false")
    experiment_name = os.environ.get("EXPERIMENT_NAME", "")

    if not container_type:
        raise OrchestrationError("CONTAINER_TYPE is required")
    if not image_prefix:
        raise OrchestrationError("IMAGE_PREFIX is required")
    if not tag_suffix:
        raise OrchestrationError("TAG_SUFFIX is required")

    start_group("Prepare Image Configuration")
    log_info(f"Container type:      {container_type}")
    log_info(f"Image prefix:        {image_prefix}")
    log_info(f"Tag suffix:          {tag_suffix}")
    log_info(f"Registry:            {registry}")
    log_info(f"Perf tracking:       {enable_perf_tracking}")

    original_image_prefix = image_prefix
    if enable_perf_tracking == "true" and container_type in {"core", "full", "custom"}:
        image_prefix = f"{image_prefix}-perf-track"
        log_info(f"Perf tracking enabled: image prefix modified to {image_prefix}")

    result = PrepareImageConfigResult(
        image_prefix=image_prefix,
        core_full_pattern=f"{registry}/{image_prefix}-{container_type}:{tag_suffix}",
        dev_custom_pattern=f"{registry}/{image_prefix}:{tag_suffix}",
        experiment_pattern=f"{registry}/{original_image_prefix}/{experiment_name}:{tag_suffix}",
        default_pattern=f"{registry}/{image_prefix}:{tag_suffix}",
    )

    log_info("Computed patterns:")
    log_info(f"  core_full_pattern:   {result.core_full_pattern}")
    log_info(f"  dev_custom_pattern:  {result.dev_custom_pattern}")
    log_info(f"  experiment_pattern:  {result.experiment_pattern}")
    log_info(f"  default_pattern:     {result.default_pattern}")
    end_group()

    set_output("image_prefix", result.image_prefix)
    set_output("core_full_pattern", result.core_full_pattern)
    set_output("dev_custom_pattern", result.dev_custom_pattern)
    set_output("experiment_pattern", result.experiment_pattern)
    set_output("default_pattern", result.default_pattern)
    log_success("Image configuration complete")
    return result


def validate_custom_inputs_from_env() -> ValidateCustomInputsResult:
    """Validate build-custom workflow inputs from environment variables."""

    core_ref = os.environ.get("CORE_REF", "")
    elements_repo = os.environ.get("ELEMENTS_REPO", "")
    elements_ref = os.environ.get("ELEMENTS_REF", "")
    image_tag = os.environ.get("IMAGE_TAG", "")

    if not core_ref:
        raise OrchestrationError("CORE_REF (sst_core_ref input) is required")

    start_group("Validate Custom Build Inputs")
    if elements_repo:
        if not elements_ref:
            raise OrchestrationError(
                "SST-elements ref (ELEMENTS_REF) is required when elements_repo is provided"
            )
        build_type = "full"
        log_info("Build type: full (core + elements)")
    else:
        build_type = "core"
        log_info("Build type: core only")

    tag_suffix = image_tag or sanitize_tag_suffix(core_ref)
    if image_tag:
        log_info(f"Tag suffix: {tag_suffix} (explicit)")
    else:
        log_info(f"Tag suffix: {tag_suffix} (derived from core ref)")
    end_group()

    result = ValidateCustomInputsResult(build_type=build_type, tag_suffix=tag_suffix)
    set_output("build_type", result.build_type)
    set_output("tag_suffix", result.tag_suffix)
    log_success(
        f"Input validation complete: build_type={result.build_type}, tag_suffix={result.tag_suffix}"
    )
    return result


def validate_experiment_inputs_from_env() -> ValidateExperimentInputsResult:
    """Validate build-experiment workflow inputs from environment variables."""

    experiment_name = os.environ.get("EXPERIMENT_NAME", "")
    base_image = os.environ.get("BASE_IMAGE", "sst-core:latest")
    repo_owner = os.environ.get("REPO_OWNER", os.environ.get("USER", ""))
    container_engine = detect_container_engine(os.environ.get("CONTAINER_ENGINE"))

    if not experiment_name:
        raise OrchestrationError("EXPERIMENT_NAME is required")

    start_group("Validate Experiment Inputs")
    log_info(f"Experiment name: {experiment_name}")

    experiment_dir = REPO_ROOT / experiment_name
    if not experiment_dir.is_dir():
        log_error(f"Experiment directory '{experiment_name}' does not exist")
        set_output("experiment_exists", "false")
        end_group()
        return ValidateExperimentInputsResult(
            experiment_exists=False,
            has_containerfile=False,
            resolved_base_image="",
            files_count=0,
        )

    set_output("experiment_exists", "true")
    log_info(f"Experiment directory found: {experiment_name}")

    has_containerfile = (experiment_dir / "Containerfile").is_file()
    resolved_base_image = ""
    if has_containerfile:
        log_info("Custom Containerfile found in experiment directory")
        set_output("has_containerfile", "true")
        set_output("resolved_base_image", "")
    else:
        log_info("No custom Containerfile - using template Containerfile.experiment")
        set_output("has_containerfile", "false")
        resolved_base_image = resolve_base_image_reference(base_image, repo_owner)
        log_info(f"Resolved base image: {resolved_base_image}")
        set_output("resolved_base_image", resolved_base_image)
        if not inspect_remote_manifest(container_engine, resolved_base_image):
            raise OrchestrationError(
                "Base image not found or not accessible: "
                f"{resolved_base_image}\n"
                "For images in this repository, use format: sst-core:latest\n"
                "For external images, use a full path: ghcr.io/username/image:tag"
            )
        log_success(f"Base image is accessible: {resolved_base_image}")

    files_count = sum(1 for path in experiment_dir.rglob("*") if path.is_file())
    log_info(f"Files in experiment directory: {files_count}")
    set_output("files_count", str(files_count))
    end_group()
    log_success(f"Experiment validation complete: {experiment_name}")
    return ValidateExperimentInputsResult(
        experiment_exists=True,
        has_containerfile=has_containerfile,
        resolved_base_image=resolved_base_image,
        files_count=files_count,
    )


def _run_command(command: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command and optionally capture stdout."""

    return subprocess.run(
        command,
        capture_output=capture_output,
        text=True,
        check=False,
    )


def _inspect_image_json(engine: str, image_tag: str) -> dict:
    """Inspect an image and return the decoded JSON metadata."""

    inspect_result = _run_command([engine, "image", "inspect", image_tag], capture_output=True)
    if inspect_result.returncode != 0:
        raise OrchestrationError(f"Failed to inspect image metadata: {image_tag}")

    try:
        payload = json.loads(inspect_result.stdout)
    except json.JSONDecodeError as error:
        raise OrchestrationError(f"Invalid image metadata returned for {image_tag}") from error

    if not payload:
        raise OrchestrationError(f"Image metadata not found: {image_tag}")

    return payload[0]


def quick_validate_image(engine: str, image_tag: str) -> None:
    """Perform lightweight validation without creating a container."""

    log_info(f"Quick validation of {image_tag}")
    metadata = _inspect_image_json(engine, image_tag)
    image_size_mb = int(metadata.get("Size", 0)) // 1024 // 1024
    log_success("Image exists")
    log_info(f"Image size: {image_size_mb}MB")
    if not metadata.get("Config"):
        raise OrchestrationError("Image inspection failed")
    log_success("Image inspection passed")
    log_success("Quick validation passed")


def metadata_validate_image(engine: str, image_tag: str, max_size_mb: int) -> None:
    """Perform metadata-only validation without running the container."""

    log_info(f"No-exec validation of {image_tag}")
    metadata = _inspect_image_json(engine, image_tag)
    image_size_mb = int(metadata.get("Size", 0)) // 1024 // 1024

    log_success("Image exists")
    log_info(f"Image size: {image_size_mb}MB")
    if image_size_mb > max_size_mb:
        raise OrchestrationError(f"Image size {image_size_mb}MB exceeds limit {max_size_mb}MB")
    log_success("Image size check passed")

    architecture = metadata.get("Architecture", "unknown")
    log_info(f"Image architecture: {architecture}")

    config_env = metadata.get("Config", {}).get("Env", []) or []
    joined_env = "\n".join(config_env).lower()
    if "path" in joined_env and ("sst" in joined_env or "mpi" in joined_env):
        log_success("Expected environment variables found")
    else:
        log_warning("Expected SST/MPI environment variables not clearly visible")

    layers = metadata.get("RootFS", {}).get("Layers")
    if layers:
        log_success("Image layers structure verified")
    else:
        log_warning("Could not verify image layers")

    log_success("No-exec validation passed")


def _validate_container(
    container_engine: str,
    image_tag: str,
    target_platform: str,
    max_size_mb: int,
) -> ValidateContainerResult:
    """Validate a pulled container image using explicit parameters."""

    start_group("Validate Container")
    log_info(f"Image:    {image_tag}")
    log_info(f"Platform: {target_platform}")
    log_info(f"Max size: {max_size_mb} MB")
    log_info(f"Engine:   {container_engine}")

    log_info("Pulling image...")
    pull_result = _run_command([container_engine, "pull", image_tag])
    if pull_result.returncode != 0:
        end_group()
        raise OrchestrationError(f"Failed to pull image: {image_tag}")

    inspect_result = _run_command(
        [container_engine, "image", "inspect", image_tag, "--format={{.Size}}"],
        capture_output=True,
    )
    if inspect_result.returncode != 0:
        end_group()
        raise OrchestrationError(f"Failed to inspect image size: {image_tag}")

    image_size_bytes_raw = inspect_result.stdout.strip()
    try:
        image_size_mb = int(image_size_bytes_raw) // 1024 // 1024
    except ValueError as error:
        end_group()
        raise OrchestrationError(
            f"Invalid image size reported for {image_tag}: {image_size_bytes_raw}"
        ) from error

    log_info(f"Image size: {image_size_mb} MB")
    if image_size_mb > max_size_mb:
        end_group()
        raise OrchestrationError(
            "Image size "
            f"({image_size_mb} MB) exceeds maximum allowed size ({max_size_mb} MB)"
        )

    create_result = _run_command(
        [container_engine, "create", "--platform", target_platform, image_tag, "/bin/true"],
        capture_output=True,
    )
    if create_result.returncode != 0:
        end_group()
        raise OrchestrationError("Failed to instantiate container")

    container_id = create_result.stdout.strip()
    if not container_id:
        end_group()
        raise OrchestrationError("Failed to instantiate container")

    _run_command([container_engine, "rm", container_id], capture_output=True)
    log_success(f"Container validation passed: {image_size_mb} MB, {target_platform}")
    end_group()
    return ValidateContainerResult(
        image_tag=image_tag,
        platform=target_platform,
        image_size_mb=image_size_mb,
    )


def _detect_experiment_containerfile_type(
    experiment_name: str,
    base_image: str,
    container_engine: str,
) -> str:
    """Determine whether an experiment uses a custom or template Containerfile."""

    log_info("Validating experiment configuration...")
    experiment_dir = REPO_ROOT / experiment_name
    if not experiment_dir.is_dir():
        raise OrchestrationError(f"Experiment directory '{experiment_name}' not found")

    log_info(f"Experiment directory exists: {experiment_name}")
    if (experiment_dir / "Containerfile").is_file():
        log_info("Using custom Containerfile from experiment directory")
        return "custom"

    log_info("Using template Containerfile.experiment")
    if base_image:
        resolved_image = resolve_base_image_reference(base_image, os.environ.get("USER", ""))
        log_info(f"Resolved base image: {resolved_image}")
        if not inspect_remote_manifest(container_engine, resolved_image):
            raise OrchestrationError(
                f"Base image not found: {resolved_image}\n"
                "For images in this repository, use format: sst-core:latest\n"
                "For external images, use full path: ghcr.io/username/image:tag"
            )
        log_info("Base image is accessible")

    return "template"


def experiment_build_from_env() -> ExperimentBuildResult:
    """Execute the experiment build path from normalized environment variables."""

    experiment_name = os.environ.get("EXPERIMENT_NAME", "")
    base_image = os.environ.get("BASE_IMAGE", "")
    build_platforms = os.environ.get("BUILD_PLATFORMS", "")
    registry = os.environ.get("REGISTRY", "localhost:5000")
    tag_suffix = os.environ.get("TAG_SUFFIX", "latest")
    validation_mode = os.environ.get("VALIDATION_MODE", "full")
    no_cache = os.environ.get("NO_CACHE", "false") == "true"
    container_engine = detect_container_engine(os.environ.get("CONTAINER_ENGINE"))
    build_args = [line for line in os.environ.get("BUILD_ARGS_SERIALIZED", "").splitlines() if line]

    if not experiment_name:
        raise OrchestrationError("Experiment name is required")
    if not build_platforms:
        raise OrchestrationError("BUILD_PLATFORMS is required")

    log_info("Starting experiment container build...")
    containerfile_type = _detect_experiment_containerfile_type(
        experiment_name,
        base_image,
        container_engine,
    )

    experiment_dir = REPO_ROOT / experiment_name
    if containerfile_type == "custom":
        containerfile_path = experiment_dir / "Containerfile"
        docker_context = experiment_dir
    else:
        containerfile_path = REPO_ROOT / "Containerfiles" / "Containerfile.experiment"
        docker_context = experiment_dir
        if base_image:
            resolved_base_image = resolve_base_image_reference(base_image, os.environ.get("USER", ""))
            build_args = [*build_args, f"BASE_IMAGE={resolved_base_image}"]

    arch = platform_to_arch(build_platforms)
    tag_name = generate_experiment_image_tag(registry, tag_suffix, arch, experiment_name)

    log_info("Configuration:")
    log_info(f"  Experiment: {experiment_name}")
    log_info("  Container type: experiment")
    log_info(f"  Containerfile type: {containerfile_type}")
    log_info(f"  Containerfile path: {containerfile_path}")
    log_info(f"  Docker context: {docker_context}")
    log_info(f"  Tag: {tag_name}")
    log_info(f"  Platforms: {build_platforms}")
    log_info(f"  Validation: {validation_mode}")
    if build_args:
        log_info("  Build args:")
        for build_arg in build_args:
            log_info(f"    {build_arg}")

    build_command = [
        container_engine,
        "build",
        "--platform",
        build_platforms,
        "-f",
        str(containerfile_path),
        "-t",
        tag_name,
    ]
    if no_cache:
        build_command.append("--no-cache")
    for build_arg in build_args:
        build_command.extend(["--build-arg", build_arg])
    build_command.append(str(docker_context))

    start_group("Container Build")
    build_result = _run_command(build_command)
    end_group()
    if build_result.returncode != 0:
        raise OrchestrationError("Experiment container build failed")

    log_info(f"Container built successfully: {tag_name}")

    max_size_mb = 8192
    if validation_mode == "none":
        log_info("Skipping validation (validation mode: none)")
    elif validation_mode == "quick":
        log_info("Running container validation...")
        quick_validate_image(container_engine, tag_name)
        log_success("Quick container validation passed")
    elif validation_mode == "metadata":
        log_info("Running container validation...")
        metadata_validate_image(container_engine, tag_name, max_size_mb)
        log_success("Metadata-only container validation passed")
    elif validation_mode == "full":
        log_info("Running container validation...")
        _validate_container(container_engine, tag_name, build_platforms, max_size_mb)
        log_success("Full container validation passed")
    else:
        raise OrchestrationError(f"Unsupported validation mode: {validation_mode}")

    log_info("Experiment build completed successfully!")
    return ExperimentBuildResult(
        image_tag=tag_name,
        containerfile_type=containerfile_type,
        containerfile_path=str(containerfile_path),
        docker_context=str(docker_context),
    )


def validate_container_from_env() -> ValidateContainerResult:
    """Validate a pulled container image using environment variables."""

    image_tag = os.environ.get("IMAGE_TAG", "")
    target_platform = os.environ.get("PLATFORM", "")
    max_size_mb = int(os.environ.get("MAX_SIZE_MB", "2048"))
    container_engine = detect_container_engine(os.environ.get("CONTAINER_ENGINE"))

    if not image_tag:
        raise OrchestrationError("IMAGE_TAG is required")
    if not target_platform:
        raise OrchestrationError("PLATFORM is required")

    return _validate_container(container_engine, image_tag, target_platform, max_size_mb)
