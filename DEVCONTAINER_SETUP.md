# SST DevContainer Setup Guide

This guide shows you how to create a devcontainer.json file to use SST container images for development.
DevContainers let you develop inside containers while preserving your host system's git identity, SSH keys, and file access.

## Quick Start

Create `.devcontainer/devcontainer.json` in your SST project root:

```json
{
  "name": "SST Development",
  "image": "ghcr.io/ai-hpc-adv-dev/sst-dev:latest",

  "mounts": [
    "source=${localEnv:HOME}/.gitconfig,target=/root/.gitconfig,type=bind,consistency=cached",
    "source=${localEnv:HOME}/.ssh,target=/root/.ssh,type=bind,consistency=cached"
  ],

  "containerEnv": {
    "no_proxy": "*"
  }
}
```

## Core Principles

### 1. Source Code Stays on Host
**Critical**: Your source code should be bind-mounted into the container, **not copied into the container image**. This ensures:
- You can edit files with your host editors (VS Code, vim, etc.)
- Files persist when containers are destroyed
- Build artifacts can be easily accessed from the host
- Performance is maintained (no file copying overhead)

### 2. Bind Mount What You Need
The container provides the build environment and binds the current directory, but you need to explicitly bind-mount:
- **Git configuration** - Preserves commit authorship
- **SSH keys** - Enables GitHub/GitLab authentication
- **Other directories** - Other related repos/directories you need (e.g., sst-elements, sst-benchmarks)

## Available SST Container Images

### Development Images (Recommended)
- `ghcr.io/ai-hpc-adv-dev/sst-dev:latest` - Complete build environment with MPICH and all dependencies

### Runtime Images
- `ghcr.io/ai-hpc-adv-dev/sst-core:15.1.0` - SST-core only (smaller)
- `ghcr.io/ai-hpc-adv-dev/sst-full:15.1.0` - SST-core + SST-elements (larger)

**For development, use `sst-dev:latest`** - it has all build tools and dependencies without pre-built SST (so you can build your own version).

## Complete Example Configurations

### SST-Core Development
```json
{
  "name": "SST-Core Dev",
  "image": "ghcr.io/ai-hpc-adv-dev/sst-dev:latest",

  "mounts": [
    // Preserve git identity
    "source=${localEnv:HOME}/.gitconfig,target=/root/.gitconfig,type=bind,consistency=cached",

    // SSH keys for GitHub access
    "source=${localEnv:HOME}/.ssh,target=/root/.ssh,type=bind,consistency=cached",

    // Mount benchmarks from sibling directory (optional)
    "source=${localWorkspaceFolder}/../sst-benchmarks,target=/workspaces/sst-benchmarks,type=bind,consistency=cached"
  ],

  "containerEnv": {
    // Add your SST installation to PATH
    "PATH": "/workspaces/sst-core/sst-install/bin:/usr/local/bin:/usr/bin:/bin",

    // Required for GitHub Copilot
    "no_proxy": "*"
  },

  // Run setup commands when container starts
  "postCreateCommand": "echo 'SST development environment ready!'",

  // Don't keep container running when VS Code closes
  "shutdownAction": "stopContainer"
}
```


### Using Runtime Images for Testing
If you want to test against a specific SST version without building:

```json
{
  "name": "SST 15.1.0 Testing",
  "image": "ghcr.io/ai-hpc-adv-dev/sst-full:15.1.0",

  "mounts": [
    "source=${localEnv:HOME}/.gitconfig,target=/root/.gitconfig,type=bind,consistency=cached",
    "source=${localEnv:HOME}/.ssh,target=/root/.ssh,type=bind,consistency=cached",

    // Mount your test scripts/benchmarks
    "source=${localWorkspaceFolder},target=/workspaces/tests,type=bind,consistency=cached"
  ],

  "containerEnv": {
    // Needed for GitHub Copilot
    "no_proxy": "*"
  }
}
```
