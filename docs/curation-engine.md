# The Curation Engine (Progressive Bundler)

## Overview
When you need to feed your entire repository to an LLM like Claude 3.5 Sonnet or Gemini 1.5 Pro, you usually use a scraper that generates hundreds of thousands of tokens.

The **Progressive Bundler** (`contextmesh bundle [target]`) gives you 100% architectural awareness of your entire repository while dropping token usage by up to 90%.

## Progressive Context
The Bundler is topology-aware:
1. **Active Zone (Deep Inspection):** For the specific directory you are actively coding in (`[target]`), ContextMesh injects the **100% raw source code** (e.g., every `.py` or `.ts` file).
2. **Mesh Zone (Shallow Inspection):** For every other directory in the entire repository, ContextMesh strips out the raw code strings and ONLY injects the lightweight `CONTEXT.md` semantic summary.

## Usage
Generate a bundle directly into your clipboard to paste into ChatGPT or Claude web:
```bash
contextmesh bundle src/api | pbcopy
```

Output XML payload to a file for prompt automation:
```bash
contextmesh bundle src/api --output payload.xml
```

## IDE Native
This capability is natively integrated into the [Model Context Protocol (MCP)](../src/contextsync/mcp_server.py) engine. AI Editors like Cursor or Claude Code can call `generate_progressive_bundle` automatically in the background.
