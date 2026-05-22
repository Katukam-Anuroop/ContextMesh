# Context: contextsync

## Purpose
Architectural context and structural map for the `src/contextsync` module.

## Key Components

### `__init__.py`

### `config.py`
- **Classes**: `AggregatorTarget`, `ApprovalMode`, `ChangeType`, `ConsumptionAggregatorConfig`, `ConsumptionConfig`, `ContextSyncConfig`, `EnhancedContextConfig`, `LLMConfig`, `MCPConfig`, `MonorepoConfig`, `QAConfig`, `RelationshipDetectionConfig`, `SalienceConfig`, `SecurityConfig`, `SecurityMode`, `SurfaceConfig`, `TreeConfig`
- **Functions**: `__init__`, `_coerce_targets`, `find_config`, `generate_default_config`, `load_config`, `save_config`
- **Constants**: `CONFIG_FILENAME`

### `mcp_server.py`
- **Functions**: `_get_search_engine`, `_get_walker`, `_load_env`, `_resolve_repo_root`, `_run`, `_run`, `check_context_health`, `context_conventions`, `context_invariants`, `context_search`, `generate_progressive_bundle`, `get_hierarchical_context`, `propose_context_patch`, `resource_status`, `run_mcp_server`, `trigger_scaffold`

## Enhanced Context (Local Mining)

### 🔒 Extracted Invariants
Auto-extracted code invariants:
- [base_class] Classes in this module should inherit from `str` (confidence: 90%)
  Example: class MyClass(str): ...
- [base_class] Classes in this module should inherit from `Enum` (confidence: 90%)
  Example: class MyClass(Enum): ...
- [base_class] Classes in this module should inherit from `BaseModel` (confidence: 90%)
  Example: class MyClass(BaseModel): ...
- [type_hint] Public functions and methods should have return type annotations (confidence: 93%)
  Example: def process(self, data: bytes) -> Result: ...

### 📈 Git Evolution & Churn
Total commits in window: 2
Date range: 2026-04-22 to 2026-04-22

Significant changes:
- 2026-04 [refactor]: Rename mcp server instance to ContextMesh (a7a1c97)

## Guided Rules & Tribal Knowledge

> [!NOTE]
> The sections below can be populated manually or automatically updated by your AI coding assistant during active chat sessions.

### Gotchas
- *Add known edge cases, performance constraints, or pitfalls for this module here.*

### Invariants
- *Add architectural invariants or patterns that must always be respected here.*

### Rejected Approaches
- *Add historical approaches that were tried but rejected and why.*
