# Context: llm

## Purpose
Architectural context and structural map for the `src/contextsync/llm` module.

## Key Components

### `__init__.py`

### `base.py`
- **Classes**: `LLMAdapter`, `PatchRequest`, `PatchResult`, `ScaffoldRequest`, `ScaffoldResult`
- **Functions**: `generate_patch`, `generate_scaffold`, `get_model_name`

### `litellm_adapter.py`
- **Classes**: `LiteLLMAdapter`
- **Functions**: `_build_patch_prompt`, `_build_scaffold_prompt`, `_detect_modified_sections`, `_estimate_cost`, `_get_scaffold_system_prompt`, `extract_sections`, `generate_patch`, `generate_scaffold`, `get_model_name`
- **Constants**: `PATCH_SYSTEM_PROMPT`, `SCAFFOLD_SYSTEM_PROMPT_BASIC`, `SCAFFOLD_SYSTEM_PROMPT_ENHANCED`

## Enhanced Context (Local Mining)

### 🔒 Extracted Invariants
Auto-extracted code invariants:
- [type_hint] Public functions and methods should have return type annotations (confidence: 100%)
  Example: def process(self, data: bytes) -> Result: ...

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
