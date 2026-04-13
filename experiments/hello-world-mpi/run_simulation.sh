#!/usr/bin/env bash
set -e

echo "Distributed MPI Hello World Experiment"
echo "======================================"
echo

# Configuration - can be overridden by environment variables
MPI_TASKS=${MPI_TASKS:-4}
MPI_NODES=${MPI_NODES:-1}

# Step 1: Build MPI test program if not already built
echo "1. Setting up MPI Hello World test..."
if [ ! -f "mpitest" ]; then
    if [ -f "mpitest.c" ]; then
        echo "   Building MPI test program..."
        # Use host MPI compiler (bound by e4s-cl) for proper library linking
        mpicc -o mpitest mpitest.c
        echo "   [SUCCESS] MPI test program built with host MPI libraries!"
    else
        echo "   Error: mpitest.c source file not found"
        exit 1
    fi
else
    echo "   [SUCCESS] MPI test program already exists!"
fi
echo

# Step 2: Display environment information (including e4s-cl binding info)
echo "2. Environment Information:"
echo "   Hostname: $(hostname)"
echo "   User: $(whoami)"
echo "   Working Directory: $(pwd)"
echo

# Check for SLURM environment
if [ ! -z "$SLURM_JOB_ID" ]; then
    echo "   SLURM Environment Detected:"
    echo "   Job ID: $SLURM_JOB_ID"
    echo "   Nodes: $SLURM_NNODES"
    echo "   Total Tasks: $SLURM_NTASKS"
    echo "   Tasks per Node: $SLURM_NTASKS_PER_NODE"
    echo
fi

# Display MPI environment (should show host MPI when e4s-cl is used)
echo "   MPI Environment (via e4s-cl binding):"
if command -v mpirun >/dev/null 2>&1; then
    echo "   mpirun: $(which mpirun)"
    mpirun --version 2>/dev/null | head -1 | sed 's/^/   /' || echo "   Version info unavailable"
else
    echo "   Warning: mpirun not found - e4s-cl MPI binding may not be active"
fi

if command -v srun >/dev/null 2>&1; then
    echo "   srun: $(which srun)"
fi

# Show key environment variables that indicate e4s-cl is working
echo "   Host MPI Library Binding:"
if [ ! -z "$LD_LIBRARY_PATH" ]; then
    echo "   LD_LIBRARY_PATH set: $(echo $LD_LIBRARY_PATH | cut -c1-80)..."
else
    echo "   Warning: LD_LIBRARY_PATH not set"
fi

if [ ! -z "$PATH" ]; then
    MPI_PATHS=$(echo $PATH | tr ':' '\n' | grep -i mpi | head -3 || echo "")
    if [ ! -z "$MPI_PATHS" ]; then
        echo "   MPI paths in PATH:"
        echo "$MPI_PATHS" | sed 's/^/     /'
    fi
fi
echo

# Step 3: Run MPI Hello World
echo "3. Running MPI Hello World..."
echo "   Parameters: ${MPI_TASKS} tasks across ${MPI_NODES} node(s)"
echo "   NOTE: This assumes e4s-cl has bound host MPI libraries into the container"
echo

# The container should be launched with e4s-cl, so we use the bound MPI directly
# Example: e4s-cl launch --image container.sif srun ./run_simulation.sh

# For distributed execution, we rely on the launcher outside the container
# Inside the container, we just run our program - the MPI context comes from the launcher
if [ ! -z "$SLURM_JOB_ID" ]; then
    echo "   Execution method: Direct execution within SLURM context"
    echo "   (srun should have been used to launch this container with proper MPI setup)"
    ./mpitest
elif [ ! -z "$OMPI_COMM_WORLD_SIZE" ] || [ ! -z "$PMI_SIZE" ]; then
    echo "   Execution method: Direct execution within MPI context"
    echo "   (Detected existing MPI process context)"
    ./mpitest
else
    echo "   Execution method: Local test (no distributed MPI context detected)"
    echo "   For distributed execution, launch this container with:"
    echo "   e4s-cl launch --image <container> srun -N $MPI_NODES --ntasks=$MPI_TASKS ./run_simulation.sh"
    echo
    echo "   Running single-process test:"
    ./mpitest
fi

echo
echo "[SUCCESS] Distributed MPI Hello World experiment completed!"
echo
echo "IMPORTANT: For true distributed MPI execution, this container must be launched via:"
echo "  e4s-cl launch --image <container-name> srun -N <nodes> --ntasks=<tasks> ./run_simulation.sh"
echo
echo "Files:"
echo "  Executable: $(pwd)/mpitest"
echo "  Source: $(pwd)/mpitest.c"
