"""Workflow orchestration helpers backed by Python."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
import platform
import re
import ssl
import shutil
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .build_spec import (
    BuildSourceSpec,
    BuildSpec,
    PlatformBuildSpec,
    PublicationSpec,
    SourceDownloadSpec,
    VerificationSpec,
    WorkflowBakePlan,
    WorkflowBakeTargetSpec,
)
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
DEFAULT_REGISTRY = "localhost:5000"
DEFAULT_MPICH_VERSION = "4.0.2"
DEFAULT_BUILD_NCPUS = "4"
DEFAULT_SST_VERSION = "15.1.2"
DEFAULT_SST_CORE_REPO = "https://github.com/sstsimulator/sst-core.git"
DEFAULT_SST_ELEMENTS_REPO = "https://github.com/sstsimulator/sst-elements.git"
VALID_SST_VERSIONS = (
    "14.0.0",
    "14.1.0",
    "15.0.0",
    "15.1.0",
    "15.1.1",
    "15.1.2",
)
DEFAULT_SIZE_LIMITS_MB = {
    "core": 2048,
    "full": 4096,
    "dev": 4096,
    "custom": 4096,
    "experiment": 8192,
}
LOCAL_SOURCE_STAGE_ROOT_REL = ".build-contexts"
LOCAL_SST_CORE_STAGE_REL = f"{LOCAL_SOURCE_STAGE_ROOT_REL}/sst-core-input"
LOCAL_SST_CORE_CONTEXT_NAME = "sst_core_input"
LOCAL_SST_CORE_SOURCE_STAGE_ARG = "SST_CORE_SOURCE_STAGE=sst-core-local-source"


class OrchestrationError(RuntimeError):
    """Raised when orchestration runtime operations fail."""


@dataclass(frozen=True)
class PrepareImageConfigResult:
    """Resolved image naming patterns for a build."""

    image_prefix: str
    core_full_pattern: str
    dev_custom_pattern: str
    experiment_pattern: str
    default_pattern: str


@dataclass(frozen=True)
class ValidateSourceInputsResult:
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


@dataclass(frozen=True)
class ExperimentBuildRequest:
    """Explicit experiment build inputs."""

    experiment_name: str
    build_platforms: str
    registry: str = DEFAULT_REGISTRY
    tag_suffix: str = "latest"
    validation_mode: str = "full"
    no_cache: bool = False
    base_image: str = ""
    container_engine: str | None = None
    build_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class DownloadSourcesResult:
    """Resolved tarball download outputs."""

    requested_files: tuple[str, ...]
    total_size_mb: int
    destination_dir: str


@dataclass(frozen=True)
class SourceBuildResult:
    """Resolved source build outputs."""

    image_tag: str
    build_type: str
    image_size_mb: int


@dataclass(frozen=True)
class SourceBuildRequest:
    """Explicit source build inputs."""

    target_platform: str
    tag_suffix: str
    sst_core_ref: str = ""
    sst_core_repo: str = DEFAULT_SST_CORE_REPO
    sst_core_path: str = ""
    sst_elements_repo: str = ""
    sst_elements_ref: str = ""
    mpich_version: str = DEFAULT_MPICH_VERSION
    build_ncpus: str = DEFAULT_BUILD_NCPUS
    registry: str = DEFAULT_REGISTRY
    enable_perf_tracking: bool = False
    no_cache: bool = False
    cleanup: bool = False
    validation_mode: str = "none"
    container_engine: str | None = None
    github_actions_mode: bool = False


@dataclass(frozen=True)
class BuildResult:
    """Resolved build entrypoint outputs."""

    image_tag: str
    container_type: str
    image_size_mb: int | None


@dataclass(frozen=True)
class BuildRequest:
    """Explicit build entrypoint inputs."""

    container_type: str
    target_platform: str
    validation_mode: str = "full"
    registry: str = DEFAULT_REGISTRY
    sst_version: str = DEFAULT_SST_VERSION
    sst_elements_version: str = DEFAULT_SST_VERSION
    mpich_version: str = DEFAULT_MPICH_VERSION
    build_ncpus: str = DEFAULT_BUILD_NCPUS
    tag_suffix: str = "latest"
    tag_suffix_set: bool = False
    validate_only: bool = False
    cleanup: bool = False
    enable_perf_tracking: bool = False
    no_cache: bool = False
    container_engine: str | None = None
    experiment_name: str = ""
    base_image: str = ""
    sst_core_path: str = ""
    sst_core_repo: str = DEFAULT_SST_CORE_REPO
    sst_core_ref: str = ""
    sst_elements_repo: str = ""
    sst_elements_ref: str = ""
    download_script: str = ""


@dataclass(frozen=True)
class WorkflowBuildRequest:
    """Explicit reusable-workflow build inputs."""

    container_type: str
    image_prefix: str
    build_platforms: str
    tag_suffix: str = ""
    registry: str = "ghcr.io"
    sst_version: str = ""
    sst_elements_version: str = ""
    mpich_version: str = DEFAULT_MPICH_VERSION
    build_ncpus: str = DEFAULT_BUILD_NCPUS
    sst_core_repo: str = DEFAULT_SST_CORE_REPO
    sst_core_ref: str = ""
    sst_elements_repo: str = ""
    sst_elements_ref: str = ""
    experiment_name: str = ""
    base_image: str = ""
    enable_perf_tracking: bool = False
    no_cache: bool = False
    validation_mode: str = "full"
    tag_as_latest: bool = False
    publish_master_latest: bool = False


@dataclass(frozen=True)
class _ContainerBuildPlan:
    """Concrete inputs for invoking one container build."""

    image_tag: str
    containerfile: str
    docker_context: str
    target_platform: str
    build_target: str = ""
    build_args: tuple[str, ...] = ()
    additional_contexts: tuple[str, ...] = ()
    no_cache: bool = False


def detect_container_engine(explicit_engine: str | None = None) -> str:
    """Return the most appropriate container engine available on the host."""

    requested = explicit_engine or os.environ.get("CONTAINER_ENGINE")
    if requested:
        if shutil.which(requested):
            return requested
        raise FileNotFoundError(f"Container engine not found: {requested}")

    if os.environ.get("GITHUB_ACTIONS") == "true" and shutil.which("docker"):
        return "docker"

    system_name = platform.system()
    preferred = ["docker", "podman"] if system_name == "Darwin" else ["podman", "docker"]
    for candidate in preferred:
        if shutil.which(candidate):
            return candidate

    raise FileNotFoundError("No container engine found")


def detect_host_platform() -> str:
    """Detect the canonical host platform string."""

    machine = platform.machine().lower()
    if machine == "x86_64":
        return "linux/amd64"
    if machine in {"aarch64", "arm64"}:
        return "linux/arm64"
    raise ValueError(f"Unsupported platform: {machine}")


def normalize_platform(target_platform: str) -> str:
    """Normalize platform aliases to canonical Linux platform strings."""

    normalized = target_platform.strip().lower()
    if normalized in {"x86_64", "amd64", "linux/amd64"}:
        return "linux/amd64"
    if normalized in {"aarch64", "arm64", "linux/arm64"}:
        return "linux/arm64"
    raise ValueError(
        f"Unsupported platform: {target_platform}\n"
        "Supported platforms: x86_64, arm64, linux/amd64, linux/arm64"
    )


def require_host_platform(target_platform: str) -> str:
    """Validate that a target platform matches the current host platform."""

    normalized_platform = normalize_platform(target_platform)
    if normalized_platform != detect_host_platform():
        raise ValueError("Cross-platform builds are not supported by this script")
    return normalized_platform


def require_single_host_platform(build_platforms: str) -> str:
    """Validate that a platform list represents exactly one host-matching platform."""

    if "," in build_platforms:
        raise ValueError("Multi-platform builds are not supported by this script")
    return require_host_platform(build_platforms)


def normalize_build_platforms(build_platforms: str) -> tuple[str, ...]:
    """Normalize a comma-separated platform list into canonical Linux platforms."""

    normalized_platforms: list[str] = []
    for raw_platform in build_platforms.split(","):
        trimmed_platform = raw_platform.strip()
        if not trimmed_platform:
            continue
        normalized_platform = normalize_platform(trimmed_platform)
        if normalized_platform not in normalized_platforms:
            normalized_platforms.append(normalized_platform)

    if not normalized_platforms:
        raise ValueError("At least one build platform is required")

    return tuple(normalized_platforms)


def validate_url(url: str, description: str) -> None:
    """Validate a repository URL."""

    if not url:
        raise ValueError(f"{description} is required")
    if not re.match(r"^https?://.*$", url):
        raise ValueError(
            f"Invalid {description} format: {url}\nURL must start with http:// or https://"
        )


def validate_git_ref(ref: str, description: str) -> None:
    """Validate a git reference string."""

    if not ref:
        raise ValueError(f"{description} is required")
    if re.search(r"\s", ref):
        raise ValueError(
            f"Invalid {description} format: '{ref}'\nGit references cannot contain spaces"
        )
    if re.search(r"[<>|&$`]", ref):
        raise ValueError(
            f"Invalid {description} format: '{ref}'\n"
            "Git references cannot contain shell special characters"
        )


def _local_sst_core_stage_dir() -> Path:
    """Return the local SST-core stage directory inside the build context."""

    return REPO_ROOT / LOCAL_SST_CORE_STAGE_REL


def reset_local_source_stage_dir(stage_dir: Path | None = None) -> Path:
    """Reset the stage directory back to its placeholder layout."""

    resolved_stage_dir = stage_dir or _local_sst_core_stage_dir()
    shutil.rmtree(resolved_stage_dir, ignore_errors=True)
    resolved_stage_dir.mkdir(parents=True, exist_ok=True)
    (resolved_stage_dir / ".gitkeep").write_text("", encoding="utf-8")
    return resolved_stage_dir


def validate_local_sst_core_checkout(source_dir: str) -> Path:
    """Validate that a local path looks like an SST-core checkout."""

    source_path = Path(source_dir)
    if not source_path.is_dir():
        raise FileNotFoundError(
            f"Local SST-core checkout (--core-path) not found: {source_dir}"
        )

    resolved_source_dir = source_path.resolve()
    if not (resolved_source_dir / "autogen.sh").is_file():
        raise ValueError(
            "Local SST-core checkout (--core-path) is missing autogen.sh: "
            f"{resolved_source_dir}"
        )
    if not (
        (resolved_source_dir / "configure.ac").is_file()
        or (resolved_source_dir / "configure.ac.in").is_file()
    ):
        raise ValueError(
            "Local SST-core checkout (--core-path) does not look like an SST-core "
            f"source tree: {resolved_source_dir}"
        )
    return resolved_source_dir


def _is_git_work_tree(source_dir: Path) -> bool:
    """Return whether a source directory is a git worktree."""

    result = _run_command(
        ["git", "-C", str(source_dir), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
    )
    return result.returncode == 0


def _git_has_head(source_dir: Path) -> bool:
    """Return whether a git worktree has a valid HEAD."""

    result = _run_command(
        ["git", "-C", str(source_dir), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
    )
    return result.returncode == 0


def _stage_git_work_tree(source_dir: Path, stage_dir: Path) -> None:
    """Stage tracked files and local changes from a git worktree."""

    file_descriptor, temp_index = tempfile.mkstemp(
        prefix="sst-core-stage-index.",
        dir=os.environ.get("TMPDIR", None),
    )
    os.close(file_descriptor)
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = temp_index

    try:
        for command in [
            ["git", "-C", str(source_dir), "read-tree", "HEAD"],
            ["git", "-C", str(source_dir), "add", "-A", "."],
            [
                "git",
                "-C",
                str(source_dir),
                "checkout-index",
                "--all",
                "--force",
                f"--prefix={stage_dir}/",
            ],
        ]:
            result = _run_command(command, env=env, capture_output=True)
            if result.returncode != 0:
                raise OrchestrationError("Failed to stage local SST-core checkout into build context")
    finally:
        Path(temp_index).unlink(missing_ok=True)


def _copy_tree_without_git(source_dir: Path, stage_dir: Path) -> None:
    """Copy a source tree into the stage directory while excluding .git metadata."""

    for child in source_dir.iterdir():
        if child.name == ".git":
            continue
        destination = stage_dir / child.name
        if child.is_dir():
            shutil.copytree(child, destination, symlinks=True)
        else:
            shutil.copy2(child, destination)


def stage_local_sst_core_checkout(source_dir: str, stage_dir: Path | None = None) -> Path:
    """Stage a local SST-core checkout into the container build context."""

    resolved_source_dir = validate_local_sst_core_checkout(source_dir)
    resolved_stage_dir = reset_local_source_stage_dir(stage_dir)

    if _is_git_work_tree(resolved_source_dir) and _git_has_head(resolved_source_dir):
        _stage_git_work_tree(resolved_source_dir, resolved_stage_dir)
    else:
        _copy_tree_without_git(resolved_source_dir, resolved_stage_dir)

    if not (resolved_stage_dir / "autogen.sh").is_file():
        raise OrchestrationError(
            "Failed to stage local SST-core checkout into build context: "
            f"{resolved_stage_dir}"
        )

    log_info(f"Staged local SST-core checkout: {resolved_source_dir}")
    return resolved_stage_dir


def normalize_source_build_request(request: SourceBuildRequest) -> SourceBuildRequest:
    """Validate and normalize source-build inputs."""

    normalized_request = replace(request)
    if normalized_request.sst_core_path:
        if normalized_request.sst_core_ref:
            raise ValueError("--core-ref cannot be combined with --core-path")
        validate_local_sst_core_checkout(normalized_request.sst_core_path)
    else:
        validate_git_ref(normalized_request.sst_core_ref, "SST-core reference (--core-ref)")
        validate_url(normalized_request.sst_core_repo, "SST-core repository URL")

    if normalized_request.sst_elements_ref and not normalized_request.sst_elements_repo:
        normalized_request = replace(
            normalized_request,
            sst_elements_repo=DEFAULT_SST_ELEMENTS_REPO,
        )
    if normalized_request.sst_elements_repo and not normalized_request.sst_elements_ref:
        raise ValueError(
            "SST-elements reference (--elements-ref) when elements repo is specified is required"
        )
    if normalized_request.sst_elements_repo:
        validate_url(normalized_request.sst_elements_repo, "SST-elements repository URL")
    if normalized_request.sst_elements_ref:
        validate_git_ref(normalized_request.sst_elements_ref, "SST-elements reference")

    normalized_platform = require_host_platform(
        normalized_request.target_platform or detect_host_platform()
    )

    derived_tag_suffix = derive_source_tag_suffix(
        normalized_request.tag_suffix,
        sst_core_path=normalized_request.sst_core_path,
        sst_core_ref=normalized_request.sst_core_ref,
        sst_elements_repo=normalized_request.sst_elements_repo,
    )

    return replace(
        normalized_request,
        target_platform=normalized_platform,
        tag_suffix=derived_tag_suffix,
    )


def normalize_experiment_build_request(request: ExperimentBuildRequest) -> ExperimentBuildRequest:
    """Validate and normalize experiment build inputs."""

    if not request.experiment_name:
        raise ValueError("Experiment name is required")

    return replace(
        request,
        base_image=request.base_image or "sst-core:latest",
        build_platforms=require_single_host_platform(
            request.build_platforms or detect_host_platform()
        ),
    )


def normalize_build_request(request: BuildRequest) -> BuildRequest:
    """Validate and normalize build entrypoint inputs."""

    if request.container_type not in {"core", "full", "dev", "custom", "experiment"}:
        raise ValueError("Container type is required")
    if request.validate_only and request.validation_mode == "none":
        raise ValueError("--validate-only requires a validation mode other than none")
    if not request.validate_only and request.sst_core_path and request.container_type != "custom":
        raise ValueError("--core-path is only supported with CONTAINER_TYPE=custom")

    normalized_platform = require_host_platform(request.target_platform or detect_host_platform())
    normalized_request = replace(
        request,
        target_platform=normalized_platform,
        sst_elements_version=request.sst_elements_version or request.sst_version,
        tag_suffix=request.tag_suffix or "latest",
    )

    if normalized_request.container_type in {"core", "full"} and normalized_request.sst_version not in VALID_SST_VERSIONS:
        log_warning(f"SST version {normalized_request.sst_version} may not be valid.")
        log_warning(f"Known valid versions: {' '.join(VALID_SST_VERSIONS)}")

    return normalized_request


def inspect_remote_manifest(engine: str, image_ref: str) -> bool:
    """Return whether the container manifest can be resolved."""

    result = subprocess.run(
        [engine, "manifest", "inspect", image_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def collect_verified_manifest_images(
    manifest_tag: str,
    platforms: str,
    engine: str = "docker",
) -> tuple[str, ...]:
    """Return the verified per-platform image tags for a planned manifest."""

    if not manifest_tag or not platforms:
        return ()

    verified_images: list[str] = []
    for platform_name in normalize_build_platforms(platforms):
        candidate_tag = f"{manifest_tag}-{platform_to_arch(platform_name)}"
        if inspect_remote_manifest(engine, candidate_tag):
            verified_images.append(candidate_tag)
        else:
            log_warning(f"Skipping missing platform image {candidate_tag}")

    return tuple(verified_images)


def resolve_base_image_reference(base_image: str, default_owner: str) -> str:
    """Resolve a short image name into a concrete registry reference."""

    if not base_image:
        raise ValueError("Base image cannot be empty")

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


def derive_source_tag_suffix(
    tag_suffix: str,
    *,
    sst_core_path: str = "",
    sst_core_ref: str = "",
    sst_elements_repo: str = "",
) -> str:
    """Return the effective tag suffix for custom-source builds."""

    if tag_suffix:
        return tag_suffix

    base_suffix = "local" if sst_core_path else sanitize_tag_suffix(sst_core_ref)
    if sst_elements_repo:
        return f"{base_suffix}-full"
    return base_suffix


def platform_to_arch(target_platform: str) -> str:
    """Convert a Linux platform string into a short architecture label."""

    mapping = {
        "linux/amd64": "amd64",
        "linux/arm64": "arm64",
    }
    try:
        return mapping[target_platform]
    except KeyError as error:
        raise ValueError(f"Invalid platform: {target_platform}") from error


def generate_experiment_image_tag(
    registry: str, tag_suffix: str, arch: str, experiment_name: str
) -> str:
    """Generate the canonical experiment image tag."""

    return f"{registry}/{experiment_name}:{tag_suffix}-{arch}"


def generate_source_image_tag(
    registry: str,
    tag_suffix: str,
    arch: str,
    enable_perf_tracking: bool,
) -> str:
    """Generate the canonical source build image tag."""

    image_name = "sst-perf-track-custom" if enable_perf_tracking else "sst-custom"
    return f"{registry}/{image_name}:{tag_suffix}-{arch}"


def generate_container_image_tag(
    registry: str,
    container_type: str,
    tag_suffix: str,
    arch: str,
    enable_perf_tracking: bool = False,
    experiment_name: str = "",
) -> str:
    """Generate the canonical local image tag for a container type."""

    if container_type == "experiment":
        if not experiment_name:
            raise ValueError("Experiment name is required for experiment image tags")
        image_name = experiment_name
    elif enable_perf_tracking and container_type != "dev":
        image_name = f"sst-perf-track-{container_type}"
    else:
        image_name = f"sst-{container_type}"

    return f"{registry}/{image_name}:{tag_suffix}-{arch}"


def get_default_size_limit(container_type: str) -> int:
    """Return the default image size limit in MB for a container type."""

    return DEFAULT_SIZE_LIMITS_MB.get(container_type, DEFAULT_SIZE_LIMITS_MB["full"])


def _verification_spec(
    container_type: str,
    validation_mode: str,
    target_platform: str,
) -> VerificationSpec:
    """Create a validation plan for a logical build."""

    return VerificationSpec(
        mode=validation_mode,
        max_size_mb=get_default_size_limit(container_type),
        platforms=(target_platform,),
    )


def _local_publication_spec(image_tag: str) -> PublicationSpec:
    """Create the default local-only publication plan."""

    return PublicationSpec(
        publish_enabled=False,
        platform_tags=(image_tag,),
    )


def _workflow_manifest_repository(
    *,
    registry: str,
    image_prefix: str,
    container_type: str,
    enable_perf_tracking: bool,
    experiment_name: str,
) -> str:
    """Return the manifest repository name for a workflow build."""

    adjusted_prefix = image_prefix
    if enable_perf_tracking and container_type in {"core", "full", "custom"}:
        adjusted_prefix = f"{image_prefix}-perf-track"

    if container_type in {"core", "full"}:
        return f"{registry}/{adjusted_prefix}-{container_type}"
    if container_type in {"dev", "custom"}:
        return f"{registry}/{adjusted_prefix}"
    if container_type == "experiment":
        if not experiment_name:
            raise ValueError("Experiment name is required for workflow experiment builds")
        return f"{registry}/{image_prefix}/{experiment_name}"

    raise ValueError(f"Unsupported workflow container type: {container_type}")


def _workflow_publication_spec(
    manifest_tag: str,
    platform_builds: tuple[PlatformBuildSpec, ...],
    alias_tags: tuple[str, ...] = (),
) -> PublicationSpec:
    """Create the publication plan for workflow builds."""

    return PublicationSpec(
        publish_enabled=True,
        manifest_tag=manifest_tag,
        platform_tags=tuple(build.image_tag for build in platform_builds),
        alias_tags=alias_tags,
    )


def _workflow_alias_tags(
    request: WorkflowBuildRequest,
    manifest_repository: str,
) -> tuple[str, ...]:
    """Return alias manifest tags requested for a workflow build."""

    alias_tags: list[str] = []
    if request.tag_as_latest:
        alias_tags.append(f"{manifest_repository}:latest")
    if request.publish_master_latest:
        alias_tags.append(f"{manifest_repository}:master-latest")
    return tuple(alias_tags)


def normalize_workflow_build_request(request: WorkflowBuildRequest) -> WorkflowBuildRequest:
    """Validate and normalize reusable-workflow build inputs."""

    if request.container_type not in {"core", "full", "dev", "custom", "experiment"}:
        raise ValueError("CONTAINER_TYPE is required")
    if not request.image_prefix:
        raise ValueError("IMAGE_PREFIX is required")

    normalized_platforms = normalize_build_platforms(request.build_platforms)
    normalized_request = replace(
        request,
        build_platforms=",".join(normalized_platforms),
        registry=request.registry or "ghcr.io",
        sst_elements_version=request.sst_elements_version or request.sst_version,
        validation_mode=request.validation_mode or "full",
    )

    if normalized_request.container_type == "dev":
        return replace(
            normalized_request,
            tag_suffix=normalized_request.tag_suffix or "latest",
        )

    if normalized_request.container_type == "experiment":
        if not normalized_request.experiment_name:
            raise ValueError("EXPERIMENT_NAME is required")
        return replace(
            normalized_request,
            tag_suffix=normalized_request.tag_suffix or "latest",
            base_image=normalized_request.base_image or "sst-core:latest",
        )

    if normalized_request.container_type == "custom":
        validate_url(normalized_request.sst_core_repo, "SST-core repository URL")
        validate_git_ref(normalized_request.sst_core_ref, "SST-core reference")
        if normalized_request.sst_elements_ref and not normalized_request.sst_elements_repo:
            normalized_request = replace(
                normalized_request,
                sst_elements_repo=DEFAULT_SST_ELEMENTS_REPO,
            )
        if normalized_request.sst_elements_repo and not normalized_request.sst_elements_ref:
            raise ValueError("SST-elements reference is required when SST-elements repo is specified")
        if normalized_request.sst_elements_repo:
            validate_url(normalized_request.sst_elements_repo, "SST-elements repository URL")
        if normalized_request.sst_elements_ref:
            validate_git_ref(normalized_request.sst_elements_ref, "SST-elements reference")
        return replace(
            normalized_request,
            tag_suffix=derive_source_tag_suffix(
                normalized_request.tag_suffix,
                sst_core_ref=normalized_request.sst_core_ref,
                sst_elements_repo=normalized_request.sst_elements_repo,
            ),
        )

    if normalized_request.sst_version and normalized_request.sst_core_ref:
        raise ValueError("SST release builds cannot combine SST version inputs with SST-core refs")

    if normalized_request.sst_version:
        if normalized_request.sst_version not in VALID_SST_VERSIONS:
            log_warning(f"SST version {normalized_request.sst_version} may not be valid.")
            log_warning(f"Known valid versions: {' '.join(VALID_SST_VERSIONS)}")
        return replace(
            normalized_request,
            tag_suffix=normalized_request.tag_suffix or normalized_request.sst_version,
        )

    validate_url(normalized_request.sst_core_repo, "SST-core repository URL")
    validate_git_ref(normalized_request.sst_core_ref, "SST-core reference")
    if normalized_request.container_type == "full":
        if normalized_request.sst_elements_ref and not normalized_request.sst_elements_repo:
            normalized_request = replace(
                normalized_request,
                sst_elements_repo=DEFAULT_SST_ELEMENTS_REPO,
            )
        if normalized_request.sst_elements_repo and not normalized_request.sst_elements_ref:
            raise ValueError("SST-elements reference is required when SST-elements repo is specified")
        if normalized_request.sst_elements_repo:
            validate_url(normalized_request.sst_elements_repo, "SST-elements repository URL")
        if normalized_request.sst_elements_ref:
            validate_git_ref(normalized_request.sst_elements_ref, "SST-elements reference")

    return replace(
        normalized_request,
        tag_suffix=normalized_request.tag_suffix or sanitize_tag_suffix(normalized_request.sst_core_ref),
    )


def _source_download_spec_for_build(request: BuildRequest) -> SourceDownloadSpec:
    """Create the source-download plan for a build entrypoint request."""

    destination_dir = str(REPO_ROOT / "Containerfiles")
    if request.container_type == "core":
        return SourceDownloadSpec(
            destination_dir=destination_dir,
            mpich_version=request.mpich_version,
            sst_version=request.sst_version,
            download_mpich=True,
            download_sst_core=True,
            force_mode=True,
        )
    if request.container_type == "full":
        return SourceDownloadSpec(
            destination_dir=destination_dir,
            mpich_version=request.mpich_version,
            sst_version=request.sst_version,
            sst_elements_version=request.sst_elements_version,
            download_mpich=True,
            download_sst_core=True,
            download_sst_elements=True,
            force_mode=True,
        )
    if request.container_type in {"dev", "custom", "experiment"}:
        return SourceDownloadSpec(
            destination_dir=destination_dir,
            mpich_version=request.mpich_version,
            download_mpich=True,
            force_mode=True,
        )
    raise OrchestrationError(f"Unknown container type: {request.container_type}")


def _source_download_spec_for_workflow_build(request: WorkflowBuildRequest) -> SourceDownloadSpec:
    """Create the source-download plan for a reusable workflow build."""

    destination_dir = str(REPO_ROOT / "Containerfiles")
    if request.container_type == "dev":
        return SourceDownloadSpec(
            destination_dir=destination_dir,
            mpich_version=request.mpich_version,
            download_mpich=True,
            force_mode=request.no_cache,
        )

    if request.container_type in {"core", "full"} and request.sst_version:
        return SourceDownloadSpec(
            destination_dir=destination_dir,
            mpich_version=request.mpich_version,
            sst_version=request.sst_version,
            sst_elements_version=request.sst_elements_version,
            download_mpich=True,
            download_sst_core=True,
            download_sst_elements=request.container_type == "full",
            force_mode=request.no_cache,
        )

    if request.container_type in {"core", "full", "custom", "experiment"}:
        return SourceDownloadSpec(
            destination_dir=destination_dir,
            mpich_version=request.mpich_version,
            download_mpich=True,
            force_mode=request.no_cache,
        )

    raise OrchestrationError(f"Unknown workflow container type: {request.container_type}")


def _workflow_platform_builds(
    *,
    repository: str,
    tag_suffix: str,
    platforms: tuple[str, ...],
    containerfile_path: str,
    docker_context: str,
    build_target: str,
    build_args: tuple[str, ...],
    additional_contexts: tuple[str, ...],
    no_cache: bool,
) -> tuple[PlatformBuildSpec, ...]:
    """Create per-platform build specs for a workflow build."""

    platform_builds: list[PlatformBuildSpec] = []
    for target_platform in platforms:
        arch = platform_to_arch(target_platform)
        platform_builds.append(
            PlatformBuildSpec(
                platform=target_platform,
                arch=arch,
                image_tag=f"{repository}:{tag_suffix}-{arch}",
                containerfile_path=containerfile_path,
                docker_context=docker_context,
                build_target=build_target,
                build_args=build_args,
                additional_contexts=additional_contexts,
                no_cache=no_cache,
            )
        )
    return tuple(platform_builds)


def _workflow_bake_context_path(path: str, workspace_root: Path) -> str:
    """Normalize workflow build contexts for emission in Buildx bake files."""

    candidate = Path(path)
    if not candidate.is_absolute():
        return path

    try:
        return str(candidate.relative_to(workspace_root)) or "."
    except ValueError:
        return path


def _workflow_bake_dockerfile_path(
    dockerfile_path: str,
    docker_context: str,
    workspace_root: Path,
) -> str:
    """Resolve a Dockerfile path the way Buildx bake expects it."""

    context_candidate = Path(docker_context)
    if context_candidate.is_absolute():
        resolved_context = context_candidate
    else:
        resolved_context = (workspace_root / context_candidate).resolve()

    dockerfile_candidate = Path(dockerfile_path)
    if dockerfile_candidate.is_absolute():
        resolved_dockerfile = dockerfile_candidate
    else:
        resolved_dockerfile = (workspace_root / dockerfile_candidate).resolve()

    try:
        return str(resolved_dockerfile.relative_to(resolved_context)) or "."
    except ValueError:
        return str(resolved_dockerfile)


def _key_value_mapping(entries: tuple[str, ...]) -> dict[str, str]:
    """Convert KEY=VALUE tuples into a mapping for Buildx bake emission."""

    mapped_entries: dict[str, str] = {}
    for entry in entries:
        key, separator, value = entry.partition("=")
        if not separator:
            raise ValueError(f"Expected KEY=VALUE entry, got: {entry}")
        mapped_entries[key] = value
    return mapped_entries


def _sst_core_input_context_entry(source_path: Path) -> str:
    """Return the named build-context mapping for the staged SST-core input."""

    return f"{LOCAL_SST_CORE_CONTEXT_NAME}={source_path}"


def _workflow_bake_target_name(build_spec: BuildSpec, platform_build: PlatformBuildSpec) -> str:
    """Return a stable Buildx bake target name for one platform build."""

    return f"{build_spec.container_type}-{platform_build.arch}"


def plan_workflow_bake(
    build_spec: BuildSpec,
    *,
    labels: Mapping[str, str] | None = None,
    workspace_root: Path = REPO_ROOT,
) -> WorkflowBakePlan:
    """Convert a workflow build spec into a Buildx bake definition."""

    if build_spec.build_kind != "workflow":
        raise ValueError("Buildx bake emission is only supported for workflow build specs")

    merged_labels = dict(labels or {})
    target_definitions: dict[str, object] = {}
    bake_targets: list[WorkflowBakeTargetSpec] = []

    for platform_build in build_spec.platform_builds:
        target_name = _workflow_bake_target_name(build_spec, platform_build)
        cache_scope = f"{build_spec.container_type}-{build_spec.tag_suffix}-{platform_build.arch}"
        target_definition: dict[str, object] = {
            "context": _workflow_bake_context_path(platform_build.docker_context, workspace_root),
            "dockerfile": _workflow_bake_dockerfile_path(
                platform_build.containerfile_path,
                platform_build.docker_context,
                workspace_root,
            ),
            "platforms": [platform_build.platform],
            "tags": [platform_build.image_tag],
            "cache-from": [f"type=gha,scope={cache_scope}"],
            "cache-to": [f"type=gha,mode=max,scope={cache_scope}"],
        }
        if platform_build.build_target:
            target_definition["target"] = platform_build.build_target
        if platform_build.build_args:
            target_definition["args"] = _key_value_mapping(platform_build.build_args)
        if platform_build.additional_contexts:
            target_definition["contexts"] = {
                name: _workflow_bake_context_path(path, workspace_root)
                for name, path in _key_value_mapping(platform_build.additional_contexts).items()
            }
        if platform_build.labels or merged_labels:
            labels_map: dict[str, str] = {}
            if platform_build.labels:
                labels_map.update(_key_value_mapping(platform_build.labels))
            labels_map.update(merged_labels)
            target_definition["labels"] = labels_map
        if platform_build.no_cache:
            target_definition["no-cache"] = True

        target_definitions[target_name] = target_definition
        bake_targets.append(
            WorkflowBakeTargetSpec(
                name=target_name,
                platform=platform_build.platform,
                arch=platform_build.arch,
                image_tag=platform_build.image_tag,
                cache_scope=cache_scope,
            )
        )

    return WorkflowBakePlan(
        definition={
            "group": {"default": {"targets": [target.name for target in bake_targets]}},
            "target": target_definitions,
        },
        targets=tuple(bake_targets),
    )


def plan_workflow_build_spec(
    request: WorkflowBuildRequest,
    *,
    validate_base_image: bool = True,
    container_engine: str | None = None,
) -> BuildSpec:
    """Return the shared build spec for a reusable workflow build."""

    normalized_request = normalize_workflow_build_request(request)
    platforms = normalize_build_platforms(normalized_request.build_platforms)
    manifest_repository = _workflow_manifest_repository(
        registry=normalized_request.registry,
        image_prefix=normalized_request.image_prefix,
        container_type=normalized_request.container_type,
        enable_perf_tracking=normalized_request.enable_perf_tracking,
        experiment_name=normalized_request.experiment_name,
    )
    manifest_tag = f"{manifest_repository}:{normalized_request.tag_suffix}"
    alias_tags = _workflow_alias_tags(normalized_request, manifest_repository)
    verification = VerificationSpec(
        mode=normalized_request.validation_mode,
        max_size_mb=get_default_size_limit(normalized_request.container_type),
        platforms=platforms,
    )

    if normalized_request.container_type == "dev":
        platform_builds = _workflow_platform_builds(
            repository=manifest_repository,
            tag_suffix=normalized_request.tag_suffix,
            platforms=platforms,
            containerfile_path="Containerfiles/Containerfile.dev",
            docker_context="Containerfiles",
            build_target="",
            build_args=(
                f"mpich={normalized_request.mpich_version}",
                f"NCPUS={normalized_request.build_ncpus}",
            ),
            additional_contexts=(),
            no_cache=normalized_request.no_cache,
        )
        return BuildSpec(
            build_kind="workflow",
            container_type="dev",
            registry=normalized_request.registry,
            tag_suffix=normalized_request.tag_suffix,
            source=BuildSourceSpec(
                source_kind="development-dependencies",
                mpich_version=normalized_request.mpich_version,
            ),
            platform_builds=platform_builds,
            verification=verification,
            publication=_workflow_publication_spec(manifest_tag, platform_builds, alias_tags),
            source_download=_source_download_spec_for_workflow_build(normalized_request),
        )

    if normalized_request.container_type in {"core", "full"} and normalized_request.sst_version:
        build_args: list[str] = [
            f"SSTver={normalized_request.sst_version}",
            f"mpich={normalized_request.mpich_version}",
            f"NCPUS={normalized_request.build_ncpus}",
        ]
        if normalized_request.container_type == "full" and normalized_request.sst_elements_version:
            build_args.append(f"SST_ELEMENTS_VERSION={normalized_request.sst_elements_version}")
        if normalized_request.enable_perf_tracking:
            build_args.append("ENABLE_PERF_TRACKING=1")

        platform_builds = _workflow_platform_builds(
            repository=manifest_repository,
            tag_suffix=normalized_request.tag_suffix,
            platforms=platforms,
            containerfile_path="Containerfiles/Containerfile",
            docker_context="Containerfiles",
            build_target="sst-core" if normalized_request.container_type == "core" else "sst-full",
            build_args=tuple(build_args),
            additional_contexts=(),
            no_cache=normalized_request.no_cache,
        )
        return BuildSpec(
            build_kind="workflow",
            container_type=normalized_request.container_type,
            registry=normalized_request.registry,
            tag_suffix=normalized_request.tag_suffix,
            source=BuildSourceSpec(
                source_kind="release-tarballs",
                mpich_version=normalized_request.mpich_version,
                sst_version=normalized_request.sst_version,
                sst_elements_version=normalized_request.sst_elements_version,
            ),
            platform_builds=platform_builds,
            verification=verification,
            publication=_workflow_publication_spec(manifest_tag, platform_builds, alias_tags),
            source_download=_source_download_spec_for_workflow_build(normalized_request),
        )

    if normalized_request.container_type == "experiment":
        experiment_dir = REPO_ROOT / normalized_request.experiment_name
        if not experiment_dir.is_dir():
            raise OrchestrationError(
                f"Experiment directory '{normalized_request.experiment_name}' not found"
            )

        has_custom_containerfile = (experiment_dir / "Containerfile").is_file()
        build_args = []
        resolved_base_image = ""
        if has_custom_containerfile:
            containerfile_path = f"{normalized_request.experiment_name}/Containerfile"
            docker_context = normalized_request.experiment_name
            source_kind = "experiment-custom-containerfile"
        else:
            repo_owner = normalized_request.image_prefix.split("/", 1)[0]
            resolved_base_image = resolve_base_image_reference(
                normalized_request.base_image,
                repo_owner,
            )
            if validate_base_image:
                engine = container_engine or detect_container_engine()
                if not inspect_remote_manifest(engine, resolved_base_image):
                    raise FileNotFoundError(
                        f"Base image not found: {resolved_base_image}\n"
                        "For images in this repository, use format: sst-core:latest\n"
                        "For external images, use full path: ghcr.io/username/image:tag"
                    )
            build_args.append(f"BASE_IMAGE={resolved_base_image}")
            containerfile_path = "Containerfiles/Containerfile.experiment"
            docker_context = normalized_request.experiment_name
            source_kind = "experiment-template"

        platform_builds = _workflow_platform_builds(
            repository=manifest_repository,
            tag_suffix=normalized_request.tag_suffix,
            platforms=platforms,
            containerfile_path=containerfile_path,
            docker_context=docker_context,
            build_target="",
            build_args=tuple(build_args),
            additional_contexts=(),
            no_cache=normalized_request.no_cache,
        )
        return BuildSpec(
            build_kind="workflow",
            container_type="experiment",
            registry=normalized_request.registry,
            tag_suffix=normalized_request.tag_suffix,
            source=BuildSourceSpec(
                source_kind=source_kind,
                experiment_name=normalized_request.experiment_name,
                base_image=resolved_base_image or normalized_request.base_image,
                uses_custom_containerfile=has_custom_containerfile,
            ),
            platform_builds=platform_builds,
            verification=verification,
            publication=_workflow_publication_spec(manifest_tag, platform_builds, alias_tags),
            source_download=_source_download_spec_for_workflow_build(normalized_request),
        )

    build_target = "full-build" if normalized_request.container_type == "full" or normalized_request.sst_elements_repo else "core-build"
    build_args = [
        f"mpich={normalized_request.mpich_version}",
        f"NCPUS={normalized_request.build_ncpus}",
        f"SSTrepo={normalized_request.sst_core_repo}",
        f"tag={normalized_request.sst_core_ref}",
    ]
    if build_target == "full-build":
        build_args.extend(
            [
                f"SSTElementsRepo={normalized_request.sst_elements_repo}",
                f"elementsTag={normalized_request.sst_elements_ref}",
            ]
        )
    if normalized_request.enable_perf_tracking:
        build_args.append("ENABLE_PERF_TRACKING=1")

    platform_builds = _workflow_platform_builds(
        repository=manifest_repository,
        tag_suffix=normalized_request.tag_suffix,
        platforms=platforms,
        containerfile_path="Containerfiles/Containerfile.tag",
        docker_context="Containerfiles",
        build_target=build_target,
        build_args=tuple(build_args),
        additional_contexts=(),
        no_cache=normalized_request.no_cache,
    )
    return BuildSpec(
        build_kind="workflow",
        container_type=normalized_request.container_type,
        registry=normalized_request.registry,
        tag_suffix=normalized_request.tag_suffix,
        source=BuildSourceSpec(
            source_kind="git-ref",
            mpich_version=normalized_request.mpich_version,
            sst_core_repo=normalized_request.sst_core_repo,
            sst_core_ref=normalized_request.sst_core_ref,
            sst_elements_repo=normalized_request.sst_elements_repo,
            sst_elements_ref=normalized_request.sst_elements_ref,
        ),
        platform_builds=platform_builds,
        verification=verification,
        publication=_workflow_publication_spec(manifest_tag, platform_builds, alias_tags),
        source_download=_source_download_spec_for_workflow_build(normalized_request),
    )


def _container_plan_from_platform_build(build_spec: PlatformBuildSpec) -> _ContainerBuildPlan:
    """Convert a platform build spec into an executable build command plan."""

    return _ContainerBuildPlan(
        image_tag=build_spec.image_tag,
        containerfile=build_spec.containerfile_path,
        docker_context=build_spec.docker_context,
        target_platform=build_spec.platform,
        build_target=build_spec.build_target,
        build_args=build_spec.build_args,
        additional_contexts=build_spec.additional_contexts,
        no_cache=build_spec.no_cache,
    )


def _plan_standard_build_spec(normalized_request: BuildRequest) -> BuildSpec:
    """Create the shared build spec for core, full, and dev build requests."""

    if normalized_request.container_type not in {"core", "full", "dev"}:
        raise ValueError("Standard build planning requires core, full, or dev")

    arch = platform_to_arch(normalized_request.target_platform)
    containerfile = REPO_ROOT / "Containerfiles" / (
        "Containerfile.dev" if normalized_request.container_type == "dev" else "Containerfile"
    )
    build_target = ""
    build_args: list[str] = []
    source_kind = "development-dependencies"
    effective_tag_suffix = normalized_request.tag_suffix or "latest"

    if normalized_request.container_type == "core":
        effective_tag_suffix = (
            normalized_request.tag_suffix if normalized_request.tag_suffix_set else normalized_request.sst_version
        )
        image_tag = generate_container_image_tag(
            normalized_request.registry,
            "core",
            effective_tag_suffix,
            arch,
            normalized_request.enable_perf_tracking,
        )
        build_target = "sst-core"
        source_kind = "release-tarballs"
        build_args.extend(
            [
                f"SSTver={normalized_request.sst_version}",
                f"mpich={normalized_request.mpich_version}",
                f"NCPUS={normalized_request.build_ncpus}",
            ]
        )
    elif normalized_request.container_type == "full":
        effective_tag_suffix = (
            normalized_request.tag_suffix if normalized_request.tag_suffix_set else normalized_request.sst_version
        )
        image_tag = generate_container_image_tag(
            normalized_request.registry,
            "full",
            effective_tag_suffix,
            arch,
            normalized_request.enable_perf_tracking,
        )
        build_target = "sst-full"
        source_kind = "release-tarballs"
        build_args.extend(
            [
                f"SSTver={normalized_request.sst_version}",
                f"mpich={normalized_request.mpich_version}",
                f"NCPUS={normalized_request.build_ncpus}",
            ]
        )
        if normalized_request.sst_elements_version:
            build_args.append(f"SST_ELEMENTS_VERSION={normalized_request.sst_elements_version}")
    else:
        effective_tag_suffix = (
            normalized_request.tag_suffix if normalized_request.tag_suffix_set else "latest"
        )
        image_tag = generate_container_image_tag(
            normalized_request.registry,
            "dev",
            effective_tag_suffix,
            arch,
        )
        build_args.extend(
            [
                f"mpich={normalized_request.mpich_version}",
                f"NCPUS={normalized_request.build_ncpus}",
            ]
        )

    if normalized_request.enable_perf_tracking and normalized_request.container_type in {"core", "full"}:
        build_args.append("ENABLE_PERF_TRACKING=1")

    platform_build = PlatformBuildSpec(
        platform=normalized_request.target_platform,
        arch=arch,
        image_tag=image_tag,
        containerfile_path=str(containerfile),
        docker_context=str(REPO_ROOT / "Containerfiles"),
        build_target=build_target,
        build_args=tuple(build_args),
        no_cache=normalized_request.no_cache,
    )
    return BuildSpec(
        build_kind="local",
        container_type=normalized_request.container_type,
        registry=normalized_request.registry,
        tag_suffix=effective_tag_suffix,
        source=BuildSourceSpec(
            source_kind=source_kind,
            mpich_version=normalized_request.mpich_version,
            sst_version=normalized_request.sst_version,
            sst_elements_version=normalized_request.sst_elements_version,
        ),
        platform_builds=(platform_build,),
        verification=_verification_spec(
            normalized_request.container_type,
            normalized_request.validation_mode,
            normalized_request.target_platform,
        ),
        publication=_local_publication_spec(image_tag),
        source_download=_source_download_spec_for_build(normalized_request),
    )


def _create_container_build_command(
    container_engine: str,
    plan: _ContainerBuildPlan,
) -> list[str]:
    """Create a container build command from a concrete build plan."""

    command = [
        container_engine,
        "build",
        "--platform",
        plan.target_platform,
        "--tag",
        plan.image_tag,
        "--file",
        plan.containerfile,
    ]
    if plan.build_target:
        command.extend(["--target", plan.build_target])
    for build_arg in plan.build_args:
        command.extend(["--build-arg", build_arg])
    for build_context in plan.additional_contexts:
        command.extend(["--build-context", build_context])
    if plan.no_cache:
        command.append("--no-cache")
    command.append(plan.docker_context)
    return command


def _run_container_build(
    plan: _ContainerBuildPlan,
    *,
    container_engine: str,
    failure_message: str,
    cwd: Path | None = None,
) -> int:
    """Execute a concrete container build plan and return elapsed build time."""

    log_info(f"Building container: {plan.image_tag}")
    log_info(f"Using containerfile: {plan.containerfile}")
    if plan.build_target:
        log_info(f"Using build target: {plan.build_target}")
    log_info(f"Using docker context: {plan.docker_context}")
    if plan.additional_contexts:
        for build_context in plan.additional_contexts:
            log_info(f"Using additional build context: {build_context}")

    start_group("Building Container")
    start_time = time.monotonic()
    try:
        build_result = _run_command(
            _create_container_build_command(container_engine, plan),
            cwd=cwd,
        )
    finally:
        end_group()

    if build_result.returncode != 0:
        raise OrchestrationError(failure_message)

    build_time_seconds = int(time.monotonic() - start_time)
    log_success(f"Build completed: {plan.image_tag}")
    return build_time_seconds


def _remove_image(container_engine: str, image_tag: str, *, warning_message: str) -> bool:
    """Attempt to remove a built image and report failures consistently."""

    remove_result = _run_command([container_engine, "rmi", image_tag], capture_output=True)
    if remove_result.returncode != 0:
        log_warning(warning_message)
        return False
    return True


def _inspect_built_image_size(container_engine: str, image_tag: str) -> int:
    """Inspect a built image and report its size in MB."""

    metadata = _inspect_image_json(container_engine, image_tag)
    image_size_mb = _image_size_mb_from_metadata(metadata)
    log_info(f"Image size: {image_size_mb}MB")
    return image_size_mb


def _download_file_url(url: str, destination: Path) -> None:
    """Download a URL to a destination file path."""

    request = urllib.request.Request(url, headers={"User-Agent": "sst-container-factory"})
    try:
        with urllib.request.urlopen(
            request,
            context=ssl.create_default_context(),
        ) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise OrchestrationError(f"Failed to download {destination.name}: {exc}") from exc


def _download_requested_file(url: str, destination: Path, description: str) -> None:
    """Download one tarball if it is not already present."""

    log_info("")
    log_info(f"Downloading {description}...")
    log_info(f"URL: {url}")
    log_info(f"File: {destination.name}")

    if destination.is_file():
        log_info(f"File {destination.name} already exists. Skipping download.")
        return

    _download_file_url(url, destination)
    size_mb = destination.stat().st_size // 1024 // 1024
    log_success(f"Successfully downloaded {destination.name}")
    log_info(f"File size: {size_mb} MB")


def download_sources(
    *,
    sst_version: str = DEFAULT_SST_VERSION,
    sst_elements_version: str | None = None,
    mpich_version: str = DEFAULT_MPICH_VERSION,
    download_mpich: bool = True,
    download_sst_core: bool = True,
    download_sst_elements: bool = True,
    force_mode: bool = False,
    destination_dir: Path | None = None,
) -> DownloadSourcesResult:
    """Download the requested build source tarballs into a directory."""

    destination = destination_dir or Path.cwd()
    effective_elements_version = sst_elements_version or sst_version

    if download_sst_core and not force_mode and sst_version not in VALID_SST_VERSIONS:
        log_warning(f"SST version {sst_version} may not be valid.")
        log_warning(f"Known valid versions: {' '.join(VALID_SST_VERSIONS)}")
        log_warning("Continuing anyway...")

    log_info("==================================================")
    log_info("SST Container Source Download Script")
    log_info("==================================================")
    if download_sst_core:
        log_info(f"SST Version:   {sst_version}")
    if download_sst_elements:
        log_info(f"Elements Ver:  {effective_elements_version}")
    if download_mpich:
        log_info(f"MPICH Version: {mpich_version}")
    log_info("==================================================")

    requested_downloads: list[tuple[str, str, str]] = []
    if download_mpich:
        requested_downloads.append(
            (
                os.environ.get(
                    "SST_DOWNLOAD_MPICH_URL",
                    f"https://www.mpich.org/static/downloads/{mpich_version}/mpich-{mpich_version}.tar.gz",
                ),
                f"mpich-{mpich_version}.tar.gz",
                f"MPICH {mpich_version}",
            )
        )
    if download_sst_core:
        requested_downloads.append(
            (
                os.environ.get(
                    "SST_DOWNLOAD_CORE_URL",
                    f"https://github.com/sstsimulator/sst-core/releases/download/v{sst_version}_Final/sstcore-{sst_version}.tar.gz",
                ),
                f"sstcore-{sst_version}.tar.gz",
                f"SST-core {sst_version}",
            )
        )
    if download_sst_elements:
        requested_downloads.append(
            (
                os.environ.get(
                    "SST_DOWNLOAD_ELEMENTS_URL",
                    f"https://github.com/sstsimulator/sst-elements/releases/download/v{effective_elements_version}_Final/sstelements-{effective_elements_version}.tar.gz",
                ),
                f"sstelements-{effective_elements_version}.tar.gz",
                f"SST-elements {effective_elements_version}",
            )
        )

    requested_files: list[str] = []
    for url, filename, description in requested_downloads:
        requested_files.append(filename)
        _download_requested_file(url, destination / filename, description)

    log_info("")
    log_info("==================================================")
    log_info("Download Summary")
    log_info("==================================================")

    total_size_mb = 0
    missing_files: list[str] = []
    for filename in requested_files:
        file_path = destination / filename
        if file_path.is_file():
            size_mb = file_path.stat().st_size // 1024 // 1024
            total_size_mb += size_mb
            log_success(f"{filename} ({size_mb} MB)")
        else:
            missing_files.append(filename)
            log_error(f"{filename} (MISSING)")

    log_info("==================================================")
    log_info(f"Total download size: {total_size_mb} MB")
    if missing_files:
        raise OrchestrationError(
            "Some downloads failed. Missing files: " + ", ".join(missing_files)
        )

    log_success("All requested files downloaded successfully!")
    return DownloadSourcesResult(
        requested_files=tuple(requested_files),
        total_size_mb=total_size_mb,
        destination_dir=str(destination),
    )


def _run_command(
    command: list[str],
    *,
    capture_output: bool = False,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command and optionally capture stdout."""

    return subprocess.run(
        command,
        capture_output=capture_output,
        cwd=cwd,
        env=env,
        text=True,
        check=False,
    )


