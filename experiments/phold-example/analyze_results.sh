#!/bin/bash
# Example results analysis script

echo "==================================="
echo "Analyzing Simulation Results"
echo "==================================="
echo ""

# Check for output files
if ls *.csv >/dev/null 2>&1 || ls *.txt >/dev/null 2>&1; then
    echo "Found output files:"
    ls -lh *.csv *.txt 2>/dev/null
    echo ""

    # Example: Show summary statistics
    echo "File summary:"
    for file in *.csv *.txt 2>/dev/null; do
        if [ -f "$file" ]; then
            echo "  - $file: $(wc -l < "$file") lines"
        fi
    done
    echo ""
    echo "[SUCCESS] Analysis complete"
else
    echo "No output files found (.csv or .txt)"
    echo "Run the simulation first with: ./run_simulation.sh"
fi

echo ""
echo "Add your custom analysis logic here!"
