# Context: cli

## Purpose
Architectural context and structural map for the `src/contextsync/cli` module.

## Key Components

### `__init__.py`

### `app.py`
- **Functions**: `_find_repo_root`, `_load_env`, `_scaffold`, `main`, `mcp_serve`, `version`

### `hooks.py`
- **Functions**: `_find_repo_root`

### `rules.py`
- **Functions**: `_find_repo_root`, `detect_frameworks`
- **Constants**: `TEMPLATES`

## Enhanced Context (Local Mining)

### 🔒 Extracted Invariants
Auto-extracted code invariants:
- [naming_convention] All Python files use lowercase_with_underscores naming (confidence: 80%)

### 📈 Git Evolution & Churn
Total commits in window: 1
Date range: 2026-04-22 to 2026-04-22

Significant changes:
- No architecturally significant changes detected in recent history

## Guided Rules & Tribal Knowledge

> [!NOTE]
> The sections below can be populated manually or automatically updated by your AI coding assistant during active chat sessions.

### Gotchas
- *Add known edge cases, performance constraints, or pitfalls for this module here.*

### Invariants
- *Add architectural invariants or patterns that must always be respected here.*

### Rejected Approaches
- *Add historical approaches that were tried but rejected and why.*