def _last_built_image_path() -> Path:
    """Return the path to the build entrypoint tag marker file."""

    return REPO_ROOT / ".last_built_image"


def _write_last_built_image(image_tag: str) -> None:
    """Persist the most recently built local image tag."""

    _last_built_image_path().write_text(f"{image_tag}\n", encoding="utf-8")


def _read_last_built_image() -> str:
    """Read the most recently built local image tag, if present."""

    marker_path = _last_built_image_path()
    if not marker_path.is_file():
        return ""
    return marker_path.read_text(encoding="utf-8").strip()


def _remove_last_built_image() -> None:
    """Remove the build entrypoint tag marker file if it exists."""

    marker_path = _last_built_image_path()
    if marker_path.exists():
        marker_path.unlink()


def _download_build_sources(
    download_spec: SourceDownloadSpec,
    *,
    download_script_override: str = "",
) -> None:
    """Download the source tarballs required for the build entrypoint."""

    log_info("Downloading source files...")
    if download_script_override:
        download_script = Path(download_script_override)
        if not download_script.is_file():
            raise OrchestrationError(f"Download script not found: {download_script}")

        command = [str(download_script), "--force"]
        if download_spec.download_sst_core:
            command.extend(["--sst-version", download_spec.sst_version])
        if download_spec.download_sst_elements:
            command.extend(["--sst-elements-version", download_spec.sst_elements_version])
        if download_spec.download_mpich:
            command.extend(["--mpich-version", download_spec.mpich_version])

        result = _run_command(command, cwd=Path(download_spec.destination_dir))
        if result.returncode != 0:
            raise OrchestrationError("Failed to download required source files")
    else:
        download_sources(
            sst_version=download_spec.sst_version or DEFAULT_SST_VERSION,
            sst_elements_version=download_spec.sst_elements_version or None,
            mpich_version=download_spec.mpich_version or DEFAULT_MPICH_VERSION,
            download_mpich=download_spec.download_mpich,
            download_sst_core=download_spec.download_sst_core,
            download_sst_elements=download_spec.download_sst_elements,
            force_mode=download_spec.force_mode,
            destination_dir=Path(download_spec.destination_dir),
        )

    log_success("Source files ready")


