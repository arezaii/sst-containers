#!/bin/bash
# Example simulation runner script

echo "==================================="
echo "Example SST Simulation"
echo "==================================="
echo ""

# Check SST installation
echo "Checking SST installation..."
sst --version
echo ""

# Run the SST simulation
echo "Running SST simulation with config.py..."
if [ -f "config.py" ]; then
    sst config.py
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo ""
        echo "[SUCCESS] Simulation completed successfully!"
        echo "  Check the output for results"
    else
        echo ""
        echo "[ERROR] Simulation failed with exit code: $exit_code"
        exit $exit_code
    fi
else
    echo "[ERROR] config.py not found"
    exit 1
fi
