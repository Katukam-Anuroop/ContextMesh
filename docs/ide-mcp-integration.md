# IDE & MCP Server Integration

## Overview
Great developer tools meet developers where they already are. ContextMesh isn't just a CLI; it is an **Intelligence Layer** designed to interface natively with platforms like VSCode, Cursor, and Claude Code.

## The Model Context Protocol (MCP)
ContextMesh ships with a built-in MCP Server. This allows any AI client to interact with your codebase's architecture graph natively.

**Exposed MCP Tools:**
- `trigger_scaffold(path)`: Forces the LLM to generate `CONTEXT.md` files for undocumented modules.
- `generate_progressive_bundle(path)`: Allows Cursor to request the 90%-token-reduced architectural payloads directly to inform its internal context.

## The VSCode Extension (`contextmesh-vscode`)
We provide a dedicated VSCode sidebar extension built on React/TypeScript.

**Features:**
- **The Dashboard:** A visual sidebar showing the global Context Health Score and exact paths where Context Drift has occurred.
- **The Watcher:** The extension natively boots `contextmesh watch` upon IDE launch, listening silently for file saves without blocking the developer's terminal.
- **CodeLens Actions:** Inline buttons appear over undocumented folders or broken `CONTEXT.md` links allowing developers to invoke "Auto-Fix via LLM" directly from their editor instance.