def _build_standard_image(build_spec: BuildSpec, *, container_engine: str) -> str:
    """Build a core, full, or dev image for the build entrypoint."""

    _run_container_build(
        _container_plan_from_platform_build(build_spec.primary_platform_build),
        container_engine=container_engine,
        failure_message="Container build failed",
    )
    return build_spec.primary_platform_build.image_tag


def _local_source_build_request(
    *,
    registry: str,
    target_platform: str,
    mpich_version: str,
    build_ncpus: str,
    tag_suffix: str,
    tag_suffix_set: bool,
    enable_perf_tracking: bool,
    no_cache: bool,
    sst_core_path: str,
    sst_core_repo: str,
    sst_core_ref: str,
    sst_elements_repo: str,
    sst_elements_ref: str,
    container_engine: str | None,
) -> SourceBuildRequest:
    """Translate a local source-backed build request into the canonical source-build request."""

    return SourceBuildRequest(
        target_platform=target_platform,
        tag_suffix=tag_suffix if tag_suffix_set else "",
        sst_core_ref=sst_core_ref,
        sst_core_repo=sst_core_repo,
        sst_core_path=sst_core_path,
        sst_elements_repo=sst_elements_repo,
        sst_elements_ref=sst_elements_ref,
        mpich_version=mpich_version,
        build_ncpus=build_ncpus,
        registry=registry,
        enable_perf_tracking=enable_perf_tracking,
        no_cache=no_cache,
        cleanup=False,
        validation_mode="none",
        container_engine=container_engine,
    )


