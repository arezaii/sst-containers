"""Environment and workflow adapters for the orchestration layer."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from . import orchestration as orchestration_module
from .github_actions import end_group, set_output, start_group
from .logging_utils import log_error, log_info, log_success
from .orchestration import (
    SourceBuildRequest,
    SourceBuildResult,
    source_build,
    DEFAULT_BUILD_NCPUS,
    DEFAULT_MPICH_VERSION,
    DEFAULT_REGISTRY,
    DEFAULT_SST_CORE_REPO,
    DEFAULT_SST_VERSION,
    ExperimentBuildRequest,
    ExperimentBuildResult,
    experiment_build,
    LocalBuildRequest,
    LocalBuildResult,
    local_build,
    plan_workflow_build_spec,
    PrepareImageConfigResult,
    ValidateContainerResult,
    ValidateSourceInputsResult,
    ValidateExperimentInputsResult,
    WorkflowBuildRequest,
)


def _env_map(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    """Return the effective environment mapping."""

    return env or os.environ


def _env_flag(env: Mapping[str, str], name: str, default: str = "false") -> bool:
    """Read a repository-style boolean flag from an environment mapping."""

    return env.get(name, default) == "true"


def _workflow_build_labels(env: Mapping[str, str], build_spec: orchestration_module.BuildSpec) -> dict[str, str]:
    """Collect workflow build labels to embed in the emitted Buildx bake file."""

    labels = {
        "com.container.type": build_spec.container_type,
        "sst.perf_tracking": env.get("ENABLE_PERF_TRACKING", "false"),
    }
    github_label_fields = {
        "com.github.sha": "GITHUB_SHA",
        "com.github.workflow": "GITHUB_WORKFLOW",
        "com.github.run_id": "GITHUB_RUN_ID",
        "com.github.run_number": "GITHUB_RUN_NUMBER",
        "com.github.repository": "GITHUB_REPOSITORY",
        "com.github.ref_name": "GITHUB_REF_NAME",
    }
    for label_name, env_name in github_label_fields.items():
        value = env.get(env_name, "")
        if value:
            labels[label_name] = value
    return labels


def local_build_request_from_env(env: Mapping[str, str] | None = None) -> LocalBuildRequest:
    """Build a local-build request object from environment variables."""

    env_map = _env_map(env)
    sst_version = env_map.get("SST_VERSION", DEFAULT_SST_VERSION)
    return LocalBuildRequest(
        container_type=env_map.get("CONTAINER_TYPE", ""),
        validate_only=_env_flag(env_map, "VALIDATE_ONLY"),
        validation_mode=env_map.get("VALIDATION_MODE", "full"),
        cleanup=_env_flag(env_map, "CLEANUP"),
        registry=env_map.get("REGISTRY", DEFAULT_REGISTRY),
        sst_version=sst_version,
        sst_elements_version=env_map.get("SST_ELEMENTS_VERSION", sst_version),
        mpich_version=env_map.get("MPICH_VERSION", DEFAULT_MPICH_VERSION),
        build_ncpus=env_map.get("BUILD_NCPUS", DEFAULT_BUILD_NCPUS),
        target_platform=env_map.get("TARGET_PLATFORM", ""),
        enable_perf_tracking=_env_flag(env_map, "ENABLE_PERF_TRACKING"),
        tag_suffix=env_map.get("TAG_SUFFIX", ""),
        tag_suffix_set=_env_flag(env_map, "TAG_SUFFIX_SET"),
        no_cache=_env_flag(env_map, "NO_CACHE"),
        experiment_name=env_map.get("EXPERIMENT_NAME", ""),
        base_image=env_map.get("BASE_IMAGE", ""),
        sst_core_path=env_map.get("SST_CORE_PATH", ""),
        sst_core_repo=env_map.get("SST_CORE_REPO", DEFAULT_SST_CORE_REPO),
        sst_core_ref=env_map.get("SST_CORE_REF", ""),
        sst_elements_repo=env_map.get("SST_ELEMENTS_REPO", ""),
        sst_elements_ref=env_map.get("SST_ELEMENTS_REF", ""),
        container_engine=env_map.get("CONTAINER_ENGINE"),
        download_script=env_map.get("DOWNLOAD_SCRIPT", ""),
    )


def experiment_build_request_from_env(env: Mapping[str, str] | None = None) -> ExperimentBuildRequest:
    """Build an experiment request object from environment variables."""

    env_map = _env_map(env)
    return ExperimentBuildRequest(
        experiment_name=env_map.get("EXPERIMENT_NAME", ""),
        base_image=env_map.get("BASE_IMAGE", ""),
        build_platforms=env_map.get("BUILD_PLATFORMS", ""),
        registry=env_map.get("REGISTRY", DEFAULT_REGISTRY),
        tag_suffix=env_map.get("TAG_SUFFIX", "latest"),
        validation_mode=env_map.get("VALIDATION_MODE", "full"),
        no_cache=_env_flag(env_map, "NO_CACHE"),
        container_engine=env_map.get("CONTAINER_ENGINE"),
        build_args=tuple(line for line in env_map.get("BUILD_ARGS_SERIALIZED", "").splitlines() if line),
    )


def source_build_request_from_env(env: Mapping[str, str] | None = None) -> SourceBuildRequest:
    """Build a source-build request object from environment variables."""

    env_map = _env_map(env)
    return SourceBuildRequest(
        target_platform=env_map.get("TARGET_PLATFORM", ""),
        tag_suffix=env_map.get("TAG_SUFFIX", ""),
        sst_core_path=env_map.get("SST_CORE_PATH", ""),
        sst_core_repo=env_map.get("SST_CORE_REPO", DEFAULT_SST_CORE_REPO),
        sst_core_ref=env_map.get("SST_CORE_REF", ""),
        sst_elements_repo=env_map.get("SST_ELEMENTS_REPO", ""),
        sst_elements_ref=env_map.get("SST_ELEMENTS_REF", ""),
        mpich_version=env_map.get("MPICH_VERSION", DEFAULT_MPICH_VERSION),
        build_ncpus=env_map.get("BUILD_NCPUS", DEFAULT_BUILD_NCPUS),
        registry=env_map.get("REGISTRY", DEFAULT_REGISTRY),
        enable_perf_tracking=_env_flag(env_map, "ENABLE_PERF_TRACKING"),
        no_cache=_env_flag(env_map, "NO_CACHE"),
        cleanup=_env_flag(env_map, "CLEANUP"),
        validation_mode=env_map.get("VALIDATION_MODE", "none"),
        container_engine=env_map.get("CONTAINER_ENGINE"),
        github_actions_mode=_env_flag(env_map, "GITHUB_ACTIONS_MODE"),
    )


def workflow_build_request_from_env(env: Mapping[str, str] | None = None) -> WorkflowBuildRequest:
    """Build a reusable-workflow request object from environment variables."""

    env_map = _env_map(env)
    return WorkflowBuildRequest(
        container_type=env_map.get("CONTAINER_TYPE", ""),
        image_prefix=env_map.get("IMAGE_PREFIX", ""),
        build_platforms=env_map.get("BUILD_PLATFORMS", "linux/amd64,linux/arm64"),
        tag_suffix=env_map.get("TAG_SUFFIX", ""),
        registry=env_map.get("REGISTRY", "ghcr.io"),
        sst_version=env_map.get("SST_VERSION", ""),
        sst_elements_version=env_map.get("SST_ELEMENTS_VERSION", ""),
        mpich_version=env_map.get("MPICH_VERSION", DEFAULT_MPICH_VERSION),
        build_ncpus=env_map.get("BUILD_NCPUS", DEFAULT_BUILD_NCPUS),
        sst_core_repo=env_map.get("SST_CORE_REPO", DEFAULT_SST_CORE_REPO),
        sst_core_ref=env_map.get("SST_CORE_REF", ""),
        sst_elements_repo=env_map.get("SST_ELEMENTS_REPO", ""),
        sst_elements_ref=env_map.get("SST_ELEMENTS_REF", ""),
        experiment_name=env_map.get("EXPERIMENT_NAME", ""),
        base_image=env_map.get("BASE_IMAGE", ""),
        enable_perf_tracking=_env_flag(env_map, "ENABLE_PERF_TRACKING"),
        no_cache=_env_flag(env_map, "IGNORE_CACHE") or _env_flag(env_map, "NO_CACHE"),
        validation_mode=env_map.get("VALIDATION_MODE", "full"),
        tag_as_latest=_env_flag(env_map, "TAG_AS_LATEST"),
        publish_master_latest=_env_flag(env_map, "PUBLISH_MASTER_LATEST"),
    )


def prepare_workflow_build_from_env(env: Mapping[str, str] | None = None) -> orchestration_module.BuildSpec:
    """Compute the reusable-workflow build plan and publish its outputs."""

    env_map = _env_map(env)
    build_spec = plan_workflow_build_spec(workflow_build_request_from_env(env_map))
    bake_plan = orchestration_module.plan_workflow_bake(
        build_spec,
        labels=_workflow_build_labels(env_map, build_spec),
        workspace_root=Path(env_map.get("GITHUB_WORKSPACE", str(orchestration_module.REPO_ROOT))),
    )
    source_download = build_spec.source_download
    platform_matrix = {
        "include": [
            {
                "platform": bake_target.platform,
                "arch": bake_target.arch,
                "image_tag": bake_target.image_tag,
                "bake_target": bake_target.name,
            }
            for bake_target in bake_plan.targets
        ]
    }

    start_group("Prepare Workflow Build Plan")
    log_info(f"Container type: {build_spec.container_type}")
    log_info(f"Manifest tag:   {build_spec.publication.manifest_tag}")
    for platform_build in build_spec.platform_builds:
        log_info(
            f"Platform build: {platform_build.platform} -> {platform_build.image_tag}"
        )
        log_info(f"  Containerfile: {platform_build.containerfile_path}")
        log_info(f"  Context:       {platform_build.docker_context}")
        if platform_build.build_target:
            log_info(f"  Target:        {platform_build.build_target}")

    set_output("platform_matrix", json.dumps(platform_matrix, separators=(",", ":")))
    set_output(
        "bake_definition_json",
        json.dumps(bake_plan.definition, separators=(",", ":"), sort_keys=True),
    )
    set_output("manifest_tag", build_spec.publication.manifest_tag)
    set_output("resolved_tag_suffix", build_spec.tag_suffix)
    set_output("validation_mode", build_spec.verification.mode)
    set_output("max_image_size_mb", str(build_spec.verification.max_size_mb))
    set_output(
        "alias_tags_json",
        json.dumps(list(build_spec.publication.alias_tags), separators=(",", ":")),
    )
    set_output("download_mpich", str(bool(source_download and source_download.download_mpich)).lower())
    set_output("download_sst_core", str(bool(source_download and source_download.download_sst_core)).lower())
    set_output(
        "download_sst_elements",
        str(bool(source_download and source_download.download_sst_elements)).lower(),
    )
    set_output("mpich_version", source_download.mpich_version if source_download else "")
    set_output("sst_version", source_download.sst_version if source_download else "")
    set_output(
        "sst_elements_version",
        source_download.sst_elements_version if source_download else "",
    )
    set_output(
        "source_download",
        json.dumps(asdict(source_download), separators=(",", ":")) if source_download else "{}",
    )
    end_group()
    log_success("Workflow build plan ready")
    return build_spec


def prepare_image_config_from_env(env: Mapping[str, str] | None = None) -> PrepareImageConfigResult:
    """Compute workflow image naming outputs from environment variables."""

    env_map = _env_map(env)
    container_type = env_map.get("CONTAINER_TYPE", "")
    image_prefix = env_map.get("IMAGE_PREFIX", "")
    tag_suffix = env_map.get("TAG_SUFFIX", "")
    registry = env_map.get("REGISTRY", "ghcr.io")
    enable_perf_tracking = env_map.get("ENABLE_PERF_TRACKING", "false")
    experiment_name = env_map.get("EXPERIMENT_NAME", "")

    if not container_type:
        raise ValueError("CONTAINER_TYPE is required")
    if not image_prefix:
        raise ValueError("IMAGE_PREFIX is required")
    if not tag_suffix:
        raise ValueError("TAG_SUFFIX is required")

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


def validate_source_inputs_from_env(env: Mapping[str, str] | None = None) -> ValidateSourceInputsResult:
    """Validate build-custom workflow inputs from environment variables."""

    env_map = _env_map(env)
    core_ref = env_map.get("CORE_REF", "")
    elements_repo = env_map.get("ELEMENTS_REPO", "")
    elements_ref = env_map.get("ELEMENTS_REF", "")
    image_tag = env_map.get("IMAGE_TAG", "")

    if not core_ref:
        raise ValueError("CORE_REF (sst_core_ref input) is required")

    start_group("Validate Source Build Inputs")
    if elements_repo:
        if not elements_ref:
            raise ValueError(
                "SST-elements ref (ELEMENTS_REF) is required when elements_repo is provided"
            )
        build_type = "full"
        log_info("Build type: full (core + elements)")
    else:
        build_type = "core"
        log_info("Build type: core only")

    tag_suffix = image_tag or orchestration_module.sanitize_tag_suffix(core_ref)
    if image_tag:
        log_info(f"Tag suffix: {tag_suffix} (explicit)")
    else:
        log_info(f"Tag suffix: {tag_suffix} (derived from core ref)")
    end_group()

    result = ValidateSourceInputsResult(build_type=build_type, tag_suffix=tag_suffix)
    set_output("build_type", result.build_type)
    set_output("tag_suffix", result.tag_suffix)
    log_success(
        f"Input validation complete: build_type={result.build_type}, tag_suffix={result.tag_suffix}"
    )
    return result


def validate_experiment_inputs_from_env(env: Mapping[str, str] | None = None) -> ValidateExperimentInputsResult:
    """Validate build-experiment workflow inputs from environment variables."""

    env_map = _env_map(env)
    experiment_name = env_map.get("EXPERIMENT_NAME", "")
    base_image = env_map.get("BASE_IMAGE", "sst-core:latest")
    repo_owner = env_map.get("REPO_OWNER", env_map.get("USER", ""))
    container_engine = orchestration_module.detect_container_engine(env_map.get("CONTAINER_ENGINE"))

    if not experiment_name:
        raise ValueError("EXPERIMENT_NAME is required")

    start_group("Validate Experiment Inputs")
    log_info(f"Experiment name: {experiment_name}")

    experiment_dir = orchestration_module.REPO_ROOT / experiment_name
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
        resolved_base_image = orchestration_module.resolve_base_image_reference(base_image, repo_owner)
        log_info(f"Resolved base image: {resolved_base_image}")
        set_output("resolved_base_image", resolved_base_image)
        if not orchestration_module.inspect_remote_manifest(container_engine, resolved_base_image):
            raise FileNotFoundError(
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


def local_build_from_env(env: Mapping[str, str] | None = None) -> LocalBuildResult:
    """Execute the local-build path from normalized environment variables."""

    return local_build(local_build_request_from_env(env))


def experiment_build_from_env(env: Mapping[str, str] | None = None) -> ExperimentBuildResult:
    """Execute the experiment build path from normalized environment variables."""

    return experiment_build(experiment_build_request_from_env(env))


def source_build_from_env(env: Mapping[str, str] | None = None) -> SourceBuildResult:
    """Execute the source build path from normalized environment variables."""

    return source_build(source_build_request_from_env(env))


def validate_container_from_env(env: Mapping[str, str] | None = None) -> ValidateContainerResult:
    """Validate a pulled container image using environment variables."""

    env_map = _env_map(env)
    image_tag = env_map.get("IMAGE_TAG", "")
    target_platform = env_map.get("PLATFORM", "")
    max_size_mb = int(env_map.get("MAX_SIZE_MB", "2048"))
    validation_mode = env_map.get("VALIDATION_MODE", "full")
    container_engine = orchestration_module.detect_container_engine(env_map.get("CONTAINER_ENGINE"))

    if not image_tag:
        raise ValueError("IMAGE_TAG is required")
    if not target_platform:
        raise ValueError("PLATFORM is required")

    if validation_mode == "full":
        return orchestration_module._validate_container(
            container_engine,
            image_tag,
            target_platform,
            max_size_mb,
        )

    image_size_mb = orchestration_module._run_image_validation(
        validation_mode,
        container_engine=container_engine,
        image_tag=image_tag,
        target_platform=target_platform,
        max_size_mb=max_size_mb,
        pre_message="Running container validation...",
        skip_message="Skipping validation (validation mode: none)",
        quick_success_message="Quick container validation passed",
        metadata_success_message="Metadata-only container validation passed",
        full_success_message="Container validation passed",
        return_image_size=True,
    )
    return ValidateContainerResult(
        image_tag=image_tag,
        platform=target_platform,
        image_size_mb=image_size_mb or 0,
    )