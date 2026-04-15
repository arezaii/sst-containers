# Test Guide

This directory contains the Python test suite for the SST container build system.

## Current Test Module

`test_python_orchestration.py` covers:

- direct CLI parsing and help output
- workflow adapter output generation
- build-entrypoint, source, experiment, and release build planning
- tarball downloads and metadata validation
- local SST-core checkout staging
- manifest verification helper behavior

Wrapper-level smoke coverage now lives in `test_python_orchestration.py` alongside the direct CLI and orchestration tests, so the documented test surface stays Python-only.

## Running Tests

Run the main commands from the repository root:

```bash
# Run the full Python test suite through the supported helper
./tests/run-python-tests.sh

# Run the main orchestration and wrapper-smoke suite only
./tests/run-python-tests.sh tests.test_python_orchestration
```

The helper prefers `.venv/bin/python` when that virtual environment exists and otherwise falls back to `python3`. Set `PYTHON_BIN` if you need to force a specific interpreter.

To inspect the current local CLI contract, check the wrapper help output directly:

```bash
./sst_container_factory/bin/build.sh --help
./sst_container_factory/bin/build.sh source --help
./sst_container_factory/bin/build.sh experiment --help
./sst_container_factory/bin/download-sources.sh --help
```