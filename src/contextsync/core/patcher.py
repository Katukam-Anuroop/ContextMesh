"""Patcher — orchestrates LLM-powered context file patching."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from contextsync.config import ContextSyncConfig
from contextsync.core.diff_analyzer import FileChange
from contextsync.core.tree_walker import ContextNode
from contextsync.llm.base import LLMAdapter, PatchRequest, PatchResult


def _get_directory_listing(dir_path: Path, max_depth: int = 2) -> str:
    """Get a formatted directory listing for LLM context."""
    lines = []
    _walk_dir(dir_path, lines, prefix="", depth=0, max_depth=max_depth)
    return "\n".join(lines[:100])  # Cap at 100 lines


def _walk_dir(path: Path, lines: list[str], prefix: str, depth: int, max_depth: int) -> None:
    skip = {
        "__pycache__", ".git", "node_modules", ".venv", "venv",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    }
    if depth > max_depth:
        return

    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        for i, entry in enumerate(entries):
            if entry.name in skip or entry.name.startswith("."):
                continue
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                _walk_dir(entry, lines, prefix + extension, depth + 1, max_depth)
    except PermissionError:
        pass


def _update_metadata(content: str, sync_hash: str) -> str:
    """Update or add metadata comments at the top of a CONTEXT.md."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Remove existing metadata lines
    lines = content.split("\n")
    clean_lines = [
        line for line in lines
        if not line.strip().startswith("<!-- last_synced:") and
           not line.strip().startswith("<!-- sync_hash:")
    ]

    # Find where to insert (after other metadata comments or at top)
    insert_idx = 0
    for i, line in enumerate(clean_lines):
        if line.strip().startswith("<!--"):
            insert_idx = i + 1
        else:
            break

    clean_lines.insert(insert_idx, f"<!-- sync_hash: {sync_hash} -->")
    clean_lines.insert(insert_idx, f"<!-- last_synced: {now} -->")

    return "\n".join(clean_lines)


class Patcher:
    """Generates surgical patches to CONTEXT.md files using an LLM."""

    def __init__(self, llm: LLMAdapter, config: ContextSyncConfig):
        self.llm = llm
        self.config = config

    async def patch(
        self,
        node: ContextNode,
        changes: list[FileChange],
        sync_hash: str,
    ) -> PatchResult:
        """Generate a patch for a context node based on code changes.

        Args:
            node: The context tree node to patch
            changes: File changes that affect this node
            sync_hash: Current git commit hash

        Returns:
            PatchResult with the updated content
        """
        # Build the patch request
        request = PatchRequest(
            current_context=node.content,
            code_diff=self._summarize_diffs(changes),
            changed_files=[c.path for c in changes],
            change_types=list(set(c.change_type.value for c in changes)),
            changed_functions=self._collect_functions(changes),
            changed_classes=self._collect_classes(changes),
            directory_listing=_get_directory_listing(node.dir_path),
            preserved_sections=self.config.preserved_sections,
            parent_context=node.parent.content if node.parent else None,
        )

        # Call LLM
        result = await self.llm.generate_patch(request)

        # Update metadata in the patched content
        result.patched_content = _update_metadata(result.patched_content, sync_hash)

        return result

    def _summarize_diffs(self, changes: list[FileChange]) -> str:
        """Create a concise diff summary for the LLM (avoid sending raw code if send_code=False)."""
        if self.config.llm.send_code:
            # Send actual diffs (truncated)
            parts = []
            for change in changes[:10]:
                diff_preview = change.diff_text[:500] if change.diff_text else "(no diff)"
                parts.append(f"--- {change.path} ({change.change_type.value}) ---\n{diff_preview}\n")
            return "\n".join(parts)
        else:
            # Send only structural summaries (privacy-preserving)
            parts = []
            for change in changes[:20]:
                summary = f"- {change.path}: {change.change_type.value}"
                if change.changed_functions:
                    summary += f" | functions: {', '.join(change.changed_functions[:5])}"
                if change.changed_classes:
                    summary += f" | classes: {', '.join(change.changed_classes[:5])}"
                summary += f" | +{change.added_lines}/-{change.deleted_lines} lines"
                parts.append(summary)
            return "\n".join(parts)

    def _collect_functions(self, changes: list[FileChange]) -> list[str]:
        """Collect all changed function names."""
        funcs = []
        for c in changes:
            funcs.extend(c.changed_functions)
        return list(set(funcs))[:20]

    def _collect_classes(self, changes: list[FileChange]) -> list[str]:
        """Collect all changed class names."""
        classes = []
        for c in changes:
            classes.extend(c.changed_classes)
        return list(set(classes))[:10]