def _delegate_local_source_build(
    *,
    registry: str,
    target_platform: str,
    mpich_version: str,
    build_ncpus: str,
    tag_suffix: str,
    tag_suffix_set: bool,
    enable_perf_tracking: bool,
    no_cache: bool,
    sst_core_path: str,
    sst_core_repo: str,
    sst_core_ref: str,
    sst_elements_repo: str,
    sst_elements_ref: str,
    container_engine: str,
) -> str:
    """Delegate a local build source image request to the canonical source-build path."""
    result = source_build(
        _local_source_build_request(
            registry=registry,
            target_platform=target_platform,
            mpich_version=mpich_version,
            build_ncpus=build_ncpus,
            tag_suffix=tag_suffix,
            tag_suffix_set=tag_suffix_set,
            enable_perf_tracking=enable_perf_tracking,
            no_cache=no_cache,
            sst_core_path=sst_core_path,
            sst_core_repo=sst_core_repo,
            sst_core_ref=sst_core_ref,
            sst_elements_repo=sst_elements_repo,
            sst_elements_ref=sst_elements_ref,
            container_engine=container_engine,
        )
    )
    return result.image_tag


def _delegate_local_experiment_build(
    *,
    registry: str,
    target_platform: str,
    tag_suffix: str,
    base_image: str,
    experiment_name: str,
    no_cache: bool,
    container_engine: str,
) -> str:
    """Delegate a build entrypoint experiment image build to the canonical experiment entrypoint."""

    if not experiment_name:
        raise OrchestrationError("Experiment builds require an experiment name")

    result = experiment_build(
        ExperimentBuildRequest(
            experiment_name=experiment_name,
            base_image=base_image,
            build_platforms=target_platform,
            registry=registry,
            tag_suffix=tag_suffix,
            validation_mode="none",
            no_cache=no_cache,
            container_engine=container_engine,
        )
    )
    return result.image_tag


