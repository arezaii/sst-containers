# TCL Test Experiment

This experiment uses a custom `Containerfile` to assemble a reusable test image with SST 14.1.0 and 15.0.0.

## Build the Image

Use the `build-experiment.yml` workflow with these inputs:

- `experiment_name`: `tcl-test-experiment`
- `tag_suffix`: choose the tag you want to publish

This experiment includes its own `Containerfile`, so the workflow ignores `base_image`.

## Run the Image

```bash
docker pull ghcr.io/hpc-ai-adv-dev/tcl-test-experiment:latest
docker run -it ghcr.io/hpc-ai-adv-dev/tcl-test-experiment:latest
```

The container defaults to SST 15.0.0 and opens a shell in the configured test build directory.

## Choose an SST Version

```bash
# SST 15.0.0 (default)
docker run -it ghcr.io/hpc-ai-adv-dev/tcl-test-experiment:latest

# SST 14.1.0
docker run -it -e SST_VERSION=14.1.0 ghcr.io/hpc-ai-adv-dev/tcl-test-experiment:latest
```

Supported values for `SST_VERSION` are `14.1.0` and `15.0.0`.

## Run the Test Suite

Inside the container:

```bash
make test
```

Or run the tests directly from the host:

```bash
docker run --rm -e SST_VERSION=15.0.0 ghcr.io/hpc-ai-adv-dev/tcl-test-experiment:latest make test
docker run --rm -e SST_VERSION=14.1.0 ghcr.io/hpc-ai-adv-dev/tcl-test-experiment:latest make test
```



