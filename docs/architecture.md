# Core ContextMesh Architecture

## The Concept
Traditional AI coding tools like Repopack or Cursor attempt to manage context by aggressively scanning your entire codebase every time you ask a question. This results in **"Attention Budget Depletion"**, where the LLM is overwhelmed by irrelevant token noise.

**ContextMesh** operates differently. It is an **Architectural Change Data Capture (CDC)** engine.

## How it Works
1. **The Graph:** Instead of reading pure code files, ContextMesh forces your LLM to maintain a distributed graph of lightweight `CONTEXT.md` files located in each major directory.
2. **The Watcher:** `contextmesh watch` detects when you save a file. Instead of re-scraping the whole repo, it mathematically deduces the "Impact Set" (the specific `CONTEXT.md` files structurally related to your change).
3. **The Patcher:** It surgically updates only the relevant `CONTEXT.md` nodes in 1-2 seconds.

## Bidirectional Edges
ContextMesh understands that folders are not just hierarchical trees (parents and children). Code heavily relies on **horizontal dependencies** (e.g., `frontend/auth` importing `backend/db`). ContextMesh maps these via "Lateral Links" using AST (Abstract Syntax Tree) python parsers natively.