def _plan_source_build_spec(normalized_request: SourceBuildRequest) -> BuildSpec:
    """Create the shared build spec for a source build request."""

    build_type = "full-build" if normalized_request.sst_elements_repo else "core-build"
    using_local_core_checkout = bool(normalized_request.sst_core_path)
    arch = platform_to_arch(normalized_request.target_platform)
    image_tag = generate_source_image_tag(
        normalized_request.registry,
        normalized_request.tag_suffix,
        arch,
        normalized_request.enable_perf_tracking,
    )

    build_args = [
        f"mpich={normalized_request.mpich_version}",
        f"NCPUS={normalized_request.build_ncpus}",
    ]
    if using_local_core_checkout:
        build_args.append(LOCAL_SST_CORE_SOURCE_STAGE_ARG)
    else:
        build_args.extend(
            [
                f"SSTrepo={normalized_request.sst_core_repo}",
                f"tag={normalized_request.sst_core_ref}",
            ]
        )

    if build_type == "full-build":
        build_args.extend(
            [
                f"SSTElementsRepo={normalized_request.sst_elements_repo}",
                f"elementsTag={normalized_request.sst_elements_ref}",
            ]
        )

    if normalized_request.enable_perf_tracking:
        build_args.append("ENABLE_PERF_TRACKING=1")

    platform_build = PlatformBuildSpec(
        platform=normalized_request.target_platform,
        arch=arch,
        image_tag=image_tag,
        containerfile_path="Containerfiles/Containerfile.tag",
        docker_context="Containerfiles",
        build_target=build_type,
        build_args=tuple(build_args),
        additional_contexts=(
            (_sst_core_input_context_entry(_local_sst_core_stage_dir()),)
            if using_local_core_checkout
            else ()
        ),
        no_cache=normalized_request.no_cache,
    )
    return BuildSpec(
        build_kind="custom",
        container_type="custom",
        registry=normalized_request.registry,
        tag_suffix=normalized_request.tag_suffix,
        source=BuildSourceSpec(
            source_kind="local-checkout" if using_local_core_checkout else "git-ref",
            mpich_version=normalized_request.mpich_version,
            sst_core_repo=normalized_request.sst_core_repo,
            sst_core_ref=normalized_request.sst_core_ref,
            sst_core_path=normalized_request.sst_core_path,
            sst_elements_repo=normalized_request.sst_elements_repo,
            sst_elements_ref=normalized_request.sst_elements_ref,
            uses_local_core_checkout=using_local_core_checkout,
        ),
        platform_builds=(platform_build,),
        verification=_verification_spec(
            "custom",
            normalized_request.validation_mode,
            normalized_request.target_platform,
        ),
        publication=_local_publication_spec(image_tag),
    )


