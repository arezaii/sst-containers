#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "$REPO_ROOT/scripts/lib/init.sh"

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

test_stage_git_checkout_excludes_ignored_artifacts() {
    local temp_dir source_dir stage_dir

    temp_dir="$(mktemp -d)"
    source_dir="$temp_dir/sst-core"
    stage_dir="$temp_dir/stage"

    mkdir -p "$source_dir/src/sst/core" "$source_dir/build" "$source_dir/.venv"
    cat > "$source_dir/.gitignore" <<'EOF'
build/
.venv/
*.tmp
EOF
    echo "#!/bin/sh" > "$source_dir/autogen.sh"
    echo "AC_INIT([sst-core],[test])" > "$source_dir/configure.ac"
    echo "tracked" > "$source_dir/src/sst/core/simulation.h"

    git -C "$temp_dir" init -q "$source_dir"
    git -C "$source_dir" config user.email "test@example.com"
    git -C "$source_dir" config user.name "Test User"
    git -C "$source_dir" add autogen.sh configure.ac .gitignore src/sst/core/simulation.h
    git -C "$source_dir" commit -qm "init"

    echo "modified" >> "$source_dir/src/sst/core/simulation.h"
    echo "local" > "$source_dir/local-change.txt"
    echo "ignored" > "$source_dir/build/output.o"
    echo "ignored" > "$source_dir/generated.tmp"
    echo "ignored" > "$source_dir/.venv/marker"

    stage_local_sst_core_checkout "$source_dir" "$stage_dir" >/dev/null

    [[ -f "$stage_dir/autogen.sh" ]]
    [[ -f "$stage_dir/configure.ac" ]]
    [[ -f "$stage_dir/src/sst/core/simulation.h" ]]
    grep -q "modified" "$stage_dir/src/sst/core/simulation.h"
    [[ -f "$stage_dir/local-change.txt" ]]
    [[ ! -e "$stage_dir/.git" ]]
    [[ ! -e "$stage_dir/build/output.o" ]]
    [[ ! -e "$stage_dir/generated.tmp" ]]
    [[ ! -e "$stage_dir/.venv/marker" ]]

    rm -rf "$temp_dir"
}

test_stage_local_checkout_excludes_git_metadata() {
    local temp_dir source_dir stage_dir

    temp_dir="$(mktemp -d)"
    source_dir="$temp_dir/sst-core"
    stage_dir="$temp_dir/stage"

    mkdir -p "$source_dir/.git" "$source_dir/src/sst/core"
    touch "$source_dir/autogen.sh" "$source_dir/configure.ac" "$source_dir/src/sst/core/simulation.h"
    echo "ref: refs/heads/main" > "$source_dir/.git/HEAD"

    stage_local_sst_core_checkout "$source_dir" "$stage_dir" >/dev/null

    [[ -f "$stage_dir/autogen.sh" ]]
    [[ -f "$stage_dir/configure.ac" ]]
    [[ -f "$stage_dir/src/sst/core/simulation.h" ]]
    [[ ! -e "$stage_dir/.git" ]]

    rm -rf "$temp_dir"
}

test_reset_stage_dir_restores_placeholder() {
    local temp_dir stage_dir

    temp_dir="$(mktemp -d)"
    stage_dir="$temp_dir/stage"

    mkdir -p "$stage_dir/subdir"
    touch "$stage_dir/subdir/file.txt"

    reset_local_source_stage_dir "$stage_dir"

    [[ -f "$stage_dir/.gitkeep" ]]
    [[ ! -e "$stage_dir/subdir/file.txt" ]]

    rm -rf "$temp_dir"
}

cd "$REPO_ROOT"

run_expect_success \
    "staging a git checkout excludes ignored artifacts and keeps local changes" \
    test_stage_git_checkout_excludes_ignored_artifacts

run_expect_success \
    "staging a local checkout copies source files and excludes .git metadata" \
    test_stage_local_checkout_excludes_git_metadata

run_expect_success \
    "resetting a stage directory restores the placeholder layout" \
    test_reset_stage_dir_restores_placeholder

echo "[PASS] Local source support tests completed: $pass_count checks"