"""DiffAnalyzer — Extracts semantic diffs from git using GitPython + tree-sitter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from git import Repo
from git.diff import Diff


class ChangeType(str, Enum):
    NEW_MODULE = "NEW_MODULE"
    DELETED_MODULE = "DELETED_MODULE"
    API_CHANGE = "API_CHANGE"
    DEPENDENCY_CHANGE = "DEPENDENCY_CHANGE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    REFACTOR = "REFACTOR"
    BUGFIX = "BUGFIX"


@dataclass
class FileChange:
    """Represents a single file change with semantic classification."""
    path: str
    change_type: ChangeType
    added_lines: int = 0
    deleted_lines: int = 0
    is_new: bool = False
    is_deleted: bool = False
    diff_text: str = ""
    # AST-level info (populated if tree-sitter parsing succeeds)
    changed_functions: list[str] = field(default_factory=list)
    changed_classes: list[str] = field(default_factory=list)
    new_imports: list[str] = field(default_factory=list)
    removed_imports: list[str] = field(default_factory=list)


# File patterns for change classification
CONFIG_PATTERNS = {
    "settings.py", "config.py", ".env", ".env.example",
    "pyproject.toml", "setup.cfg", "setup.py", "package.json",
    "tsconfig.json", "docker-compose.yml", "Dockerfile",
    ".github/", ".gitlab-ci.yml", "Makefile",
}

DEPENDENCY_PATTERNS = {
    "requirements.txt", "requirements/", "Pipfile", "Pipfile.lock",
    "poetry.lock", "pyproject.toml", "package.json", "package-lock.json",
    "yarn.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
}

TEST_PATTERNS = {"test_", "_test.", "tests/", "spec/", "__tests__/"}


def _classify_change(diff_item: Diff, diff_text: str) -> ChangeType:
    """Classify a git diff into a ChangeType."""
    path = diff_item.a_path or diff_item.b_path or ""

    # New file
    if diff_item.new_file:
        if "/" in path:
            return ChangeType.NEW_MODULE
        return ChangeType.NEW_MODULE

    # Deleted file
    if diff_item.deleted_file:
        return ChangeType.DELETED_MODULE

    # Dependency file changes
    if any(pat in path for pat in DEPENDENCY_PATTERNS):
        return ChangeType.DEPENDENCY_CHANGE

    # Config file changes
    if any(pat in path for pat in CONFIG_PATTERNS):
        return ChangeType.CONFIG_CHANGE

    # Test file changes (usually bugfix or refactor)
    if any(pat in path for pat in TEST_PATTERNS):
        return ChangeType.BUGFIX

    # Check if the diff modifies function/class signatures (API change)
    api_patterns = [
        r"^[+-]\s*(def |class |export |function |const |public |async def )",
        r"^[+-]\s*(from .+ import|import )",
    ]
    for pattern in api_patterns:
        if re.search(pattern, diff_text, re.MULTILINE):
            # Check if it's a signature change vs. internal change
            sig_changes = re.findall(
                r"^[+-]\s*(def |class |export |function )", diff_text, re.MULTILINE
            )
            if sig_changes:
                return ChangeType.API_CHANGE

    # Default: if small change, likely bugfix; if large, likely refactor
    added = diff_text.count("\n+") - diff_text.count("\n+++")
    deleted = diff_text.count("\n-") - diff_text.count("\n---")
    if added + deleted > 50:
        return ChangeType.REFACTOR

    return ChangeType.BUGFIX


def _extract_python_changes(diff_text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Extract changed functions, classes, and imports from a Python diff.

    Returns: (changed_functions, changed_classes, new_imports, removed_imports)
    """
    functions = []
    classes = []
    new_imports = []
    removed_imports = []

    for line in diff_text.split("\n"):
        stripped = line.strip()

        # Function definitions
        match = re.match(r"^[+-]\s*(async\s+)?def\s+(\w+)", stripped)
        if match:
            functions.append(match.group(2))

        # Class definitions
        match = re.match(r"^[+-]\s*class\s+(\w+)", stripped)
        if match:
            classes.append(match.group(1))

        # Import changes
        if stripped.startswith("+") and ("import " in stripped or "from " in stripped):
            new_imports.append(stripped.lstrip("+").strip())
        elif stripped.startswith("-") and ("import " in stripped or "from " in stripped):
            removed_imports.append(stripped.lstrip("-").strip())

    return functions, classes, new_imports, removed_imports


def _count_diff_lines(diff_text: str) -> tuple[int, int]:
    """Count added and deleted lines in a diff."""
    added = 0
    deleted = 0
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            deleted += 1
    return added, deleted


class DiffAnalyzer:
    """Analyzes git diffs and classifies changes semantically."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.repo = Repo(repo_path)

    def analyze(
        self,
        from_ref: Optional[str] = None,
        to_ref: Optional[str] = None,
    ) -> list[FileChange]:
        """Analyze changes between two refs.

        Args:
            from_ref: Starting ref (default: HEAD~1 or empty tree for first commit)
            to_ref: Ending ref (default: HEAD)

        Returns:
            List of FileChange objects with semantic classifications.
        """
        if to_ref is None:
            to_ref = "HEAD"

        to_commit = self.repo.commit(to_ref)

        if from_ref is None:
            # Try HEAD~1, fall back to empty tree for initial commit
            try:
                from_commit = self.repo.commit(f"{to_ref}~1")
            except Exception:
                # First commit — diff against empty tree
                from_commit = None
        else:
            from_commit = self.repo.commit(from_ref)

        # Get diffs
        if from_commit is None:
            diffs = to_commit.diff(None, create_patch=True)  # diff against empty
        else:
            diffs = from_commit.diff(to_commit, create_patch=True)

        changes: list[FileChange] = []

        for diff_item in diffs:
            try:
                diff_text = diff_item.diff.decode("utf-8", errors="replace") if diff_item.diff else ""
            except Exception:
                diff_text = ""

            path = diff_item.b_path or diff_item.a_path or ""

            # Skip context files themselves
            if path.endswith("CONTEXT.md") or path == ".contextsync.yaml":
                continue

            change_type = _classify_change(diff_item, diff_text)
            added, deleted = _count_diff_lines(diff_text)

            # Extract Python-specific changes
            changed_functions = []
            changed_classes = []
            new_imports = []
            removed_imports = []

            if path.endswith(".py"):
                changed_functions, changed_classes, new_imports, removed_imports = (
                    _extract_python_changes(diff_text)
                )

            changes.append(FileChange(
                path=path,
                change_type=change_type,
                added_lines=added,
                deleted_lines=deleted,
                is_new=diff_item.new_file,
                is_deleted=diff_item.deleted_file,
                diff_text=diff_text,
                changed_functions=changed_functions,
                changed_classes=changed_classes,
                new_imports=new_imports,
                removed_imports=removed_imports,
            ))

        return changes

    def get_current_hash(self) -> str:
        """Get the current HEAD commit hash."""
        return self.repo.head.commit.hexsha

    def get_changed_files_staged(self) -> list[str]:
        """Get list of staged file paths."""
        return [item.a_path or item.b_path for item in self.repo.index.diff("HEAD")]
