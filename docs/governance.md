# Context Triggers (CI Governance)

## Overview
For enterprise teams, maintaining codebase architecture is critical. ContextMesh provides native GitHub CI/CD integration to automatically gate Pull Requests if they induce **Architectural Context Drift**.

## How it Works
When a developer modifies a database schema but forgets to update the relevant `CONTEXT.md` documentation, the ContextMesh CI pipeline intercepts the PR:
1. Using Git integration, it isolates the exact files changed in the PR.
2. It fetches the **Impact Set** (the specific related context nodes).
3. It runs the `CrossDocValidator` to ensure no lateral links are broken and parent/child graphs are still symmetric.

If Drift is detected, it pushes **inline GitHub Action annotations** directly onto the PR diff interface blocking the merge.

## Installation
Drop the automated CI pipeline into your repository with one command:
```bash
contextmesh init-ci
```

This generates `.github/workflows/contextmesh-pr.yml`.

## Manual Execution
If you wish to test governance scripts locally or in custom Jenkins runners:
```bash
contextmesh validate --ci --changed-only
```
