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
# Run the main orchestration and wrapper-smoke suite
.venv/bin/python -m unittest tests.test_python_orchestration

# Or run all Python tests under tests/
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

You can also run the module from the `tests/` directory:

```bash
cd tests
../.venv/bin/python -m unittest test_python_orchestration
```

To inspect the current local CLI contract, check the wrapper help output directly:

```bash
../sst_container_factory/bin/build.sh --help
../sst_container_factory/bin/build.sh source --help
../sst_container_factory/bin/build.sh experiment --help
../sst_container_factory/bin/download-sources.sh --help
```