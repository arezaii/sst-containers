#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$REPO_ROOT"

pass_count=0

get_host_platform() {
    case "$(uname -m)" in
        x86_64)
            echo "linux/amd64"
            ;;
        aarch64|arm64)
            echo "linux/arm64"
            ;;
        *)
            echo "unsupported"
            return 1
            ;;
    esac
}

get_non_host_platform() {
    case "$(get_host_platform)" in
        linux/amd64)
            echo "linux/arm64"
            ;;
        linux/arm64)
            echo "linux/amd64"
            ;;
        *)
            echo "unsupported"
            return 1
            ;;
    esac
}

run_expect_success() {
    local description="$1"
    shift

    echo "[TEST] $description"

    if "$@"; then
        echo "[PASS] $description"
        pass_count=$((pass_count + 1))
    else
        echo "[FAIL] $description"
        exit 1
    fi
}

run_expect_success_with_output() {
    local description="$1"
    local expected_text="$2"
    shift 2

    echo "[TEST] $description"

    local output
    if ! output=$("$@" 2>&1); then
        echo "[FAIL] $description"
        echo "Expected command to succeed"
        echo "Actual output:"
        echo "$output"
        exit 1
    fi

    if [[ "$output" != *"$expected_text"* ]]; then
        echo "[FAIL] $description"
        echo "Expected output to contain: $expected_text"
        echo "Actual output:"
        echo "$output"
        exit 1
    fi

    echo "[PASS] $description"
    pass_count=$((pass_count + 1))
}

run_expect_success_without_output() {
    local description="$1"
    local unexpected_text="$2"
    shift 2

    echo "[TEST] $description"

    local output
    if ! output=$("$@" 2>&1); then
        echo "[FAIL] $description"
        echo "Expected command to succeed"
        echo "Actual output:"
        echo "$output"
        exit 1
    fi

    if [[ "$output" == *"$unexpected_text"* ]]; then
        echo "[FAIL] $description"
        echo "Did not expect output to contain: $unexpected_text"
        echo "Actual output:"
        echo "$output"
        exit 1
    fi

    echo "[PASS] $description"
    pass_count=$((pass_count + 1))
}

run_expect_failure_with_output() {
    local description="$1"
    local expected_text="$2"
    shift 2

    echo "[TEST] $description"

    set +e
    local output
    output=$("$@" 2>&1)
    local status=$?
    set -e

    if [[ $status -eq 0 ]]; then
        echo "[FAIL] $description"
        echo "Expected command to fail"
        exit 1
    fi

    if [[ "$output" != *"$expected_text"* ]]; then
        echo "[FAIL] $description"
        echo "Expected output to contain: $expected_text"
        echo "Actual output:"
        echo "$output"
        exit 1
    fi

    echo "[PASS] $description"
    pass_count=$((pass_count + 1))
}

run_expect_success_with_output \
    "experiment-build help documents canonical validation mode" \
    "--validation MODE" \
    ./scripts/build/experiment-build.sh --help

run_expect_success_without_output \
    "experiment-build help omits removed prefix option" \
    "--prefix" \
    ./scripts/build/experiment-build.sh --help

run_expect_success_with_output \
    "custom-build help documents canonical engine option" \
    "--engine ENGINE" \
    ./scripts/build/custom-build.sh --help

run_expect_success_with_output \
    "custom-build help documents local checkout option" \
    "--core-path PATH" \
    ./scripts/build/custom-build.sh --help

run_expect_success_with_output \
    "local-build help groups custom build options" \
    "Custom build options:" \
    ./scripts/build/local-build.sh --help

run_expect_success_without_output \
    "local-build help omits legacy docker alias" \
    "--docker" \
    ./scripts/build/local-build.sh --help

run_expect_success_without_output \
    "local-build help omits legacy validation alias" \
    "--validate " \
    ./scripts/build/local-build.sh --help

run_expect_success_without_output \
    "local-build help omits test-only tagging flag" \
    "--test-tagging" \
    ./scripts/build/local-build.sh --help

run_expect_success_without_output \
    "custom-build help omits legacy core ref alias" \
    "--sst-core-ref" \
    ./scripts/build/custom-build.sh --help

