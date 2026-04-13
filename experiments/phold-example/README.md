# PHOLD Example

This experiment clones, builds, and runs the PHOLD benchmark from the `sst-benchmarks` repository at runtime.

## Files

```text
experiments/phold-example/
├── README.md
├── run_simulation.sh
└── analyze_results.sh
```

## Build the Image

Use the `build-experiment.yml` workflow with these inputs:

- `experiment_name`: `phold-example`
- `base_image`: for example `sst-core:latest` or `ghcr.io/hpc-ai-adv-dev/sst-full:15.1.0`
- `tag_suffix`: choose the tag you want to publish

This experiment does not include a custom `Containerfile`, so the workflow copies these files into the selected base image.

## Run the Experiment

```bash
docker pull ghcr.io/hpc-ai-adv-dev/phold-example:latest
docker run -it ghcr.io/hpc-ai-adv-dev/phold-example:latest

cd /experiments/phold-example
./run_simulation.sh
./analyze_results.sh
```

`run_simulation.sh` clones `sst-benchmarks`, builds the PHOLD benchmark, and runs a simple simulation. `analyze_results.sh` is a starter script for post-processing output files.
