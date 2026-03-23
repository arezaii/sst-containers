#!/bin/bash
# GitHub Actions integration functions
# Provides GitHub Actions specific output formatting and integration

set -euo pipefail

# path resolution for library scripts (only set if not already defined)
if [[ -z "${SCRIPT_LIB_DIR:-}" ]]; then
    readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Detect if running in GitHub Actions
is_github_actions() {
    [[ "${GITHUB_ACTIONS:-}" == "true" ]]
}

# Set GitHub Actions output
set_output() {
    local name="$1"
    local value="$2"

    if is_github_actions; then
        echo "${name}=${value}" >> "${GITHUB_OUTPUT:-/dev/null}"
    fi
}

# Create GitHub Actions job summary
create_job_summary() {
    local content="$1"

    if is_github_actions && [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        echo "$content" >> "$GITHUB_STEP_SUMMARY"
    fi
}

# Add step annotation (notice, warning, error)
annotate_step() {
    local type="$1"  # notice, warning, error
    local message="$2"
    local file="${3:-}"
    local line="${4:-}"

    if is_github_actions; then
        local annotation="::${type}::"
        if [[ -n "$file" ]]; then
            annotation="${annotation}file=${file}"
            if [[ -n "$line" ]]; then
                annotation="${annotation},line=${line}"
            fi
            annotation="${annotation}::"
        fi
        echo "${annotation}${message}"
    fi
}

# Group output in GitHub Actions
start_group() {
    local group_name="$1"

    if is_github_actions; then
        echo "::group::${group_name}"
    fi
}

end_group() {
    if is_github_actions; then
        echo "::endgroup::"
    fi
}

# Report build metrics in GitHub Actions format
report_build_metrics() {
    local image_tag="$1"
    local build_time_seconds="$2"
    local image_size_mb="$3"
    local platform="$4"

    # Set outputs for GitHub Actions
    set_output "image-tag" "$image_tag"
    set_output "build-time" "$build_time_seconds"
    set_output "image-size-mb" "$image_size_mb"
    set_output "platform" "$platform"

    # Create job summary
    if is_github_actions; then
        create_job_summary "
## Build Results

| Metric | Value |
|--------|-------|
| Image Tag | \`${image_tag}\` |
| Platform | \`${platform}\` |
| Build Time | ${build_time_seconds}s |
| Image Size | ${image_size_mb}MB |
"
    fi
}

# Report validation results
report_validation_metrics() {
    local image_tag="$1"
    local validation_success="$2"
    local tests_passed="$3"  # JSON array or comma-separated
    local size_check_passed="$4"

    set_output "validation-success" "$validation_success"
    set_output "tests-passed" "$tests_passed"
    set_output "size-check-passed" "$size_check_passed"

    if is_github_actions; then
        local status_icon="[SUCCESS]"
        if [[ "$validation_success" != "true" ]]; then
            status_icon="[FAILED]"
        fi

        create_job_summary "
## Validation Results ${status_icon}

| Check | Status |
|-------|--------|
| Image Tag | \`${image_tag}\` |
| Validation | ${validation_success} |
| Tests Passed | ${tests_passed} |
| Size Check | ${size_check_passed} |
"
    fi
}

# Export environment variables for GitHub Actions
export_github_env() {
    local name="$1"
    local value="$2"

    if is_github_actions && [[ -n "${GITHUB_ENV:-}" ]]; then
        echo "${name}=${value}" >> "$GITHUB_ENV"
    fi
}

# Mask sensitive information in logs
mask_value() {
    local value="$1"

    if is_github_actions; then
        echo "::add-mask::${value}"
    fi
}
