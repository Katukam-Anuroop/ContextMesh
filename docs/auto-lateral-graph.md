# The Auto-Lateral Resolver (AST Graph Engine)

## Overview
A `CONTEXT.md` architecture is only as good as its connections. Hierarchical connections (parents/children) are easy because folders map directly to them. 

However, **Lateral Connections** (when `auth` calls `database`) are usually manually typed by developers. ContextMesh eliminates this tedious work through the **Auto-Lateral Resolver**.

## How it Works
When running the `contextmesh link` or `scaffold` commands, the ContextMesh engine parses the **Abstract Syntax Tree (AST)** of your source code:
1. It reads `import db.models` or `from utils import math`.
2. It mathematically maps those python modules into physical local repository paths.
3. It draws a "Logical Edge" in the ContextMesh DAG (Directed Acyclic Graph).

## Usage
To test the dependency generator on a specific target directory:
```bash
contextmesh link src/core
```

This will automatically inject `→ src/db` arrows into your `CONTEXT.md` relationships section the next time you scaffold, guaranteeing that the AI agent stays 100% aware of connected systems globally without human intervention.
