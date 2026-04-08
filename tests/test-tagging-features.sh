#!/bin/bash
# Test script for latest tagging functionality
# Tests both library functions and docker tagging locally

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/lib/init.sh"
source "${SCRIPT_DIR}/../scripts/lib/config.sh"

# Configuration for local testing
LOCAL_REGISTRY="${LOCAL_REGISTRY:-localhost:5000}"
TEST_OWNER="${TEST_OWNER:-$(whoami)}"

# Test data - simulate built_images output from workflows
SAMPLE_BUILT_IMAGES_CORE='[
    "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-amd64",
    "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-arm64"
]'

SAMPLE_BUILT_IMAGES_FULL='[
    "ghcr.io/hpc-ai-adv-dev/sst-full:15.1.2-amd64",
    "ghcr.io/hpc-ai-adv-dev/sst-full:15.1.2-arm64"
]'

SAMPLE_BUILT_IMAGES_MASTER='[
    "ghcr.io/hpc-ai-adv-dev/sst-core:master-abc123-amd64",
    "ghcr.io/hpc-ai-adv-dev/sst-core:master-abc123-arm64"
]'

SAMPLE_BUILT_IMAGES_CUSTOM='[
    "ghcr.io/hpc-ai-adv-dev/sst-custom:main-20241201-amd64",
    "ghcr.io/hpc-ai-adv-dev/sst-custom:main-20241201-arm64"
]'

SAMPLE_BUILT_IMAGES_MIXED='[
    "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-amd64",
    "ghcr.io/hpc-ai-adv-dev/sst-core:15.1.2-arm64",
    "ghcr.io/hpc-ai-adv-dev/sst-full:15.1.2-amd64",
    "ghcr.io/hpc-ai-adv-dev/sst-full:15.1.2-arm64"
]'

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

# Test the generate_latest_tagging_info function
test_library_function() {
    log_test "Testing generate_latest_tagging_info library function..."

    echo ""
    echo "=== Test 1: Core containers only ==="
    local result1
    result1=$(generate_latest_tagging_info "$SAMPLE_BUILT_IMAGES_CORE")
    echo "Input: $SAMPLE_BUILT_IMAGES_CORE"
    echo "Output:"
    echo "$result1" | jq '.'

    # Validate core output has correct count and latest tag format
    local count1
    count1=$(echo "$result1" | jq 'length')
    if [[ "$count1" -eq 1 ]]; then
        log_pass "Core test: Found expected 1 base image group"

        # Validate release builds get plain :latest tag
        local release_latest_tag
        release_latest_tag=$(echo "$result1" | jq -r '.[0].latest_tag // empty')
        if [[ "$release_latest_tag" == "ghcr.io/hpc-ai-adv-dev/sst-core:latest" ]]; then
            log_pass "Release test: Correctly generated plain latest tag"
        else
            log_fail "Release test: Expected plain latest tag, got $release_latest_tag"
            return 1
        fi
    else
        log_fail "Core test: Expected 1 base image, got $count1"
        return 1
    fi

    echo ""
    echo "=== Test 2: Full containers only ==="
    local result2
    result2=$(generate_latest_tagging_info "$SAMPLE_BUILT_IMAGES_FULL")
    echo "Input: $SAMPLE_BUILT_IMAGES_FULL"
    echo "Output:"
    echo "$result2" | jq '.'

    echo ""
    echo "=== Test 3: Master/nightly containers ==="
    local result3
    result3=$(generate_latest_tagging_info "$SAMPLE_BUILT_IMAGES_MASTER")
    echo "Input: $SAMPLE_BUILT_IMAGES_MASTER"
    echo "Output:"
    echo "$result3" | jq '.'

    # Validate master tagging gets master-latest
    local master_latest_tag
    master_latest_tag=$(echo "$result3" | jq -r '.[0].latest_tag // empty')
    if [[ "$master_latest_tag" == "ghcr.io/hpc-ai-adv-dev/sst-core:master-latest" ]]; then
        log_pass "Master test: Correctly generated master-latest tag"
    else
        log_fail "Master test: Expected master-latest tag, got $master_latest_tag"
        return 1
    fi

    echo ""
    echo "=== Test 4: Custom containers ==="
    local result4
    result4=$(generate_latest_tagging_info "$SAMPLE_BUILT_IMAGES_CUSTOM")
    echo "Input: $SAMPLE_BUILT_IMAGES_CUSTOM"
    echo "Output:"
    echo "$result4" | jq '.'

    echo ""
    echo "=== Test 5: Mixed containers (core + full) ==="
    local result5
    result5=$(generate_latest_tagging_info "$SAMPLE_BUILT_IMAGES_MIXED")
    echo "Input: $SAMPLE_BUILT_IMAGES_MIXED"
    echo "Output:"
    echo "$result5" | jq '.'

    # Validate mixed output
    local count5
    count5=$(echo "$result5" | jq 'length')
    if [[ "$count5" -eq 2 ]]; then
        log_pass "Mixed test: Found expected 2 base image groups"
    else
        log_fail "Mixed test: Expected 2 base images, got $count5"
        return 1
    fi

    echo ""
    echo "=== Test 6: Empty input ==="
    local result6
    result6=$(generate_latest_tagging_info "[]")
    echo "Input: []"
    echo "Output: $result6"

    local count6
    count6=$(echo "$result6" | jq 'length')
    if [[ "$count6" -eq 0 ]]; then
        log_pass "Empty test: Correctly returned empty array"
    else
        log_fail "Empty test: Expected empty array, got $result6"
        return 1
    fi

    echo ""
    echo "=== Test 7: Invalid input ==="
    local result7
    result7=$(generate_latest_tagging_info "null")
    echo "Input: null"
    echo "Output: $result7"

    local count7
    count7=$(echo "$result7" | jq 'length')
    if [[ "$count7" -eq 0 ]]; then
        log_pass "Invalid input test passed"
    else
        log_fail "Invalid test: Expected empty array for null input, got $count7 items"
        return 1
    fi

    log_pass "Library function tests completed successfully!"
}

