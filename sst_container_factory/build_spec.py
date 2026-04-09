"""Shared build-spec dataclasses for SST container planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDownloadSpec:
    """External source archives required before a build can execute."""

    destination_dir: str
    mpich_version: str = ""
    sst_version: str = ""
    sst_elements_version: str = ""
    download_mpich: bool = False
    download_sst_core: bool = False
    download_sst_elements: bool = False
    force_mode: bool = True


@dataclass(frozen=True)
class BuildSourceSpec:
    """Normalized description of the logical inputs behind a build."""

    source_kind: str
    mpich_version: str = ""
    sst_version: str = ""
    sst_elements_version: str = ""
    sst_core_repo: str = ""
    sst_core_ref: str = ""
    sst_core_path: str = ""
    sst_elements_repo: str = ""
    sst_elements_ref: str = ""
    experiment_name: str = ""
    base_image: str = ""
    uses_local_core_checkout: bool = False
    uses_custom_containerfile: bool = False


@dataclass(frozen=True)
class PlatformBuildSpec:
    """Concrete build invocation for one target platform."""

    platform: str
    arch: str
    image_tag: str
    containerfile_path: str
    docker_context: str
    build_target: str = ""
    build_args: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    no_cache: bool = False


@dataclass(frozen=True)
class VerificationSpec:
    """Validation policy attached to a logical image build."""

    mode: str
    max_size_mb: int
    platforms: tuple[str, ...]
    requires_runtime_validation: bool


@dataclass(frozen=True)
class PublicationSpec:
    """Publication outputs associated with a logical image build."""

    publish_enabled: bool
    manifest_tag: str = ""
    platform_tags: tuple[str, ...] = ()
    alias_tags: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildSpec:
    """Wholistic description of one repository image build."""

    build_kind: str
    container_type: str
    registry: str
    tag_suffix: str
    source: BuildSourceSpec
    platform_builds: tuple[PlatformBuildSpec, ...]
    verification: VerificationSpec
    publication: PublicationSpec
    source_download: SourceDownloadSpec | None = None

    @property
    def primary_platform_build(self) -> PlatformBuildSpec:
        """Return the single-platform build entry expected by current executors."""

        if not self.platform_builds:
            raise ValueError("Build spec must contain at least one platform build")
        return self.platform_builds[0]