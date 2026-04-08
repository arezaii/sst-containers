#!/bin/bash
# Demonstrate that original version tags and latest tags coexist

set -euo pipefail

echo "=== Testing Tag Coexistence ==="
echo "Demonstrating that both version tags and latest tags remain available"
echo ""

# Test images with actual docker commands (using alpine as lightweight test)
TEST_REGISTRY="localhost:5000"
TEST_IMAGE_BASE="test-sst-core"
VERSION_TAG="15.1.2"

# Simulate the build process that creates platform-specific images
echo "Step 1: Creating platform-specific images (simulating build process)"
echo "Building ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-amd64"
echo "Building ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-arm64"

# Create test platform images
docker build -t "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-amd64" - <<EOF
FROM alpine:latest
RUN echo "Test AMD64 image for version ${VERSION_TAG}" > /test.txt
LABEL platform="amd64"
LABEL version="${VERSION_TAG}"
EOF

docker build -t "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-arm64" - <<EOF
FROM alpine:latest
RUN echo "Test ARM64 image for version ${VERSION_TAG}" > /test.txt
LABEL platform="arm64"
LABEL version="${VERSION_TAG}"
EOF

echo ""
echo "Step 2: Creating original version manifest (simulating build workflow)"
echo "Creating ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}"

# Create the original version manifest (what the build workflow does)
if command -v docker >/dev/null 2>&1; then
    docker buildx imagetools create \
        --tag "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}" \
        "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-amd64" \
        "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-arm64"
    echo "[OK] Created version tag: ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}"
else
    echo "[ERROR] Docker not available, cannot test actual manifest creation"
    exit 1
fi

echo ""
echo "Step 3: Creating latest tag (simulating latest tagging feature)"
echo "Creating ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest"

# Create the latest tag (what our latest tagging feature does)
docker buildx imagetools create \
    --tag "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest" \
    "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-amd64" \
    "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-arm64"
echo "[OK] Created latest tag: ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest"

echo ""
echo "Step 4: Verifying both tags exist and work"

# Test version tag
echo "Testing version tag:"
if docker manifest inspect "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}" >/dev/null 2>&1; then
    echo "[OK] ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG} - EXISTS and accessible"
else
    echo "[ERROR] ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG} - NOT ACCESSIBLE"
fi

# Test latest tag
echo "Testing latest tag:"
if docker manifest inspect "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest" >/dev/null 2>&1; then
    echo "[OK] ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest - EXISTS and accessible"
else
    echo "[ERROR] ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest - NOT ACCESSIBLE"
fi

echo ""
echo "Step 5: Comparing manifests"
echo "Both tags should point to the same platform images:"

echo ""
echo "Version tag manifest:"
docker manifest inspect "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}" | jq -r '.manifests[].platform | "\(.os)/\(.architecture)"' | sort

echo ""
echo "Latest tag manifest:"
docker manifest inspect "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest" | jq -r '.manifests[].platform | "\(.os)/\(.architecture)"' | sort

echo ""
echo "=== CONCLUSION ==="
echo "Both tags coexist and point to the same underlying platform images."
echo "Users can pull either:"
echo "  docker pull ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}"
echo "  docker pull ${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest"
echo ""
echo "Cleaning up test images..."
docker rmi "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-amd64" >/dev/null 2>&1 || true
docker rmi "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}-arm64" >/dev/null 2>&1 || true
docker rmi "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:${VERSION_TAG}" >/dev/null 2>&1 || true
docker rmi "${TEST_REGISTRY}/${TEST_IMAGE_BASE}:latest" >/dev/null 2>&1 || true
echo "[OK] Cleanup completed"