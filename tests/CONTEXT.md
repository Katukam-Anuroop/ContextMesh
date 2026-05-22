# Context: tests

## Purpose
Architectural context and structural map for the `tests` module.

## Key Components

### `test_hooks.py`
- **Classes**: `TestHooks`
- **Functions**: `setUp`, `tearDown`, `test_init_ci_creates_workflow`, `test_init_ci_does_not_overwrite_existing`, `test_install_creates_pre_commit_hook`, `test_install_fails_without_git`, `test_local_scaffold_creates_context_files`

### `test_linter.py`
- **Classes**: `TestLinter`
- **Functions**: `setUp`, `tearDown`, `test_extract_defined_entities`, `test_linter_finds_stale_references`, `test_linter_ignores_keywords`

### `test_rules_compiler.py`
- **Classes**: `TestRulesCompiler`
- **Functions**: `setUp`, `tearDown`, `test_detect_frameworks_empty`, `test_detect_frameworks_fastapi`, `test_detect_frameworks_typescript_react_next`

## Enhanced Context (Local Mining)

### 🔒 Extracted Invariants
Auto-extracted code invariants:
- [base_class] Classes in this module should inherit from `TestCase` (confidence: 90%)
  Example: class MyClass(TestCase): ...
- [naming_convention] All Python files use lowercase_with_underscores naming (confidence: 80%)

## Guided Rules & Tribal Knowledge

> [!NOTE]
> The sections below can be populated manually or automatically updated by your AI coding assistant during active chat sessions.

### Gotchas
- *Add known edge cases, performance constraints, or pitfalls for this module here.*

### Invariants
- *Add architectural invariants or patterns that must always be respected here.*

### Rejected Approaches
- *Add historical approaches that were tried but rejected and why.*
