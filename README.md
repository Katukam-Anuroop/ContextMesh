<div align="center">
  <h1>🧠 ContextMesh</h1>
  <p><strong>One source of truth for every AI coding tool.<br>Automated. Verified. Universal.</strong></p>
  <p>
    <a href="#-quickstart"><img src="https://img.shields.io/badge/get_started-2_minutes-brightgreen?style=for-the-badge" alt="Get Started"></a>
    <a href="#-supported-tools"><img src="https://img.shields.io/badge/tools-7+_supported-blue?style=for-the-badge" alt="Supported Tools"></a>
    <a href="https://github.com/Katukam-Anuroop/ContextMesh/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"></a>
  </p>
</div>

---

Your AI coding tools are only as good as the context you feed them. Today, teams maintain `.cursorrules`, `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` **manually**. Within weeks, they go stale. Stale context = bad AI output. Bad AI output = eroded trust.

**ContextMesh** is a Change Data Capture (CDC) engine that automatically generates, maintains, and delivers a hierarchical tree of `CONTEXT.md` files — then pushes that knowledge to **every AI tool you use**, in the exact format each tool expects.

```
Your Codebase                      Every AI Tool Gets Context
─────────────                      ─────────────────────────
                                   ✅  .cursorrules        (Cursor)
   CONTEXT.md  ──── CDC ────────►  ✅  CLAUDE.md           (Claude Code)
   Tree            Engine          ✅  GEMINI.md           (Gemini CLI)
   (auto-maintained)               ✅  AGENTS.md           (OpenAI Codex)
                                   ✅  copilot-instructions (GitHub Copilot)
                                   ✅  .windsurfrules      (Windsurf)
                                   ✅  .clinerules         (Cline)
                                   ✅  .cursor/rules/*.mdc (Cursor v2)
                                   ✅  MCP Server          (Any MCP client)
```

---

## Why ContextMesh?

| Problem | Without ContextMesh | With ContextMesh |
|---|---|---|
| **Context creation** | Manual, hours of writing | `contextmesh scaffold` — 2 minutes |
| **Context maintenance** | Rots silently after every commit | CDC pipeline auto-patches on changes |
| **Tool fragmentation** | Maintain 3-5 files per repo manually | One source → all 7+ formats generated |
| **Context quality** | No verification, can hallucinate | QA pipeline validates against real AST |
| **Team coverage** | Only the person who wrote it benefits | Git-native, shared across the entire team |
| **What AI knows** | Structure only | **Gotchas, invariants, evolution, rejected approaches** |

---

## 🚀 Quickstart

### Install

```bash
pip install contextmesh-cli
```

### Initialize & Generate

```bash
# Initialize config
contextmesh init

# Generate context tree for your entire codebase
contextmesh scaffold

# Generate enhanced context with gotchas, invariants, evolution data
contextmesh scaffold --depth enhanced
```

### Deliver to Every Tool

```bash
# Generate ALL tool-specific context files at once
contextmesh aggregate --targets all

# Or pick your tools interactively
contextmesh aggregate --setup

# Generate Cursor v2 directory-scoped rules
contextmesh aggregate --cursor-v2
```

### Auto-Maintain

```bash
# Watch for changes — context updates automatically
contextmesh watch

# Or run on a specific diff
contextmesh run --from HEAD~1
```

### 🛡️ Set up Git Hooks & CI/CD Gates
Prevent context drift automatically before code ever leaves a developer's machine:

```bash
# Install local Git pre-commit hook to audit rules before every commit
contextmesh hooks install

# Generate GitHub Actions workflow to run validation on PRs automatically
contextmesh init-ci
```

---

## 🛠️ Supported Tools

ContextMesh generates context in the native format for each tool:

| Tool | Output File | Max Lines | Format |
|---|---|---|---|
| **Cursor** | `.cursorrules` | 300 | Markdown |
| **Cursor v2** | `.cursor/rules/*.mdc` | 300/file | MDC (directory-scoped) |
| **Claude Code** | `CLAUDE.md` | 800 | Markdown |
| **Gemini CLI** | `GEMINI.md` | 800 | Markdown |
| **OpenAI Codex** | `AGENTS.md` | 800 | Markdown |
| **GitHub Copilot** | `.github/copilot-instructions.md` | 500 | Markdown |
| **Windsurf** | `.windsurfrules` | 300 | Markdown |
| **Cline** | `.clinerules` | 300 | Markdown |
| **Any MCP Client** | MCP Server (live queries) | ∞ | JSON |

Each file respects the tool's token budget. When space is limited, ContextMesh prioritizes **Gotchas** and **Invariants** (things AI can't discover from code) over **Key Components** (things AI can read directly).

---

## 🛡️ Git-Native Rule Auditing: "The ESLint for AI Rules"

As your codebase evolves daily, your AI instructions (`.cursorrules`, `.cursor/rules/*.mdc`, `CLAUDE.md`, etc.) rot. Classes get renamed, functions get deleted, and variables are refactored. The AI continues to reference dead entities, leading to hallucination and confusion.

ContextMesh includes a fully automated **rule and context auditor** that works just like **ESLint for your AI instructions**:

```bash
# Audit all AI rules and context files for stale AST references and coverage gaps
contextmesh lint

# Fail with exit code 1 if any stale reference or error is found (ideal for local/CI scripts)
contextmesh lint --fail-on-stale
```

### 1. Local Git Hook Protection
Run `contextmesh hooks install` to instantly configure a fast, non-blocking local Git `pre-commit` hook. If a developer makes changes that break rules or introduces stale class references, the commit is blocked with an actionable, inline error pointing to the exact line number of the stale rule:

```
🔍 Auditing AI context and rules before commit...

ContextSync Audit Report
Health Score: 85.0%
Context Coverage Index (CCI): 92.0%
Rules scanned: 12 | Stale links: 2

Location                              Severity    Type                Issue Details
.cursor/rules/stripe_rules.mdc:24     ERROR       stale_reference     Stale reference to StripeClient (class not found)
.cursor/rules/auth_rules.mdc:12       WARN        stale_reference     Stale reference to authenticate_jwt (function not found)

🛑 Failing due to stale references or errors.
```

### 2. CI/CD Automated Gates
Run `contextmesh init-ci` to bootstrap a premium GitHub Actions pipeline under `.github/workflows/contextmesh-pr.yml`. Every pull request will automatically run `contextmesh validate --ci --changed-only` to:
- Detect parent-child directory context drift.
- Verify bidirectional lateral links.
- Render rich inline GitHub check annotations directly on the PR diff.

---

## 🔍 MCP Server — Universal Context Protocol

ContextMesh exposes a Model Context Protocol server that any MCP-compliant client can query:

```json
{
  "mcpServers": {
    "contextmesh": {
      "command": "contextmesh",
      "args": ["mcp-serve"]
    }
  }
}
```

### Available MCP Tools

| Tool | What it does |
|---|---|
| `context_search(query, scope)` | Search for relevant context across the entire codebase |
| `context_invariants(path)` | Get all rules, gotchas, and constraints for a module |
| `context_conventions(path)` | Get coding conventions and rejected approaches |
| `get_hierarchical_context(path)` | Get the full ancestor chain for a file |
| `check_context_health(path)` | Coverage, staleness, and health metrics |
| `trigger_scaffold(path)` | Generate CONTEXT.md for an undocumented module |
| `propose_context_patch(diff, path)` | Update context based on code changes |
| `generate_progressive_bundle(path)` | Full source for active dir, summaries for everything else |

**Example**: An AI agent working on `payments/services/stripe.py` can call:
```
context_invariants("payments/")
→ "All payment handlers must use @transaction.atomic"
→ "Idempotency keys must be set BEFORE Stripe API calls"
→ "process_payment() has a 500ms SLA budget — use async patterns"
```