run_expect_success_with_output \
    "test-local-build help describes smoke defaults" \
    "validation defaults to metadata" \
    ./tests/test-local-build.sh --help

run_expect_failure_with_output \
    "local-build rejects unsupported platforms option" \
    "Unsupported option for local-build: --platforms" \
    ./scripts/build/local-build.sh --platforms linux/amd64 core

run_expect_failure_with_output \
    "local-build rejects core-path for non-custom builds" \
    "--core-path is only supported with CONTAINER_TYPE=custom" \
    ./scripts/build/local-build.sh --core-path /tmp/sst-core dev

run_expect_failure_with_output \
    "local-build rejects validate-only with validation none" \
    "--validate-only requires a validation mode other than none" \
    ./scripts/build/local-build.sh --validate-only --validation none core

run_expect_failure_with_output \
    "local-build rejects non-host platform" \
    "Cross-platform builds are not supported by this script" \
    ./scripts/build/local-build.sh --platform "$(get_non_host_platform)" core

run_expect_failure_with_output \
    "experiment-build rejects removed prefix option" \
    "Unknown option: --prefix" \
    ./scripts/build/experiment-build.sh --prefix ignored phold-example

run_expect_failure_with_output \
    "custom-build rejects legacy core ref alias" \
    "Unknown option: --sst-core-ref" \
    ./scripts/build/custom-build.sh --sst-core-ref main

run_expect_failure_with_output \
    "custom-build rejects mixing core-path with core-ref" \
    "--core-ref cannot be combined with --core-path" \
    ./scripts/build/custom-build.sh --core-path /tmp/sst-core --core-ref main

run_expect_failure_with_output \
    "custom-build rejects missing local checkout path" \
    "Local SST-core checkout (--core-path) not found" \
    ./scripts/build/custom-build.sh --core-path /tmp/does-not-exist

run_expect_failure_with_output \
    "local-build rejects legacy docker alias" \
    "Unknown option: --docker" \
    ./scripts/build/local-build.sh --docker core

run_expect_failure_with_output \
    "local-build rejects test-only tagging flag" \
    "Unknown option: --test-tagging" \
    ./scripts/build/local-build.sh --test-tagging core

run_expect_failure_with_output \
    "experiment-build rejects legacy validation mode name" \
    "Invalid validation mode: no-exec" \
    ./scripts/build/experiment-build.sh --validation no-exec phold-example

run_expect_failure_with_output \
    "experiment-build rejects non-host platform" \
    "Cross-platform builds are not supported by this script" \
    ./scripts/build/experiment-build.sh --platforms "$(get_non_host_platform)" phold-example

run_expect_failure_with_output \
    "experiment-build rejects multi-platform requests" \
    "Multi-platform builds are not supported by this script" \
    ./scripts/build/experiment-build.sh --platforms linux/amd64,linux/arm64 phold-example

# Positional-argument-only paths (no named options → PARSED_CANONICAL_OPTIONS is empty).
# These cover a regression where an empty array expansion produced a spurious
# "Unsupported option for <profile>: " error before any real validation ran.

run_expect_failure_with_output \
    "local-build requires container type argument" \
    "Container type is required" \
    ./scripts/build/local-build.sh

run_expect_failure_with_output \
    "local-build rejects unrecognized container type with no options" \
    "Container type is required" \
    ./scripts/build/local-build.sh not-a-type

run_expect_failure_with_output \
    "experiment-build requires experiment name argument" \
    "Experiment name is required" \
    ./scripts/build/experiment-build.sh

run_expect_failure_with_output \
    "experiment-build rejects nonexistent experiment directory" \
    "Experiment directory 'nonexistent-experiment' not found" \
    ./scripts/build/experiment-build.sh nonexistent-experiment

run_expect_failure_with_output \
    "custom-build requires core ref argument" \
    "SST-core reference (--core-ref) is required" \
    ./scripts/build/custom-build.sh

run_expect_failure_with_output \
    "custom-build rejects non-host platform" \
    "Cross-platform builds are not supported by this script" \
    ./scripts/build/custom-build.sh --core-ref main --platform "$(get_non_host_platform)"

echo "[PASS] CLI smoke tests completed: $pass_count checks"