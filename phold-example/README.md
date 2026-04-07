# PHOLD Benchmark Experiment

This experiment pulls and builds the PHOLD benchmark from the sst-benchmarks repository.

## Directory Structure

```
phold-example/
|-- README.md           # This file
|-- run_simulation.sh   # Script to pull and build PHOLD benchmark
`-- analyze_results.sh  # Post-processing script
```

## Usage

Once the container is built using the "Build Experiment Container" workflow:

```bash
# Pull the experiment container
docker pull ghcr.io/hpc-ai-adv-dev/phold-example:latest

# Run the container
docker run -it ghcr.io/hpc-ai-adv-dev/phold-example:latest

# Inside the container, experiment files are in /experiments/phold-example
cd /experiments/phold-example

# Build and run the PHOLD benchmark
./run_simulation.sh

# This script will:
# 1. Clone the sst-benchmarks repository
# 2. Build the PHOLD benchmark
# 3. Run a simple PHOLD simulation

# Analyze results (optional)
./analyze_results.sh
```

## Building the Container

1. Go to Actions > Build Experiment Container
2. Click "Run workflow"
3. Fill in the parameters:
   - **experiment_name**: `phold-example`
   - **base_image**: e.g., `ar-sst-core:latest` or `ghcr.io/hpc-ai-adv-dev/ar-sst-full:15.1.0`
   - **build_platforms**: e.g., `linux/amd64` or `linux/amd64,linux/arm64`
   - **tag_suffix**: `latest` (or any custom tag)
4. Click "Run workflow"
