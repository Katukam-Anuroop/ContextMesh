# Context: core

## Purpose
Architectural context and structural map for the `src/contextsync/core` module.

## Key Components

### `__init__.py`

### `aggregator.py`
- **Classes**: `Aggregator`
- **Functions**: `__init__`, `aggregate_full`, `aggregate_scoped`, `generate_agents_md`, `generate_cursorrules`, `generate_for_target`, `write_all_surfaces`, `write_cursor_v2_rules`, `write_surfaces`

### `bundler.py`
- **Classes**: `ProgressiveBundler`
- **Functions**: `__init__`, `_get_mesh_zone_summaries`, `_get_working_zone_code`, `_load_gitignore`, `_should_include_file`, `generate_bundle`

### `code_extractor.py`
- **Classes**: `ClassInfo`, `FileStructure`, `FunctionInfo`
- **Functions**: `_extract_docstring`, `extract_file_structure`, `extract_python_structure`, `to_summary`

### `context_search_engine.py`
- **Classes**: `ContextSearchEngine`, `IndexedSection`, `SearchResult`
- **Functions**: `__init__`, `_extract_keywords`, `_parse_sections`, `get_all_section_types`, `index`

### `cross_doc_validator.py`
- **Classes**: `ConsistencyIssue`, `CrossDocReport`, `CrossDocValidator`
- **Functions**: `__init__`, `_check_bidirectional_links`, `_check_parent_child_drift`, `_check_stale_entities`, `errors`, `validate`, `warnings`

### `dependency_graph.py`
- **Classes**: `PythonDependencyExtractor`
- **Functions**: `__init__`, `_resolve_module_to_path`, `extract_dependencies`

### `diff_analyzer.py`
- **Classes**: `ChangeType`, `DiffAnalyzer`, `FileChange`
- **Functions**: `__init__`, `_classify_change`, `_count_diff_lines`, `_extract_python_changes`, `get_changed_files_staged`, `get_current_hash`
- **Constants**: `CONFIG_PATTERNS`, `DEPENDENCY_PATTERNS`, `TEST_PATTERNS`

### `engine.py`
- **Classes**: `Engine`, `PipelineResult`, `PipelineStepResult`
- **Functions**: `_load_env`

### `git_miner.py`
- **Classes**: `ComplexitySignals`, `EvolutionData`, `EvolutionEntry`, `GitMiner`
- **Functions**: `__init__`, `_classify_significance`, `_clean_commit_message`, `format_complexity_for_llm`, `format_evolution_for_llm`, `format_gotcha_hints_for_llm`, `mine_complexity_signals`, `mine_evolution`, `mine_gotcha_hints`
- **Constants**: `GOTCHA_PATTERNS`, `SIGNIFICANT_PATTERNS`

### `invariant_extractor.py`
- **Classes**: `Invariant`, `InvariantExtractor`
- **Functions**: `__init__`, `_extract_base_class_patterns`, `_extract_decorator_patterns`, `_extract_naming_conventions`, `_extract_test_assertions`, `_extract_type_hint_patterns`, `extract`, `format_invariants_for_llm`

### `linter.py`
- **Classes**: `ContextLinter`, `LintIssue`, `LintReport`
- **Functions**: `__init__`, `_find_rule_files`, `extract_defined_entities`, `run_scan`

### `patcher.py`
- **Classes**: `Patcher`
- **Functions**: `__init__`, `_collect_classes`, `_collect_functions`, `_get_directory_listing`, `_summarize_diffs`, `_update_metadata`, `_walk_dir`

### `qa_pipeline.py`
- **Classes**: `QACheck`, `QAPipeline`, `QAResult`
- **Functions**: `__init__`, `_check_diff_size`, `_check_empty_sections`, `_check_entities`, `_check_evolution_format`, `_check_invariant_validity`, `_check_metadata`, `_check_schema`, `errors`, `warnings`

### `salience.py`
- **Classes**: `SalienceClassifier`, `SalienceResult`
- **Functions**: `__init__`, `filter_significant`, `score`, `score_batch`

### `section_ranker.py`
- **Classes**: `RankedSection`
- **Functions**: `_get_priority`, `parse_sections`, `rank_and_truncate`
- **Constants**: `DEFAULT_PRIORITY`

### `tree_walker.py`
- **Classes**: `ContextNode`, `TreeWalker`
- **Functions**: `__init__`, `_parse_lateral_links`, `_resolve_parents`, `_scan_directory`, `build_tree`, `find_nearest_context`, `get_ancestor_chain`, `get_directories_needing_context`, `get_impact_set`

### `visualizer.py`
- **Classes**: `ContextVisualizer`
- **Functions**: `__init__`, `export_and_open`, `generate_html`
- **Constants**: `HTML_TEMPLATE`

### `watcher.py`
- **Classes**: `ContextSyncEventHandler`, `ContextSyncWatcher`
- **Functions**: `__init__`, `_add_to_queue`, `_flush_queue`, `_should_ignore`, `on_any_event`, `start`, `stop`

## Enhanced Context (Local Mining)

### 🔒 Extracted Invariants
Auto-extracted code invariants:
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
