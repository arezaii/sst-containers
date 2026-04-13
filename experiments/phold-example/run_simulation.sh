#!/usr/bin/env bash
set -e

echo "PHOLD Benchmark Experiment"
echo "========================="

# Configuration
REPO_URL="https://github.com/hpc-ai-adv-dev/sst-benchmarks.git"
COMMIT_SHA="main"  # Use specific commit SHA for reproducibility
BENCHMARK_DIR="sst-benchmarks"

# Step 1: Clone and build PHOLD benchmark
echo "1. Building PHOLD benchmark from sst-benchmarks repository..."
if [ ! -d "$BENCHMARK_DIR" ]; then
    echo "   Cloning sst-benchmarks repository..."
    git clone "$REPO_URL" "$BENCHMARK_DIR"
fi

cd "$BENCHMARK_DIR"
echo "   Checking out commit: $COMMIT_SHA"
git checkout "$COMMIT_SHA"

echo "   Building PHOLD benchmark..."
cd phold
make

echo "   [SUCCESS] PHOLD benchmark built!"
echo ""

# Step 2: Run PHOLD simulation
echo "2. Running PHOLD simulation..."
echo "   Parameters: 10x10 grid, 2 rings, 100ns, event density 1.0"
sst phold_dist.py -- --width 10 --height 10 --ring-size 2 --time-to-run 100ns --event-density 1.0 --verbose 1

echo ""
echo "[SUCCESS] PHOLD experiment completed!"
echo "Library: $(pwd)/libphold.so"
echo "Configuration: $(pwd)/phold_dist.py"