---

## 🧬 What Makes Context "Enhanced"

Basic context tools give you structure. ContextMesh gives you **tribal knowledge**:

```
contextmesh scaffold --depth enhanced
```

| Section | What it captures | How it's generated |
|---|---|---|
| **## Purpose** | What this module does | LLM + AST analysis |
| **## Key Components** | Classes, functions, files | AST parsing |
| **## Relationships** | Module dependencies (→ lateral links) | Import graph analysis |
| **## Gotchas** | Things that will break if you don't know | LLM inference + git history |
| **## Invariants** | Rules that must always be followed | AST pattern extraction |
| **## Evolution** | How this module changed over time | Git log mining |
| **## Rejected Approaches** | What NOT to do and why | LLM inference from patterns |
| **## Complexity Signals** | Churn, author count, bug-fix ratio | Git statistics |
| **## Conventions** | Coding style and patterns | AST + LLM analysis |

### Why this matters

```
Without enhanced context:
  AI writes: process_payment() with synchronous validation
  Result: p99 latency exceeds SLA → production incident

With enhanced context (## Gotchas):
  AI reads: "process_payment() has a 500ms SLA budget. Use async patterns."
  AI writes: process_payment() with async validation
  Result: ✅ SLA met
```

---

## 🏗️ Architecture

```
Change Detection          CDC Engine                   Output
───────────────          ──────────                   ──────

  Git Hook     ──►  Semantic Diff Analyzer
  GitHub Action ──►  Context Tree Walker    ──►  CONTEXT.md tree
  File Watcher  ──►  Salience Classifier          │
                     Update Planner               ├──►  .cursorrules
                     LLM Patcher                  ├──►  CLAUDE.md
                     QA Pipeline                  ├──►  GEMINI.md
                     Cross-Doc Validator          ├──►  AGENTS.md
                                                  ├──►  .windsurfrules
                                                  ├──►  .clinerules
                                                  ├──►  copilot-instructions.md
                                                  ├──►  .cursor/rules/*.mdc
                                                  └──►  MCP Server
```

**Key design decisions:**
- **Surgical patching, not regeneration** — Only the affected sections of CONTEXT.md are updated
- **AST-first, LLM-second** — Structure from tree-sitter, intelligence from LLM
- **Human sections preserved** — `## Caveats` and `## Decisions` are never overwritten
- **Hierarchical, not flat** — AI loads only the branch it needs (~200 lines vs ~2000)

---

## 📊 Benchmarks

Tested on a Django codebase (148 modules, 600K+ lines):

| Metric | Value |
|---|---|
| **Context files generated** | 148 |
| **Average quality score** | 72.5% |
| **Files at Excellent quality (≥80%)** | 89 (60%) |
| **Gotcha sections generated** | 75 |
| **Invariant sections generated** | 75 |
| **Sections indexed for search** | 1,004 |
| **Tool formats supported** | 9 |
| **Cost per scaffold (Gemini Flash)** | ~$0.02/module |
| **Cost per CDC update** | ~$0.003/commit |

### Token Efficiency

| Approach | Tokens per update | Cost |
|---|---|---|
| Full regeneration (traditional) | ~2,000,000 | $0.15+ |
| ContextMesh CDC patch | ~4,275 | $0.003 |
| **Savings** | **99.8%** | |

---

## ⚙️ Configuration

ContextMesh is configured via `.contextmesh.yaml`:

