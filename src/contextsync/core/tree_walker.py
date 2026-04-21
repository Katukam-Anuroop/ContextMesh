"""TreeWalker — Navigates the context file tree and resolves impact sets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from contextsync.config import ContextSyncConfig


@dataclass
class ContextNode:
    """A node in the context tree representing a CONTEXT.md file."""
    path: Path  # Absolute path to the CONTEXT.md
    dir_path: Path  # Directory containing this CONTEXT.md
    depth: int
    parent: Optional[ContextNode] = None
    children: list[ContextNode] = field(default_factory=list)
    lateral_links: list[str] = field(default_factory=list)  # Relative paths to linked contexts
    content: str = ""
    exists: bool = True


class TreeWalker:
    """Walks the filesystem to build and navigate the context tree."""

    def __init__(self, repo_root: Path, config: ContextSyncConfig):
        self.repo_root = repo_root.resolve()
        self.config = config
        self.context_filename = config.tree.filename
        self._tree: dict[Path, ContextNode] = {}  # dir_path -> ContextNode

    def build_tree(self) -> dict[Path, ContextNode]:
        """Scan the repo and build the full context tree."""
        self._tree = {}
        self._scan_directory(self.repo_root, depth=0)
        self._resolve_parents()
        self._parse_lateral_links()
        return self._tree

    def _scan_directory(self, directory: Path, depth: int) -> None:
        """Recursively scan for CONTEXT.md files."""
        if depth > self.config.tree.max_depth:
            return

        # Skip hidden directories and common non-code directories
        skip_dirs = {
            ".git", ".contextsync", "__pycache__", "node_modules",
            ".venv", "venv", ".env", ".tox", ".mypy_cache",
            ".pytest_cache", ".ruff_cache", "dist", "build",
            ".next", ".nuxt", "coverage",
        }

        context_path = directory / self.context_filename
        if context_path.exists():
            content = context_path.read_text(encoding="utf-8", errors="replace")
            self._tree[directory] = ContextNode(
                path=context_path,
                dir_path=directory,
                depth=depth,
                content=content,
                exists=True,
            )
        else:
            # Track potential locations (directory exists but no CONTEXT.md yet)
            self._tree[directory] = ContextNode(
                path=context_path,
                dir_path=directory,
                depth=depth,
                exists=False,
            )

        try:
            for child in sorted(directory.iterdir()):
                if child.is_dir() and child.name not in skip_dirs:
                    self._scan_directory(child, depth + 1)
        except PermissionError:
            pass

    def _resolve_parents(self) -> None:
        """Link child nodes to their nearest parent with a CONTEXT.md."""
        for dir_path, node in self._tree.items():
            if dir_path == self.repo_root:
                continue

            parent_dir = dir_path.parent
            while parent_dir >= self.repo_root:
                if parent_dir in self._tree and self._tree[parent_dir].exists:
                    node.parent = self._tree[parent_dir]
                    self._tree[parent_dir].children.append(node)
                    break
                parent_dir = parent_dir.parent

    def _parse_lateral_links(self) -> None:
        """Extract lateral relationship links from ## Relationships sections."""
        for node in self._tree.values():
            if not node.exists or not node.content:
                continue

            # Find ## Relationships section
            in_relationships = False
            for line in node.content.split("\n"):
                if line.strip() == "## Relationships":
                    in_relationships = True
                    continue
                if in_relationships and line.startswith("## "):
                    break
                if in_relationships and line.strip().startswith("- **"):
                    # Extract path references like "→ notifications" or "← orders"
                    match = re.search(r"[→←]\s*(\w+)", line)
                    if match:
                        node.lateral_links.append(match.group(1))

    def find_nearest_context(self, file_path: Path) -> Optional[ContextNode]:
        """Find the nearest CONTEXT.md ancestor for a given file.

        Walks up from the file's directory until finding a directory
        that has (or should have) a CONTEXT.md.
        """
        if not file_path.is_absolute():
            file_path = self.repo_root / file_path

        directory = file_path.parent if file_path.is_file() else file_path

        while directory >= self.repo_root:
            if directory in self._tree and self._tree[directory].exists:
                return self._tree[directory]
            directory = directory.parent

        return None

    def get_impact_set(self, changed_files: list[str]) -> list[ContextNode]:
        """Given a list of changed file paths, determine which CONTEXT.md files are impacted.

        Returns nodes that need evaluation (not necessarily update — salience decides that).
        """
        impacted: set[Path] = set()

        for file_path_str in changed_files:
            file_path = self.repo_root / file_path_str

            # Find nearest context node
            node = self.find_nearest_context(file_path)
            if node:
                impacted.add(node.dir_path)

                # Also consider parent (change might affect parent's summary)
                if node.parent:
                    impacted.add(node.parent.dir_path)

                # Check lateral links
                for link in node.lateral_links:
                    # Resolve link to a directory path
                    for dir_path, other_node in self._tree.items():
                        if other_node.exists and dir_path.name == link:
                            impacted.add(dir_path)

        # Return existing context nodes only
        return [
            self._tree[p] for p in impacted
            if p in self._tree and self._tree[p].exists
        ]

    def get_ancestor_chain(self, file_path: Path) -> list[ContextNode]:
        """Get the full ancestor chain of context files for a given file.

        Used by the consumption layer to scope context loading.
        Returns: [immediate_context, parent_context, ..., root_context]
        """
        chain = []
        node = self.find_nearest_context(file_path)

        while node:
            chain.append(node)
            node = node.parent

        return chain

    def get_directories_needing_context(self) -> list[Path]:
        """Find directories that meet the threshold for needing a CONTEXT.md but don't have one.

        Uses min_files_for_context from config.
        """
        needs_context = []
        min_files = self.config.tree.min_files_for_context

        for dir_path, node in self._tree.items():
            if node.exists:
                continue

            # Count code files in this directory (non-recursive)
            try:
                code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}
                code_files = [
                    f for f in dir_path.iterdir()
                    if f.is_file() and f.suffix in code_extensions
                ]
                if len(code_files) >= min_files:
                    needs_context.append(dir_path)
            except (PermissionError, FileNotFoundError):
                pass

        return needs_context
