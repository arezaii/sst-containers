# Local Build Tooling

This directory contains the Python-backed orchestration layer and the thin shell wrappers used for local builds.

Run the commands below from the repository root.

## Public Entry Points

- `./sst_container_factory/bin/build.sh` for local image builds
- `./sst_container_factory/bin/download-sources.sh` for local tarball downloads

Supported build targets:

- `core` for SST-core release images
- `full` for SST-core plus SST-elements release images
- `dev` for the development image
- `source` for builds from a local `sst-core` checkout or a selected repository/ref
- `experiment` for experiment images

Local builds are host-platform only. The shared `--platform` option rejects anything other than the detected host platform.

Inspect the current contract with:

```bash
./sst_container_factory/bin/build.sh --help
./sst_container_factory/bin/build.sh source --help
./sst_container_factory/bin/build.sh experiment --help
```

## Common Commands

Build the default development image:

```bash
./sst_container_factory/bin/build.sh dev
```

Build a specific SST-core release image:

```bash
./sst_container_factory/bin/build.sh core --sst-version 15.1.2
```

Build a full release image with an explicit SST-elements version:

```bash
./sst_container_factory/bin/build.sh \
  full \
  --sst-version 15.1.2 \
  --elements-version 15.1.0
```

Build a development image, run metadata validation, and remove it afterward:

```bash
./sst_container_factory/bin/build.sh dev --validation metadata --cleanup
```

Validate an existing local image without rebuilding it:

```bash
./sst_container_factory/bin/build.sh core --validate-only --validation full
```

Build from a local `sst-core` checkout instead of a release tarball:

```bash
./sst_container_factory/bin/build.sh \
  source \
  --core-path /path/to/sst-core \
  --tag-suffix local-core
```

Build from a selected SST-core ref in the default repository:

```bash
./sst_container_factory/bin/build.sh source --core-ref main
```

Build a source-driven full image from SST-core and SST-elements repositories:

```bash
./sst_container_factory/bin/build.sh \
  source \
  --core-ref main \
  --elements-repo https://github.com/sstsimulator/sst-elements.git \
  --elements-ref main
```

Build an experiment image:

```bash
./sst_container_factory/bin/build.sh experiment --experiment-name phold-example
```

Build a template-based experiment on top of a specific base image:

```bash
./sst_container_factory/bin/build.sh \
  experiment \
  --experiment-name phold-example \
  --base-image sst-core:latest
```

Build an experiment image and run full container validation:

```bash
./sst_container_factory/bin/build.sh experiment --validation full --experiment-name phold-example
```

Use `./sst_container_factory/bin/download-sources.sh` when you want the local downloader entry point. It calls the same Python implementation used by GitHub Actions.

## Notes

- `source` requires `--core-ref` or `--core-path`
- `experiment` requires `--experiment-name`
- Experiment validation uses the same generic container validation modes as other image types; it does not run experiment-specific benchmark or test scripts automatically
- The shell wrappers call `python -m sst_container_factory.cli` and keep the local interface small

## Supporting Code

The remaining support surface is intentionally small:

- `sst_container_factory/bin/` contains thin local entry-point wrappers that export `PYTHONPATH` and exec the Python CLI
- `sst_container_factory/` contains the stdlib-only Python transition layer for workflow orchestration, migrated build execution paths, and local wrapper entrypoints
- The Python transition layer uses only the standard library so the repo does not pick up extra runtime package prerequisites