def plan_source_build_spec(request: SourceBuildRequest) -> BuildSpec:
    """Return the shared build spec for a source build request."""

    return _plan_source_build_spec(normalize_source_build_request(request))


def _plan_experiment_build_spec(
    normalized_request: ExperimentBuildRequest,
    *,
    container_engine: str | None,
    validate_base_image: bool,
) -> BuildSpec:
    """Create the shared build spec for an experiment build request."""

    experiment_dir = REPO_ROOT / normalized_request.experiment_name
    if not experiment_dir.is_dir():
        raise OrchestrationError(
            f"Experiment directory '{normalized_request.experiment_name}' not found"
        )
    has_custom_containerfile = (experiment_dir / "Containerfile").is_file()
    build_args = list(normalized_request.build_args)
    resolved_base_image = ""

    if has_custom_containerfile:
        containerfile_path = experiment_dir / "Containerfile"
        docker_context = experiment_dir
        source_kind = "experiment-custom-containerfile"
    else:
        containerfile_path = REPO_ROOT / "Containerfiles" / "Containerfile.experiment"
        docker_context = experiment_dir
        source_kind = "experiment-template"
        resolved_base_image = resolve_base_image_reference(
            normalized_request.base_image,
            os.environ.get("USER", ""),
        )
        build_args.append(f"BASE_IMAGE={resolved_base_image}")
        if validate_base_image:
            if container_engine is None:
                raise ValueError("Container engine is required to validate experiment base images")
            if not inspect_remote_manifest(container_engine, resolved_base_image):
                raise FileNotFoundError(
                    f"Base image not found: {resolved_base_image}\n"
                    "For images in this repository, use format: sst-core:latest\n"
                    "For external images, use full path: ghcr.io/username/image:tag"
                )

    arch = platform_to_arch(normalized_request.build_platforms)
    image_tag = generate_experiment_image_tag(
        normalized_request.registry,
        normalized_request.tag_suffix,
        arch,
        normalized_request.experiment_name,
    )
    platform_build = PlatformBuildSpec(
        platform=normalized_request.build_platforms,
        arch=arch,
        image_tag=image_tag,
        containerfile_path=str(containerfile_path),
        docker_context=str(docker_context),
        build_args=tuple(build_args),
        no_cache=normalized_request.no_cache,
    )
    return BuildSpec(
        build_kind="experiment",
        container_type="experiment",
        registry=normalized_request.registry,
        tag_suffix=normalized_request.tag_suffix,
        source=BuildSourceSpec(
            source_kind=source_kind,
            experiment_name=normalized_request.experiment_name,
            base_image=resolved_base_image or normalized_request.base_image,
            uses_custom_containerfile=has_custom_containerfile,
        ),
        platform_builds=(platform_build,),
        verification=_verification_spec(
            "experiment",
            normalized_request.validation_mode,
            normalized_request.build_platforms,
        ),
        publication=_local_publication_spec(image_tag),
    )


