# SST Multi-Version Testing Container

Container with SST 14.1.0 and 15.0.0 plus test suite for compatibility testing.

## Quick Start

1. **Build**: Use Actions > Build Experiment Container with experiment name `tcl-test-experiment`

2. **Run**:
```bash
docker pull ghcr.io/ai-hpc-adv-dev/tcl-test-experiment:latest
docker run -it ghcr.io/ai-hpc-adv-dev/tcl-test-experiment:latest
```

## Usage

**Switch SST versions**:
```bash
# SST 15.0.0 (default)
docker run -it ghcr.io/ai-hpc-adv-dev/tcl-test-experiment:latest

# SST 14.1.0
docker run -it -e SST_VERSION=14.1.0 ghcr.io/ai-hpc-adv-dev/tcl-test-experiment:latest
```

**Run tests** (inside container):
```bash
make test     # Run tests
```

**Compare versions**:
```bash
# Test both versions
docker run --rm -e SST_VERSION=15.0.0 ghcr.io/ai-hpc-adv-dev/tcl-test-experiment:latest bash -c "make test"
docker run --rm -e SST_VERSION=14.1.0 ghcr.io/ai-hpc-adv-dev/tcl-test-experiment:latest bash -c "make test"
```



