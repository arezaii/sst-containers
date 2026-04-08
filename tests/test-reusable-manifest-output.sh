#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "$REPO_ROOT/scripts/lib/config.sh"

pass_count=0

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

assert_json_equals() {
    local actual="$1"
    local expected="$2"

    if [[ "$(echo "$actual" | jq -c '.')" != "$(echo "$expected" | jq -c '.')" ]]; then
        echo "Expected: $(echo "$expected" | jq -c '.')"
        echo "Actual:   $(echo "$actual" | jq -c '.')"
        return 1
    fi

    return 0
}

make_manifest_stub() {
    local stub_path="$1"
    local available_refs="$2"

    cat > "$stub_path" <<EOF
#!/bin/bash
set -euo pipefail

if [[ "\$1" != "manifest" || "\$2" != "inspect" ]]; then
    exit 2
fi

case "\$3" in
${available_refs}
    *)
        exit 1
        ;;
esac
EOF

    chmod +x "$stub_path"
}

test_only_verified_images_are_reported() {
    local temp_dir stub output
    temp_dir="$(mktemp -d)"

    stub="$temp_dir/docker"
    make_manifest_stub "$stub" '    ghcr.io/example/sst-core:15.1.2-amd64|ghcr.io/example/sst-core:15.1.2-arm64)
        exit 0
        ;;'

    output="$(collect_verified_manifest_images \
        "ghcr.io/example/sst-core:15.1.2" \
        "linux/amd64,linux/arm64,linux/ppc64le" \
        "$stub")"

    assert_json_equals "$output" '["ghcr.io/example/sst-core:15.1.2-amd64","ghcr.io/example/sst-core:15.1.2-arm64"]'
    local status=$?
    rm -rf "$temp_dir"
    return $status
}

test_empty_output_when_no_images_exist() {
    local temp_dir stub output
    temp_dir="$(mktemp -d)"

    stub="$temp_dir/docker"
    make_manifest_stub "$stub" ''

    output="$(collect_verified_manifest_images \
        "ghcr.io/example/sst-full:15.1.2" \
        "linux/amd64,linux/arm64" \
        "$stub")"

    assert_json_equals "$output" '[]'
    local status=$?
    rm -rf "$temp_dir"
    return $status
}

cd "$REPO_ROOT"

run_expect_success \
    "manifest output helper reports only verified platform images" \
    test_only_verified_images_are_reported

run_expect_success \
    "manifest output helper returns empty array when no images are inspectable" \
    test_empty_output_when_no_images_exist

echo "[PASS] Manifest output regression tests completed: $pass_count checks"