def plan_experiment_build_spec(
    request: ExperimentBuildRequest,
    *,
    container_engine: str | None = None,
    validate_base_image: bool = True,
) -> BuildSpec:
    """Return the shared build spec for an experiment build request."""

    return _plan_experiment_build_spec(
        normalize_experiment_build_request(request),
        container_engine=container_engine,
        validate_base_image=validate_base_image,
    )


def plan_build_spec(
    request: BuildRequest,
    *,
    container_engine: str | None = None,
) -> BuildSpec:
    """Return the shared build spec for a build entrypoint request."""

    normalized_request = normalize_build_request(request)
    if normalized_request.container_type in {"core", "full", "dev"}:
        return _plan_standard_build_spec(normalized_request)
    if normalized_request.container_type == "custom":
        custom_spec = _plan_source_build_spec(
            normalize_source_build_request(
                _local_source_build_request(
                    registry=normalized_request.registry,
                    target_platform=normalized_request.target_platform,
                    mpich_version=normalized_request.mpich_version,
                    build_ncpus=normalized_request.build_ncpus,
                    tag_suffix=normalized_request.tag_suffix,
                    tag_suffix_set=normalized_request.tag_suffix_set,
                    enable_perf_tracking=normalized_request.enable_perf_tracking,
                    no_cache=normalized_request.no_cache,
                    sst_core_path=normalized_request.sst_core_path,
                    sst_core_repo=normalized_request.sst_core_repo,
                    sst_core_ref=normalized_request.sst_core_ref,
                    sst_elements_repo=normalized_request.sst_elements_repo,
                    sst_elements_ref=normalized_request.sst_elements_ref,
                    container_engine=normalized_request.container_engine,
                )
            )
        )
        return replace(
            custom_spec,
            build_kind="local",
            source_download=_source_download_spec_for_build(normalized_request),
            verification=_verification_spec(
                "custom",
                normalized_request.validation_mode,
                normalized_request.target_platform,
            ),
        )
    if normalized_request.container_type == "experiment":
        experiment_spec = _plan_experiment_build_spec(
            normalize_experiment_build_request(
                ExperimentBuildRequest(
                    experiment_name=normalized_request.experiment_name,
                    base_image=normalized_request.base_image,
                    build_platforms=normalized_request.target_platform,
                    registry=normalized_request.registry,
                    tag_suffix=normalized_request.tag_suffix,
                    validation_mode=normalized_request.validation_mode,
                    no_cache=normalized_request.no_cache,
                    container_engine=normalized_request.container_engine,
                )
            ),
            container_engine=container_engine,
            validate_base_image=False,
        )
        return replace(
            experiment_spec,
            build_kind="local",
            source_download=_source_download_spec_for_build(normalized_request),
            verification=_verification_spec(
                "experiment",
                normalized_request.validation_mode,
                normalized_request.target_platform,
            ),
        )
    raise OrchestrationError(f"Unknown container type: {normalized_request.container_type}")


def _validate_build_image(
    *,
    build_spec: BuildSpec,
    container_engine: str,
    image_tag: str,
    target_platform: str,
) -> int | None:
    """Validate an image produced by the build entrypoint."""

    log_info(f"Validating container: {image_tag}")
    return _run_image_validation(
        build_spec.verification.mode,
        container_engine=container_engine,
        image_tag=image_tag,
        target_platform=target_platform,
        max_size_mb=build_spec.verification.max_size_mb,
        validation_profile="development" if build_spec.container_type == "dev" else "runtime",
        skip_message="Skipping validation (validation mode: none)",
        quick_success_message="Quick container validation passed",
        metadata_success_message="Metadata-only container validation passed",
        full_success_message="Container validation passed",
        return_image_size=True,
    )


def _cleanup_build(container_engine: str, image_tag: str) -> None:
    """Remove the built image, marker file, and builder cache for the build entrypoint."""

    log_info("Cleaning up...")
    log_info(f"Removing image: {image_tag}")
    _remove_image(
        container_engine,
        image_tag,
        warning_message="Failed to remove image",
    )
    _remove_last_built_image()

    prune_result = _run_command([container_engine, "builder", "prune", "-f"])
    if prune_result.returncode != 0:
        log_warning("Failed to prune build cache")

    log_success("Cleanup completed")


def build(request: BuildRequest) -> BuildResult:
    """Execute the build entrypoint path from explicit arguments."""

    normalized_request = normalize_build_request(request)
    container_engine = detect_container_engine(normalized_request.container_engine)
    build_spec = plan_build_spec(
        normalized_request,
        container_engine=container_engine,
    )
    sst_elements_version = normalized_request.sst_elements_version or normalized_request.sst_version

    log_info("=== Build Entry Point ===")
    log_info("Execution Mode: local")
    log_info(f"Container Type: {normalized_request.container_type}")
    log_info(f"Platform: {normalized_request.target_platform}")
    log_info(f"Container Engine: {container_engine}")
    log_info(f"Registry: {normalized_request.registry}")
    log_info(f"SST Version: {normalized_request.sst_version}")
    if sst_elements_version:
        log_info(f"SST Elements Version: {sst_elements_version}")
    log_info(f"MPICH Version: {normalized_request.mpich_version}")
    log_info("Starting build sequence...")

    image_tag = ""
    image_size_mb: int | None = None
    try:
        if not normalized_request.validate_only:
            if not (REPO_ROOT / "Containerfiles").is_dir():
                raise OrchestrationError(
                    "Containerfiles directory not found. Please run from project root."
                )

            if build_spec.source_download is None:
                raise OrchestrationError("Build spec did not include a download plan")

            _download_build_sources(
                build_spec.source_download,
                download_script_override=normalized_request.download_script,
            )

            if normalized_request.container_type in {"core", "full", "dev"}:
                image_tag = _build_standard_image(
                    build_spec,
                    container_engine=container_engine,
                )
            elif normalized_request.container_type == "custom":
                image_tag = _delegate_local_source_build(
                    registry=normalized_request.registry,
                    target_platform=normalized_request.target_platform,
                    mpich_version=normalized_request.mpich_version,
                    build_ncpus=normalized_request.build_ncpus,
                    tag_suffix=normalized_request.tag_suffix,
                    tag_suffix_set=normalized_request.tag_suffix_set,
                    enable_perf_tracking=normalized_request.enable_perf_tracking,
                    no_cache=normalized_request.no_cache,
                    sst_core_path=normalized_request.sst_core_path,
                    sst_core_repo=normalized_request.sst_core_repo,
                    sst_core_ref=normalized_request.sst_core_ref,
                    sst_elements_repo=normalized_request.sst_elements_repo,
                    sst_elements_ref=normalized_request.sst_elements_ref,
                    container_engine=container_engine,
                )
            elif normalized_request.container_type == "experiment":
                image_tag = _delegate_local_experiment_build(
                    registry=normalized_request.registry,
                    target_platform=normalized_request.target_platform,
                    tag_suffix=normalized_request.tag_suffix,
                    base_image=normalized_request.base_image,
                    experiment_name=normalized_request.experiment_name,
                    no_cache=normalized_request.no_cache,
                    container_engine=container_engine,
                )
            else:
                raise OrchestrationError(f"Unknown container type: {normalized_request.container_type}")

            _write_last_built_image(image_tag)
        else:
            image_tag = _read_last_built_image()
            if not image_tag:
                raise OrchestrationError("No image tag specified for validation")

        image_size_mb = _validate_build_image(
            build_spec=build_spec,
            container_engine=container_engine,
            image_tag=image_tag,
            target_platform=normalized_request.target_platform,
        )

        if normalized_request.cleanup:
            _cleanup_build(container_engine, image_tag)
        else:
            log_info("Image preserved. Use --cleanup to remove after the build.")
            log_info(f"Built image: {image_tag}")

        log_success("Build sequence completed successfully!")
        return BuildResult(
            image_tag=image_tag,
            container_type=normalized_request.container_type,
            image_size_mb=image_size_mb,
        )
    except Exception:
        _remove_last_built_image()
        raise