# Create test images locally for docker testing
create_test_images() {
    log_test "Creating local test images..."

    # Check if local registry is running
    if ! curl -s "http://${LOCAL_REGISTRY}/v2/" > /dev/null 2>&1; then
        log_info "Local registry not detected at ${LOCAL_REGISTRY}"
        log_info "To test with docker commands, start a local registry:"
        log_info "  docker run -d -p 5000:5000 --name registry registry:2"
        return 1
    fi

    # Create minimal test images
    local temp_dir
    temp_dir=$(mktemp -d)

    cat > "${temp_dir}/Dockerfile" << 'EOF'
FROM alpine:latest
RUN echo "Test image for tagging" > /test.txt
CMD ["echo", "hello from test image"]
EOF

    # Build and push test images for different architectures (simulated)
    local test_images=(
        "${LOCAL_REGISTRY}/sst-core:15.1.2-amd64"
        "${LOCAL_REGISTRY}/sst-core:15.1.2-arm64"
        "${LOCAL_REGISTRY}/sst-full:15.1.2-amd64"
        "${LOCAL_REGISTRY}/sst-full:15.1.2-arm64"
    )

    for image in "${test_images[@]}"; do
        log_info "Building test image: $image"
        docker build -t "$image" "$temp_dir"
        docker push "$image" || log_fail "Failed to push $image"
    done

    # Clean up
    rm -rf "$temp_dir"
    log_pass "Test images created successfully"
    return 0
}

# Test the actual docker tagging workflow
test_docker_tagging() {
    log_test "Testing docker tagging workflow..."

    # Create test images first
    if ! create_test_images; then
        log_info "Skipping docker tagging tests (no local registry)"
        return 0
    fi

    # Test the workflow logic with local images
    local test_built_images
    test_built_images='[
        "'${LOCAL_REGISTRY}'/sst-core:15.1.2-amd64",
        "'${LOCAL_REGISTRY}'/sst-core:15.1.2-arm64",
        "'${LOCAL_REGISTRY}'/sst-full:15.1.2-amd64",
        "'${LOCAL_REGISTRY}'/sst-full:15.1.2-arm64"
    ]'

    log_info "Testing with local images: $test_built_images"

    # Generate tagging information
    local tagging_info
    tagging_info=$(generate_latest_tagging_info "$test_built_images")

    echo "Generated tagging info:"
    echo "$tagging_info" | jq '.'

    # Execute the tagging (similar to workflow logic)
    echo "$tagging_info" | jq -c '.[]' | while read -r entry; do
        local base_name latest_tag
        base_name=$(echo "$entry" | jq -r '.base_name')
        latest_tag=$(echo "$entry" | jq -r '.latest_tag')

        log_info "Creating latest tag: $latest_tag"
        log_info "Base name: $base_name"

        # Get platform images for this base
        local platform_images=()
        while IFS= read -r img; do
            if [[ -n "$img" ]]; then
                platform_images+=("$img")
                log_info "  Platform image: $img"

                # Verify the source image exists
                if ! docker manifest inspect "$img" > /dev/null 2>&1; then
                    log_fail "Source image not found: $img"
                    return 1
                fi
            fi
        done < <(echo "$entry" | jq -r '.platform_images[]')

        if [[ ${#platform_images[@]} -gt 0 ]]; then
            # Create the latest tag from all platform images
            log_info "Executing: docker buildx imagetools create --tag '$latest_tag' ${platform_images[*]}"

            if docker buildx imagetools create --tag "$latest_tag" "${platform_images[@]}"; then
                log_pass "Created: $latest_tag"

                # Verify the manifest was created
                if docker manifest inspect "$latest_tag" > /dev/null 2>&1; then
                    log_pass "Verified manifest exists: $latest_tag"
                else
                    log_fail "Manifest verification failed: $latest_tag"
                fi
            else
                log_fail "Failed to create: $latest_tag"
                return 1
            fi
        else
            log_fail "No platform images found for $base_name"
            return 1
        fi
    done

    log_pass "Docker tagging tests completed successfully!"
}

# Test edge cases and error conditions
test_edge_cases() {
    log_test "Testing edge cases..."
    local test_failed="false"

    # Test with malformed image names
    local malformed_images='[
        "invalid-image-name:latest",
        "ghcr.io/owner/image-without-arch:1.0.0"
    ]'

    local result
    result=$(generate_latest_tagging_info "$malformed_images")
    local count
    count=$(echo "$result" | jq 'length')

    if [[ "$count" -eq 0 ]]; then
        log_pass "Edge case: Malformed images correctly ignored"
    else
        log_fail "Edge case: Should have ignored malformed images, got $count results"
        test_failed="true"
    fi

    # Test with duplicate platform images for the same base tag.
    local duplicate_images='[
        "ghcr.io/owner/sst-core:15.1.2-amd64",
        "ghcr.io/owner/sst-core:15.1.2-arm64",
        "ghcr.io/owner/sst-core:15.1.2-amd64"
    ]'

    result=$(generate_latest_tagging_info "$duplicate_images")
    count=$(echo "$result" | jq 'length')

    if [[ "$count" -eq 1 ]]; then
        log_pass "Edge case: Duplicate base names correctly grouped"
    else
        log_fail "Edge case: Expected 1 group for duplicates, got $count"
        test_failed="true"
    fi

    if [[ "$test_failed" == "true" ]]; then
        return 1
    fi

    log_pass "Edge case tests completed!"
}

