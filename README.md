# sst-containers

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
docker pull ghcr.io/arezaii/ar-sst-core:15.1.0
docker run -it ghcr.io/arezaii/ar-sst-core:15.1.0

# Or pull the development environment
docker pull ghcr.io/arezaii/sst-dev:latest
docker run -it ghcr.io/arezaii/sst-dev:latest
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

- **Release**: `ghcr.io/arezaii/ar-sst-core:15.1.0` (official SST versions, multi-arch)
- **Development**: `ghcr.io/arezaii/sst-dev:latest` (build environment with dependencies, multi-arch)
- **Custom**: `ghcr.io/arezaii/ar-sst-core:custom-a1b2c3d` (custom SST from git sources, multi-arch)
- **Experiment**: `ghcr.io/arezaii/my-experiment:latest` (your scripts, architecture-specific)

### Architecture-Specific Tags (Advanced)
If you need a specific architecture, you can still pull:
- **AMD64**: `ghcr.io/arezaii/ar-sst-core-amd64:15.1.0`
- **ARM64**: `ghcr.io/arezaii/ar-sst-core-arm64:15.1.0`

## Automated Building & Packaging

The GitHub Actions workflows provide consistent, automated container builds:

- **Multi-architecture support**: Builds for both `linux/amd64` and `linux/arm64` platforms using native runners
- **Automatic platform detection**: Multi-architecture manifest lists allow `docker pull` to automatically select the right architecture
- **Automatic metadata**: Injects build information, source URLs, and commit SHAs as container labels
- **Consistent tagging**: Uses git references for reproducible builds
- **Dependency caching**: Optimizes build times by caching MPICH and other dependencies

All containers include metadata for traceability and can be inspected with `docker inspect`.

example labels:
```
            "Labels": {
                "com.github.ref_name": "main",
                "com.github.repository": "arezaii/sst-containers",
                "com.github.run_id": "19543004220",
                "com.github.run_number": "12",
                "com.github.sha": "2e1578540f5662b277f0cd3177d08afdbc2be9d8",
                "com.github.workflow": "Build Experiment Container",
                "org.opencontainers.image.ref.name": "ubuntu",
                "org.opencontainers.image.version": "22.04"
            },
```

## Creating Experiments

Add directory to this repo with your experiment files:
```
my-experiment/
├── run_simulation.sh
├── README.md
└── Containerfile (optional - for custom dependencies)
```

The workflow will automatically detect and package your experiment. See existing examples: `hello-world-mpi/`, `phold-example/`, `tcl-test-experiment/`.
