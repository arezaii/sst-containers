# AHP Graph Experiment

This experiment uses a custom `Containerfile` to build an SST image with [ahp_graph](https://github.com/alvaradoo/ahp_graph), Graphviz, matplotlib, and a compiled PHOLD benchmark.

## Build the Image

Use the `build-experiment.yml` workflow with these inputs:

- `experiment_name`: `ahp-graph`
- `tag_suffix`: choose the tag you want to publish

This experiment includes its own `Containerfile`, so the workflow ignores `base_image`.

## What the Image Contains

The current `Containerfile` starts from `ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2` and adds:

- Build tools: `autoconf`, `cmake`, `libtool`, `libtool-bin`
- Graphviz and development headers
- [ahp_graph](https://github.com/alvaradoo/ahp_graph)
- `matplotlib`
- The [PHOLD benchmark](https://github.com/hpc-ai-adv-dev/sst-benchmarks), built during image creation

## Run the Image

```bash
docker pull ghcr.io/hpc-ai-adv-dev/ahp-graph:latest
docker run -it ghcr.io/hpc-ai-adv-dev/ahp-graph:latest
```

The image clones `sst-benchmarks` into `/sst-benchmarks` and builds the PHOLD benchmark under `/sst-benchmarks/phold/` during image creation.
