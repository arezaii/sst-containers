#!/bin/bash
set -e

# Default to SST 15.0.0 if no version specified
SST_VERSION=${SST_VERSION:-15.0.0}

# Validate version and set paths
case "$SST_VERSION" in
    14.1.0)
        export PATH="/opt/SST/14.1.0/bin:$PATH"
        export LD_LIBRARY_PATH="/opt/SST/14.1.0/lib:/opt/SST/14.1.0/elements/lib:$LD_LIBRARY_PATH"
        echo "Using built-in SST version 14.1.0"
        ;;
    15.0.0)
        export PATH="/opt/SST/15.0.0/bin:$PATH"
        export LD_LIBRARY_PATH="/opt/SST/15.0.0/lib:/opt/SST/15.0.0/elements/lib:$LD_LIBRARY_PATH"
        echo "Using built-in SST version 15.0.0"
        ;;
    *)
        echo "Error: Unsupported SST version '$SST_VERSION'"
        echo "Available versions: 14.1.0, 15.0.0"
        exit 1
        ;;
esac

# Configure test suite if not already done for this SST version
TEST_BUILD_DIR="/workspace/sst-ext-tests/build-$SST_VERSION"
if [ ! -d "$TEST_BUILD_DIR" ] || [ ! -f "$TEST_BUILD_DIR/Makefile" ]; then
    echo "Configuring test suite for SST $SST_VERSION..."
    mkdir -p "$TEST_BUILD_DIR"
    cd "$TEST_BUILD_DIR"

    CMAKE_ARGS="-DENABLE_ALL_TESTS=ON"

    echo "Running: cmake $CMAKE_ARGS .."
    cmake $CMAKE_ARGS ..
    echo "Test suite configured for SST $SST_VERSION"
    echo "Build directory: $TEST_BUILD_DIR"
else
    echo "Test suite already configured for SST $SST_VERSION"
fi

# If no command provided, start interactive shell in the test build directory
if [ $# -eq 0 ]; then
    echo ""
    echo "To change SST version, set SST_VERSION environment variable and restart container"
    echo "Available versions: 14.1.0, 15.0.0"
    echo "Current build directory: $TEST_BUILD_DIR"
    echo "To build tests: make"
    echo "To run tests: make test"
    echo ""
    # Change to the appropriate test build directory
    cd "$TEST_BUILD_DIR"
    exec /bin/bash
else
    # Execute the provided command in the test build directory
    cd "$TEST_BUILD_DIR"
    exec "$@"
fi