def _inspect_image_json(engine: str, image_tag: str) -> dict[str, Any]:
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


def _image_size_mb_from_metadata(metadata: dict[str, Any]) -> int:
    """Extract image size in MB from container metadata."""

    return int(metadata.get("Size", 0)) // 1024 // 1024


def quick_validate_image(engine: str, image_tag: str) -> None:
    """Perform lightweight validation without creating a container."""

    log_info(f"Quick validation of {image_tag}")
    metadata = _inspect_image_json(engine, image_tag)
    image_size_mb = _image_size_mb_from_metadata(metadata)
    log_success("Image exists")
    log_info(f"Image size: {image_size_mb}MB")
    if not metadata.get("Config"):
        raise OrchestrationError("Image inspection failed")
    log_success("Image inspection passed")
    log_success("Quick validation passed")


def metadata_validate_image(
    engine: str,
    image_tag: str,
    max_size_mb: int,
    *,
    validation_profile: str = "runtime",
) -> None:
    """Perform metadata-only validation without running the container."""

    log_info(f"No-exec validation of {image_tag}")
    metadata = _inspect_image_json(engine, image_tag)
    image_size_mb = _image_size_mb_from_metadata(metadata)

    log_success("Image exists")
    log_info(f"Image size: {image_size_mb}MB")
    if image_size_mb > max_size_mb:
        raise OrchestrationError(f"Image size {image_size_mb}MB exceeds limit {max_size_mb}MB")
    log_success("Image size check passed")

    architecture = metadata.get("Architecture", "unknown")
    log_info(f"Image architecture: {architecture}")

    config_env = metadata.get("Config", {}).get("Env", []) or []
    joined_env = "\n".join(config_env).lower()
    if validation_profile == "development":
        if "path" in joined_env or "lang=" in joined_env or "lc_all=" in joined_env:
            log_success("Expected development image environment variables found")
        else:
            log_info("Development image environment-variable check skipped")
    elif "path" in joined_env and ("sst" in joined_env or "mpi" in joined_env):
        log_success("Expected runtime environment variables found")
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
    *,
    pull_image: bool = True,
) -> ValidateContainerResult:
    """Validate a pulled container image using explicit parameters."""

    start_group("Validate Container")
    log_info(f"Image:    {image_tag}")
    log_info(f"Platform: {target_platform}")
    log_info(f"Max size: {max_size_mb} MB")
    log_info(f"Engine:   {container_engine}")

    if pull_image:
        log_info("Pulling image...")
        pull_result = _run_command([container_engine, "pull", image_tag])
        if pull_result.returncode != 0:
            end_group()
            raise OrchestrationError(f"Failed to pull image: {image_tag}")
    else:
        log_info("Using locally available image...")

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


def experiment_build(request: ExperimentBuildRequest) -> ExperimentBuildResult:
    """Execute the experiment build path from explicit arguments."""

    normalized_request = normalize_experiment_build_request(request)

    container_engine = detect_container_engine(normalized_request.container_engine)
    build_spec = _plan_experiment_build_spec(
        normalized_request,
        container_engine=container_engine,
        validate_base_image=True,
    )
    platform_build = build_spec.primary_platform_build

    log_info("Starting experiment container build...")
    log_info("Configuration:")
    log_info(f"  Experiment: {normalized_request.experiment_name}")
    log_info("  Container type: experiment")
    log_info(
        f"  Containerfile type: {'custom' if build_spec.source.uses_custom_containerfile else 'template'}"
    )
    log_info(f"  Containerfile path: {platform_build.containerfile_path}")
    log_info(f"  Docker context: {platform_build.docker_context}")
    log_info(f"  Tag: {platform_build.image_tag}")
    log_info(f"  Platforms: {platform_build.platform}")
    log_info(f"  Validation: {build_spec.verification.mode}")
    if platform_build.build_args:
        log_info("  Build args:")
        for build_arg in platform_build.build_args:
            log_info(f"    {build_arg}")

    start_group("Container Build")
    build_result = _run_command(
        _create_container_build_command(
            container_engine,
            _container_plan_from_platform_build(platform_build),
        )
    )
    end_group()
    if build_result.returncode != 0:
        raise OrchestrationError("Experiment container build failed")

    log_info(f"Container built successfully: {platform_build.image_tag}")

    _run_image_validation(
        build_spec.verification.mode,
        container_engine=container_engine,
        image_tag=platform_build.image_tag,
        target_platform=platform_build.platform,
        max_size_mb=build_spec.verification.max_size_mb,
        pre_message="Running container validation...",
        skip_message="Skipping validation (validation mode: none)",
        quick_success_message="Quick container validation passed",
        metadata_success_message="Metadata-only container validation passed",
        full_success_message="Full container validation passed",
    )

    log_info("Experiment build completed successfully!")
    return ExperimentBuildResult(
        image_tag=platform_build.image_tag,
        containerfile_type="custom" if build_spec.source.uses_custom_containerfile else "template",
        containerfile_path=platform_build.containerfile_path,
        docker_context=platform_build.docker_context,
    )


def source_build(request: SourceBuildRequest) -> SourceBuildResult:
    """Execute the source build path from explicit arguments."""

    normalized_request = normalize_source_build_request(request)
    build_spec = _plan_source_build_spec(normalized_request)
    platform_build = build_spec.primary_platform_build
    build_type = platform_build.build_target
    using_local_core_checkout = build_spec.source.uses_local_core_checkout
    container_engine = detect_container_engine(normalized_request.container_engine)

    start_group("Source SST Container Build")
    log_info("Build Configuration:")
    if using_local_core_checkout:
        log_info(f"  SST Core Checkout: {normalized_request.sst_core_path}")
    else:
        log_info(f"  SST Core Repository: {normalized_request.sst_core_repo}")
        log_info(f"  SST Core Reference: {normalized_request.sst_core_ref}")
    if normalized_request.sst_elements_repo:
        log_info(f"  SST Elements Repository: {normalized_request.sst_elements_repo}")
        log_info(f"  SST Elements Reference: {normalized_request.sst_elements_ref}")
    log_info(f"  MPICH Version: {normalized_request.mpich_version}")
    log_info(f"  Performance Tracking: {str(normalized_request.enable_perf_tracking).lower()}")
    log_info(f"  Build Type: {build_type}")
    log_info(f"  Target Platform: {normalized_request.target_platform}")
    log_info(f"  Container Engine: {container_engine}")
    log_info(f"  Image Tag: {platform_build.image_tag}")
    end_group()

    staged_local_source = False
    if using_local_core_checkout:
        stage_local_sst_core_checkout(normalized_request.sst_core_path)
        staged_local_source = True

    try:
        build_time_seconds = _run_container_build(
            _container_plan_from_platform_build(platform_build),
            container_engine=container_engine,
            failure_message="Container build failed",
            cwd=REPO_ROOT,
        )
        log_success(f"Container build completed in {build_time_seconds}s")

        image_size_mb = _inspect_built_image_size(container_engine, platform_build.image_tag)

        _run_image_validation(
            build_spec.verification.mode,
            container_engine=container_engine,
            image_tag=platform_build.image_tag,
            target_platform=normalized_request.target_platform,
            max_size_mb=build_spec.verification.max_size_mb,
            group_name="Validating Container",
            quick_success_message="Quick container validation passed",
            metadata_success_message="Metadata-only container validation passed",
            full_success_message="Container validation passed",
        )

        if normalized_request.cleanup:
            log_info(f"Cleaning up image: {platform_build.image_tag}")
            if _remove_image(
                container_engine,
                platform_build.image_tag,
                warning_message="Failed to clean up image",
            ):
                log_success("Image cleaned up successfully")

        log_success("Source build completed successfully")
        log_info(f"Image: {platform_build.image_tag}")

        if normalized_request.github_actions_mode or os.environ.get("GITHUB_ACTIONS") == "true":
            set_output("image-tag", platform_build.image_tag)
            set_output("build-time", str(build_time_seconds))
            set_output("image-size-mb", str(image_size_mb))
            set_output("platform", normalized_request.target_platform)
            set_output("build-successful", "true")

        return SourceBuildResult(
            image_tag=platform_build.image_tag,
            build_type=build_type,
            image_size_mb=image_size_mb,
        )
    finally:
        if staged_local_source:
            reset_local_source_stage_dir()


def _run_image_validation(
    validation_mode: str,
    *,
    container_engine: str,
    image_tag: str,
    target_platform: str,
    max_size_mb: int,
    validation_profile: str = "runtime",
    pre_message: str | None = None,
    skip_message: str | None = None,
    group_name: str | None = None,
    quick_success_message: str = "Quick container validation passed",
    metadata_success_message: str = "Metadata-only container validation passed",
    full_success_message: str = "Container validation passed",
    return_image_size: bool = False,
    pull_image: bool = False,
) -> int | None:
    """Run one of the supported validation modes and optionally return image size."""

    if validation_mode == "none":
        if skip_message:
            log_info(skip_message)
        return None

    if pre_message:
        log_info(pre_message)

    if group_name:
        start_group(group_name)

    try:
        if validation_mode == "quick":
            quick_validate_image(container_engine, image_tag)
            log_success(quick_success_message)
            return None

        if validation_mode == "metadata":
            metadata_validate_image(
                container_engine,
                image_tag,
                max_size_mb,
                validation_profile=validation_profile,
            )
            log_success(metadata_success_message)
            if return_image_size:
                metadata = _inspect_image_json(container_engine, image_tag)
                return _image_size_mb_from_metadata(metadata)
            return None

        if validation_mode == "full":
            result = _validate_container(
                container_engine,
                image_tag,
                target_platform,
                max_size_mb,
                pull_image=pull_image,
            )
            log_success(full_success_message)
            if return_image_size:
                return result.image_size_mb
            return None

        raise OrchestrationError(f"Unsupported validation mode: {validation_mode}")
    finally:
        if group_name:
            end_group()