# Cleanup test artifacts
cleanup_test_artifacts() {
    log_test "Cleaning up test artifacts..."

    if curl -s "http://${LOCAL_REGISTRY}/v2/" > /dev/null 2>&1; then
        # Remove test latest tags
        local test_latest_tags=(
            "${LOCAL_REGISTRY}/sst-core:latest"
            "${LOCAL_REGISTRY}/sst-full:latest"
        )

        for tag in "${test_latest_tags[@]}"; do
            if docker manifest inspect "$tag" > /dev/null 2>&1; then
                log_info "Removing test tag: $tag"
                # Note: Cannot easily delete from registry, but we can remove locally
                docker rmi "$tag" 2>/dev/null || true
            fi
        done
    fi

    log_pass "Cleanup completed"
}

# Usage information
show_usage() {
    echo "Usage: $0 [OPTIONS] [TEST_TYPE]"
    echo ""
    echo "Test the latest tagging functionality locally."
    echo ""
    echo "TEST_TYPES:"
    echo "  library     Test library functions only (default)"
    echo "  docker      Test docker tagging (requires local registry)"
    echo "  edge        Test edge cases and error conditions"
    echo "  all         Run all tests"
    echo ""
    echo "OPTIONS:"
    echo "  --registry REGISTRY   Use specific local registry (default: localhost:5000)"
    echo "  --cleanup            Clean up test artifacts after running"
    echo "  --help               Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0 library              # Test library functions"
    echo "  $0 docker               # Test with docker (needs local registry)"
    echo "  $0 all --cleanup        # Run all tests and cleanup"
    echo ""
    echo "To start a local registry for docker tests:"
    echo "  docker run -d -p 5000:5000 --name registry registry:2"
}

# Parse command line arguments
TEST_TYPE="library"
CLEANUP_AFTER="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        library|docker|edge|all)
            TEST_TYPE="$1"
            shift
            ;;
        --registry)
            LOCAL_REGISTRY="$2"
            shift 2
            ;;
        --cleanup)
            CLEANUP_AFTER="true"
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main test execution
main() {
    echo "========================================"
    echo "Testing Latest Tagging Features"
    echo "========================================"
    echo "Test type: $TEST_TYPE"
    echo "Local registry: $LOCAL_REGISTRY"
    echo ""

    case "$TEST_TYPE" in
        library)
            test_library_function
            test_edge_cases
            ;;
        docker)
            test_library_function
            test_docker_tagging
            ;;
        edge)
            test_edge_cases
            ;;
        all)
            test_library_function
            test_edge_cases
            test_docker_tagging
            ;;
        *)
            echo "Invalid test type: $TEST_TYPE"
            show_usage
            exit 1
            ;;
    esac

    if [[ "$CLEANUP_AFTER" == "true" ]]; then
        cleanup_test_artifacts
    fi

    echo ""
    echo "========================================"
    log_pass "All tests completed successfully!"
    echo "========================================"
}

# Run main function
main "$@"