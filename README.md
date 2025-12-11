# SST Container Factory

Containerized SST (Structural Simulation Toolkit) environments with automated GitHub Actions workflows.

## Container Types

1. **Release Containers** - Official SST releases (e.g., v15.1.0)
2. **Development Containers** - Build dependencies for SST development
3. **Custom Builds** - Custom SST from any git repository/branch/commit
4. **Experiment Containers** - Package experiment scripts with base SST environment
5. **Nightly Builds** - Automated builds from latest SST master branch

## GitHub Actions Workflows

### User-Facing Workflows

#### Build SST Release Containers

**Workflow**: `build-release.yml`

**Purpose**: Build official SST release versions

**Required Parameters**:
- `sst_version`: SST version to build (e.g., "v15.1.0")
- `container_types`: Types to build - "core", "full", or both

**Optional Parameters**:
- `build_platforms`: Platforms to build for (default: "linux/amd64,linux/arm64")
- `mpich_version`: MPICH version (default: "4.0.2")
- `force_rebuild`: Force rebuild even if image exists (default: false)
- `ignore_cache`: Ignore build cache (default: false)

**Output**: `ghcr.io/{owner}/ar-sst-core:{version}` and/or `ghcr.io/{owner}/ar-sst-full:{version}`

#### Build SST Development Container
**Workflow**: `build-dev.yml`

**Purpose**: Build development environment with SST dependencies (no SST itself)

**Optional Parameters**:
- `tag_suffix`: Container tag suffix (default: "latest")
- `mpich_version`: MPICH version (default: "4.0.2")
- `build_platforms`: Platforms to build for (default: "linux/amd64,linux/arm64")
- `force_rebuild`: Force rebuild (default: false)
- `ignore_cache`: Ignore build cache (default: false)

**Output**: `ghcr.io/{owner}/sst-dev:{tag_suffix}`

#### Build Custom SST Containers

**Workflow**: `build-custom.yml`

**Purpose**: Build SST from any git repository, branch, tag, or commit

**Required Parameters**:
- `image_name`: Name for the resulting container image
- `sst_core_repo`: SST-core git repository URL
- `sst_core_ref`: Branch, tag, or commit reference

**Optional Parameters**:
- `sst_elements_repo`: SST-elements git repository URL
- `sst_elements_ref`: SST-elements branch, tag, or commit
- `image_tag`: Custom tag for image (auto-generated if not provided)
- `build_platforms`: Platforms to build for (default: "linux/amd64,linux/arm64")
- `mpich_version`: MPICH version (default: "4.0.2")

**Output**: `ghcr.io/{owner}/{image_name}:{tag}`

#### Build Experiment Container

**Workflow**: `build-experiment.yml`

**Purpose**: Package experiment scripts with base SST environment

**Required Parameters**:
- `experiment_name`: Name of experiment directory (must exist in repository)

**Optional Parameters**:
- `base_image`: Base SST image (default: "ar-sst-core:latest", auto-resolves to current repo)
- `build_platforms`: Platforms to build for (default: "linux/amd64,linux/arm64")
- `tag_suffix`: Tag suffix (default: "latest")

**Output**: `ghcr.io/{owner}/{experiment_name}:{tag_suffix}`

**Note**: Automatically resolves base images - use `ar-sst-core:latest` for images in this repo, or full paths like `ghcr.io/user/image:tag` for external images.

#### Nightly SST Core Container Build

**Workflow**: `build-nightly.yml`

**Purpose**: Automated builds from SST master branch when new commits are detected

**Optional Parameters**:
- `mpich_version`: MPICH version (default: "4.0.2")
- `build_platforms`: Platforms to build for (default: "linux/amd64,linux/arm64")

**Output**: `ghcr.io/{owner}/ar-sst-core:master-{short_sha}` and `ghcr.io/{owner}/ar-sst-core:master-latest`

**Schedule**: Runs automatically on schedule to check for new commits

## Quick Start

### Use Pre-built Containers
```bash
# Pull official release (replace 'owner' with repository owner)
docker pull ghcr.io/owner/ar-sst-core:v15.1.0
docker run -it ghcr.io/owner/ar-sst-core:v15.1.0

# Pull development environment
docker pull ghcr.io/owner/sst-dev:latest
docker run -it ghcr.io/owner/sst-dev:latest

# Pull latest nightly build
docker pull ghcr.io/owner/ar-sst-core:master-latest
docker run -it ghcr.io/owner/ar-sst-core:master-latest
```

### Build via GitHub Actions
1. Go to the **Actions** tab
2. Select the appropriate workflow from the left sidebar
3. Click **Run workflow**
4. Fill in the required parameters
5. Monitor the build progress and download artifacts

## Reusable Workflow Components

The user-facing workflows are built using internal reusable components:

- **`_reusable-build-containers.yml`**: Core container building logic with multi-platform support, MPICH caching, and manifest creation
- **`_reusable-validate-containers.yml`**: Container validation including size checks, functionality testing, and platform verification
- **`_reusable-generate-summary.yml`**: Build summary generation with metadata collection and artifact documentation

These internal workflows are automatically combined by the user-facing workflows to provide consistent container builds.

## Features

- **Multi-architecture support**: Native builds for both `linux/amd64` and `linux/arm64` platforms
- **Automatic platform detection**: Multi-architecture manifests allow `docker pull` to select the correct architecture
- **Build validation**: Automated container pulling and size verification
- **Dependency caching**: Cache dependencies like MPICH for faster builds
- **Consistent tagging**: Git-based tagging for reproducible builds
- **Build metadata**: Comprehensive labels with build information, source URLs, and commit SHAs
- **Standardized workflows**: Clean logging, error handling, and consistent patterns

## Development Environment Setup

### Using SST Containers with VS Code DevContainers

The SST development containers are designed to work with VS Code's Dev Containers extension.
See [DEVCONTAINER_SETUP.md](DEVCONTAINER_SETUP.md) for comprehensive instructions on creating your own devcontainer configuration.

Key benefits:
- **Git identity preservation** - Your commits maintain proper authorship
- **SSH key access** - Full GitHub/GitLab authentication inside the container
- **Source code mounting** - Edit code on your host, build in the container
- **GitHub Copilot compatibility** - AI assistance works inside containers

## Creating Experiments

### Experiment Structure
Add a directory to this repository with your experiment files:
```
my-experiment/
├── run_simulation.sh         # Your experiment script
├── README.md                 # Documentation
├── Containerfile            # Optional: custom Containerfile with all dependencies
└── additional_files/        # Any other required files
```

### Workflow Behavior
- If `Containerfile` exists: Uses custom container build
- If no `Containerfile`: Copies experiment files into specified base image
- Base image automatically resolves to current repository's GHCR when registry not specified

### Examples
See existing experiments: `hello-world-mpi/`, `phold-example/`, `tcl-test-experiment/`

## Container Registry

All containers are published to GitHub Container Registry (GHCR):
- **Release containers**: `ghcr.io/{owner}/ar-sst-core:{version}`, `ghcr.io/{owner}/ar-sst-full:{version}`
- **Development containers**: `ghcr.io/{owner}/sst-dev:{tag}`
- **Custom containers**: `ghcr.io/{owner}/{custom-name}:{tag}`
- **Experiment containers**: `ghcr.io/{owner}/{experiment-name}:{tag}`
- **Nightly containers**: `ghcr.io/{owner}/ar-sst-core:master-{sha}`, `ghcr.io/{owner}/ar-sst-core:master-latest`

All containers include metadata accessible via `docker inspect`.
