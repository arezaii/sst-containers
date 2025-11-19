# SST Multi-Version Testing Container

Container with SST 14.1.0 and 15.0.0 plus test suite for compatibility testing.

## Quick Start

1. **Build**: Use [Actions > Build Experiment Container](../../actions/workflows/build-experiment.yaml) with experiment name `tcl-test-experiment`

2. **Run**:
```bash
docker pull ghcr.io/arezaii/tcl-test-experiment-amd64:latest
docker run -it ghcr.io/arezaii/tcl-test-experiment-amd64:latest
```

## Usage

**Switch SST versions**:
```bash
# SST 15.0.0 (default)
docker run -it ghcr.io/arezaii/tcl-test-experiment-amd64:latest

# SST 14.1.0
docker run -it -e SST_VERSION=14.1.0 ghcr.io/arezaii/tcl-test-experiment-amd64:latest
```

**Run tests** (inside container):
```bash
make test     # Run tests
```

**Compare versions**:
```bash
# Test both versions
docker run --rm -e SST_VERSION=15.0.0 ghcr.io/arezaii/tcl-test-experiment-amd64:latest bash -c "make test"
docker run --rm -e SST_VERSION=14.1.0 ghcr.io/arezaii/tcl-test-experiment-amd64:latest bash -c "make test"
```



