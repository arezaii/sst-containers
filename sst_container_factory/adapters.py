"""Environment and workflow adapters for the orchestration layer."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from . import orchestration as orchestration_module
from .github_actions import end_group, set_output, start_group
from .logging_utils import log_info, log_success
from .orchestration import (
    DEFAULT_BUILD_NCPUS,
    DEFAULT_MPICH_VERSION,
    DEFAULT_SST_CORE_REPO,
    plan_workflow_build_spec,
    ValidateContainerResult,
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
            pull_image=True,
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
