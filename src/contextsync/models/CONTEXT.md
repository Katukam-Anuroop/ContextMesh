# Context: models

## Purpose
Architectural context and structural map for the `src/contextsync/models` module.

## Key Components

### `__init__.py`

### `change_log.py`
- **Classes**: `ChangeLog`, `ChangeLogCreate`, `ChangeLogORM`

### `context_file.py`
- **Classes**: `ContextFile`, `ContextFileCreate`, `ContextFileORM`

### `database.py`
- **Classes**: `Base`
- **Functions**: `_import_models`, `_set_sqlite_pragma`, `get_db_path`, `get_engine`, `get_session`, `init_db`, `make_id`

### `entity.py`
- **Classes**: `Entity`, `EntityCreate`, `EntityORM`

### `relationship.py`
- **Classes**: `Relationship`, `RelationshipCreate`, `RelationshipORM`

## Enhanced Context (Local Mining)

### 🔒 Extracted Invariants
Auto-extracted code invariants:
- [base_class] Classes in this module should inherit from `Base` (confidence: 80%)
  Example: class MyClass(Base): ...
- [base_class] Classes in this module should inherit from `BaseModel` (confidence: 90%)
  Example: class MyClass(BaseModel): ...
- [naming_convention] All Python files use lowercase_with_underscores naming (confidence: 80%)
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