```yaml
version: 1

tree:
  filename: CONTEXT.md
  max_depth: 4
  auto_scaffold: true

llm:
  provider: gemini           # gemini | openai | anthropic | ollama
  model: gemini-2.5-flash
  temperature: 0.2

enhanced:
  enabled: true
  depth: enhanced            # basic | enhanced | deep
  generate_gotchas: true
  generate_invariants: true
  generate_evolution: true

consumption:
  aggregator:
    targets:
      - path: .cursorrules
        max_lines: 300
      - path: CLAUDE.md
        max_lines: 800
      - path: AGENTS.md
        max_lines: 800

security:
  mode: hybrid               # local | hybrid | cloud
  # hybrid: AST parsed locally, only summaries sent to LLM

preserved_sections:
  - "## Caveats"
  - "## Decisions"
  - "## Gotchas"
  - "## Invariants"
```

---

## 🔄 How It Compares

| | ContextMesh | claude-mem | Obsidian | Manual .cursorrules |
|---|---|---|---|---|
| **What it knows** | Codebase structure + behavioral truth | AI session transcripts | Human-written notes | Whatever you typed once |
| **Source** | AST + git history + LLM | AI conversation logs | Human memory | Human memory |
| **Auto-updates** | ✅ CDC on every commit | ✅ On every session | ❌ Manual | ❌ Manual |
| **Verification** | ✅ QA pipeline vs real AST | ❌ No verification | ❌ No verification | ❌ No verification |
| **Scope** | Team-wide (git) | Per-developer (local) | Per-developer (local) | Per-repo (shared) |
| **Tool support** | All 9 formats + MCP | Claude only | Any (via files) | One tool only |
| **Freshness** | Always current | Session-level | Decays | Decays |

**ContextMesh knows what the codebase *needs*. claude-mem remembers what the AI *did*. They're complementary.**

---

## 📋 CLI Reference

| Command | Description |
|---|---|
| `contextmesh init` | Initialize `.contextmesh.yaml` config |
| `contextmesh scaffold` | Generate CONTEXT.md tree for the codebase |
| `contextmesh scaffold --depth enhanced` | Generate with gotchas, invariants, evolution |
| `contextmesh run --from HEAD~1` | CDC update from recent changes |
| `contextmesh aggregate --targets all` | Generate all 7+ tool-specific context files |
| `contextmesh aggregate --setup` | Interactive tool selection |
| `contextmesh aggregate --cursor-v2` | Generate `.cursor/rules/*.mdc` |
| `contextmesh watch` | Auto-update on file changes (daemon) |
| `contextmesh validate` | Check context tree for drift and errors |
| `contextmesh validate --ci` | CI mode with GitHub Actions annotations |
| `contextmesh lint` | Run context rule auditing (stale AST links and coverage gaps) |
| `contextmesh hooks install` | Configure a Git pre-commit hook to automatically audit rules on every commit |
| `contextmesh init-ci` | Bootstrap ContextMesh GitHub Actions CI configuration |
| `contextmesh link` | Auto-discover lateral dependencies via AST |
| `contextmesh bundle <dir>` | Progressive XML bundle (full source + summaries) |
| `contextmesh mcp-serve` | Start MCP server (STDIO transport) |
| `contextmesh status` | Show context health and coverage |

---

## 🗺️ Roadmap

- [x] CDC engine with surgical patching
- [x] Hierarchical CONTEXT.md tree
- [x] Enhanced context (gotchas, invariants, evolution)
- [x] Universal delivery (7 tool formats + MCP)
- [x] Keyword-based context search
- [x] Cursor v2 directory-scoped rules
- [x] Evaluation harness
- [x] Git pre-commit hook integration (`hooks install`)
- [x] GitHub Action CI/CD integration (`init-ci`)
- [ ] Embedding-based semantic search (Chroma)
- [ ] VS Code extension with auto-inject
- [ ] Enterprise dashboard
- [ ] Cross-repo context graph
- [ ] Feedback loop (accept/reject telemetry)

---

## 📄 License

MIT — free to use, modify, and distribute.

---

<div align="center">
  <p><strong>Stop maintaining 5 context files. Start maintaining zero.</strong></p>
  <pre>pip install contextmesh-cli && contextmesh init && contextmesh scaffold --depth enhanced</pre>
</div>
