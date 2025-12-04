# PHOLD Benchmark Experiment

This experiment pulls and builds the PHOLD benchmark from the sst-benchmarks repository.

## Directory Structure

```
example-experiment/
|-- README.md           # This file
|-- run_simulation.sh   # Script to pull and build PHOLD benchmark
`-- analyze_results.sh  # Post-processing script
```

## Usage

Once the container is built using the "Build Experiment Container" workflow:

```bash
# Pull the experiment container
docker pull ghcr.io/ai-hpc-adv-dev/example-experiment:latest

# Run the container
docker run -it ghcr.io/ai-hpc-adv-dev/example-experiment:latest

# Inside the container, experiment files are in /experiments/example-experiment
cd /experiments/example-experiment

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
   - **experiment_name**: `example-experiment`
   - **base_image_type**: Choose `sst-core` or `sst-full`
   - **base_image_tag**: e.g., `15.1.0` or `latest`
   - **base_image_arch**: `amd64` or `arm64`
   - **tag_suffix**: `latest` (or any custom tag)
4. Click "Run workflow"
