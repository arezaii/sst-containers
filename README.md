# sst-container-factory

Build containerized SST (Structural Simulation Toolkit) environments.

## Four Container Types

1. **Release Containers** - Official SST releases (e.g., 15.1.0)
2. **Development Containers** - Build dependencies for SST development
3. **Custom Git Builds** - Custom SST from any git repo/branch/commit
4. **Experiment Containers** - Your scripts or custom containers, packaged

## Quick Start

### Use Pre-built Containers
```bash
# Automatically pulls the right architecture for your platform
docker pull ghcr.io/ai-hpc-adv-dev/sst-core:15.1.0
docker run -it ghcr.io/ai-hpc-adv-dev/sst-core:15.1.0

# Or pull the development environment
docker pull ghcr.io/ai-hpc-adv-dev/sst-dev:latest
docker run -it ghcr.io/ai-hpc-adv-dev/sst-dev:latest
```

### Build Containers via GitHub Actions
Go to Actions tab and select:
- **"Build SST Release Containers"** - Build official SST versions
- **"Build SST Development Container"** - Create SST development environment
- **"Build Custom SST Containers from Git"** - Build from any SST git source
- **"Build Experiment Container"** - Package your experiment scripts

### Create Experiment
1. Add experiment directory to this repo (see `hello-world-mpi/` example)
2. Go to Actions > "Build Experiment Container"
3. Specify your experiment directory name

## Container Types

- **Release**: `ghcr.io/ai-hpc-adv-dev/sst-core:15.1.0` (official SST versions, multi-arch)
- **Development**: `ghcr.io/ai-hpc-adv-dev/sst-dev:latest` (build environment with dependencies, multi-arch)
- **Custom**: `ghcr.io/ai-hpc-adv-dev/sst-core:custom-a1b2c3d` (custom SST from git sources, multi-arch)
- **Experiment**: `ghcr.io/ai-hpc-adv-dev/my-experiment:latest` (your scripts, architecture-specific)

## Automated Building & Packaging

The GitHub Actions workflows provide consistent, automated container builds:

- **Multi-architecture support**: Builds for both `linux/amd64` and `linux/arm64` platforms using native runners
- **Automatic platform detection**: Multi-architecture manifest lists allow `docker pull` to automatically select the right architecture
- **Automatic metadata**: Injects build information, source URLs, and commit SHAs as container labels
- **Consistent tagging**: Uses git references for reproducible builds
- **Dependency caching**: Optimizes build times by caching MPICH and other dependencies

All containers include metadata for traceability and can be inspected with `docker inspect`.

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

Add a directory to this repo with your experiment files:
```
my-experiment/
|-- run_simulation.sh
|-- README.md
`-- Containerfile (optional - for custom dependencies)
```

The workflow will automatically detect and package your experiment.
See existing examples: `hello-world-mpi/`, `phold-example/`, `tcl-test-experiment/`.
