# SST Container Factory

Build and publish SST (Structural Simulation Toolkit) container images through GitHub Actions or the local wrappers in `./sst_container_factory/bin/`.

## Available Images

- **Release images** for official SST releases
- **Development images** with SST build dependencies but no SST install
- **Source images** from a selected repo/ref or a local `sst-core` checkout
- **Experiment images** built from content under `experiments/`
- **Nightly images** from the `sst-core` `master` branch

Published image names follow these patterns:

| Build type | Image name |
|---|---|
| Release core | `ghcr.io/{owner}/sst-core:{version}` |
| Release full | `ghcr.io/{owner}/sst-full:{version}` |
| Development | `ghcr.io/{owner}/sst-dev:{tag}` |
| Source | `ghcr.io/{owner}/{image_name}:{tag}` |
| Experiment | `ghcr.io/{owner}/{experiment_name}:{tag}` |
| Nightly | `ghcr.io/{owner}/sst-core:master-{sha}` and `ghcr.io/{owner}/sst-core:master-latest` |

All images include build metadata visible through `docker inspect`.

## Quick Start

### Pull a Published Image

Replace `OWNER` with the GitHub repository owner.

```bash
docker pull ghcr.io/OWNER/sst-core:15.1.2
docker run -it ghcr.io/OWNER/sst-core:15.1.2

docker pull ghcr.io/OWNER/sst-dev:latest
docker run -it ghcr.io/OWNER/sst-dev:latest

docker pull ghcr.io/OWNER/sst-core:master-latest
docker run -it ghcr.io/OWNER/sst-core:master-latest
```

### Build Locally

Run local commands from the repository root. The public local entry point is `./sst_container_factory/bin/build.sh`.
Local builds are host-platform only.

```bash
./sst_container_factory/bin/build.sh dev
./sst_container_factory/bin/build.sh core --sst-version 15.1.2
./sst_container_factory/bin/build.sh source --core-path /path/to/sst-core --tag-suffix local-core
./sst_container_factory/bin/build.sh experiment --experiment-name phold-example
```

For more local examples, see [sst_container_factory/README.md](sst_container_factory/README.md).

## GitHub Actions Workflows

Use the **Actions** tab, choose a workflow, then select **Run workflow**.

| Workflow | Purpose | Main inputs | Published image |
|---|---|---|---|
| `build-release.yml` | Build official SST release images | `sst_version`, `container_types`, optional `sst_elements_version`, `tag_as_latest` | `sst-core:{version}`, `sst-full:{version}` |
| `build-dev.yml` | Build the development image | `tag_suffix`, `mpich_version` | `sst-dev:{tag_suffix}` |
| `build-custom.yml` | Build from a repo/ref | `sst_core_ref`, optional `sst_core_repo`, `sst_elements_repo`, `sst_elements_ref`, `image_name`, `image_tag` | `{image_name}:{tag}` |
| `build-experiment.yml` | Package an experiment from `experiments/` | `experiment_name`, optional `base_image`, `tag_suffix` | `{experiment_name}:{tag_suffix}` |
| `build-nightly.yml` | Build from the latest `sst-core` `master` commit | optional `force_rebuild`, `mpich_version` | `sst-core:master-{sha}`, `sst-core:master-latest` |

Common workflow defaults:

- `mpich_version`: `4.0.2`
- `build_platforms`: `linux/amd64,linux/arm64`

Release and source workflows also support `enable_perf_tracking`.

All user-facing workflows, including `build-experiment.yml`, run the shared container validation step after a successful build. For experiment images, that validation is generic image validation such as image inspection, size checks, and container instantiation. It does not run experiment-specific test logic automatically.

## Experiments

Add experiment content under `experiments/<name>/`.

```text
experiments/my-experiment/
├── run_simulation.sh
├── README.md
├── Containerfile
└── ...
```

If an experiment includes a `Containerfile`, the build uses that file directly and ignores `base_image`. Otherwise the repository copies the experiment files into the selected base image. Short base-image names such as `sst-core:latest` resolve to this repository's GHCR namespace.

Current examples:

- [experiments/ahp-graph/README.md](experiments/ahp-graph/README.md)
- `experiments/hello-world-mpi/`
- [experiments/phold-example/README.md](experiments/phold-example/README.md)
- [experiments/tcl-test-experiment/README.md](experiments/tcl-test-experiment/README.md)

## Repository Docs

- [sst_container_factory/README.md](sst_container_factory/README.md): local wrapper and downloader usage
- [DEVCONTAINER_SETUP.md](DEVCONTAINER_SETUP.md): VS Code Dev Container setup
- [tests/README.md](tests/README.md): test inventory and usage
- [CLI_NORMALIZATION.md](CLI_NORMALIZATION.md): maintainer notes for the public local CLI

## Internal Workflow Pieces

The user-facing workflows call these reusable workflows:

- `_reusable-build-containers.yml` for build planning, caching, and manifest publication
- `_reusable-validate-containers.yml` for container validation
- `_reusable-generate-summary.yml` for run summaries and metadata

