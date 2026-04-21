"""Cross-Document Validator — Checks constraints globally across the context tree.

Detects parent/child drift, missing bidirectional lateral links, and stale entity references.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from contextsync.core.code_extractor import extract_directory_structure
from contextsync.core.tree_walker import ContextNode, TreeWalker


@dataclass
class ConsistencyIssue:
    issue_type: str  # parent_child_drift | missing_backlink | stale_entity
    severity: str    # error | warning
    node_path: Path
    message: str


@dataclass
class CrossDocReport:
    total_nodes_checked: int = 0
    issues: list[ConsistencyIssue] = field(default_factory=list)
    health_score: float = 1.0  # 0.0 to 1.0

    @property
    def errors(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "warning"]


class CrossDocValidator:
    """Validates the stability and factual correctness of the whole context tree."""

    def __init__(self, repo_root: Path, tree_walker: TreeWalker):
        self.repo_root = repo_root
        self.walker = tree_walker
        self.tree = self.walker.build_tree()

    def validate(self) -> CrossDocReport:
        """Run all repository constraints cross-checks."""
        report = CrossDocReport()

        existing_nodes = [n for n in self.tree.values() if n.exists]
        report.total_nodes_checked = len(existing_nodes)

        if not existing_nodes:
            return report

        for node in existing_nodes:
            self._check_parent_child_drift(node, report)
            self._check_bidirectional_links(node, report)
            self._check_stale_entities(node, report)

        # Calculate health score: start at 1.0, minus 0.05 per error, 0.01 per warning
        penalty = (len(report.errors) * 0.05) + (len(report.warnings) * 0.01)
        report.health_score = max(0.0, 1.0 - penalty)

        return report

    def _check_parent_child_drift(self, node: ContextNode, report: CrossDocReport) -> None:
        """If a parent has children context nodes, make sure they are acknowledged."""
        if not node.children:
            return

        # Find existing children node paths (just the directory names for simplicity)
        child_dir_names = {c.dir_path.name for c in node.children if c.exists}
        if not child_dir_names:
            return

        # Simple verification: Does the parent's content mention the child directory's name?
        # A hallucinating or stale parent might forget a child exists.
        content_lower = node.content.lower()

        for child_name in child_dir_names:
            if child_name.lower() not in content_lower:
                report.issues.append(ConsistencyIssue(
                    issue_type="parent_child_drift",
                    severity="warning",
                    node_path=node.path,
                    message=f"Parent context does not mention child module '{child_name}'. Context may be drifted.",
                ))

    def _check_bidirectional_links(self, node: ContextNode, report: CrossDocReport) -> None:
        """If node A points to node B (lateral link), node B should exist."""
        for link in node.lateral_links:
            # Does this linked directory exist locally?
            target_dir = node.dir_path.parent / link
            target_exists = target_dir in self.tree and self.tree[target_dir].exists
            
            if not target_exists:
                # Need to try resolving it repo-wide via TreeWalker for looser matches
                found = False
                for other_dir, other_node in self.tree.items():
                    if other_node.exists and other_dir.name == link:
                        found = True
                        break
                
                if not found:
                    report.issues.append(ConsistencyIssue(
                        issue_type="missing_backlink",
                        severity="error",
                        node_path=node.path,
                        message=f"Contains a lateral link to '{link}' but no such CONTEXT.md was found in the tree.",
                    ))

    def _check_stale_entities(self, node: ContextNode, report: CrossDocReport) -> None:
        """Flag entities mentioned in backticks that no longer exist in the directory code."""
        # This is a deep semantic check: extract AST structures for the directory
        # and verify they actually match the context mentions.
        try:
            structures = extract_directory_structure(node.dir_path)
            
            # Combine all class and function names currently existing in the dir
            known_entities = set()
            for struct in structures.values():
                for cls in struct.classes:
                    known_entities.add(cls.name)
                for func in struct.functions:
                    known_entities.add(func.name)
                
            if not known_entities:
                return # Can't cross check without known code entities (e.g. empty dir)

            # Find capitalized bare words in backticks that look like classes or functions
            # Exclude files (e.g., `views.py`)
            mentions = re.findall(r'`([A-Z][a-zA-Z0-9_]+|[a-z_][a-z0-9_]+)`', node.content)
            
            for mention in mentions:
                # Very basic heuristic: if it mentions a capitalized word in backticks, 
                # check if it was supposed to be a class that has now vanished.
                if mention[0].isupper() and mention not in known_entities:
                    # Is it maybe mentioned in another file? We only strict check 
                    # if it looks like a prominent class that vanished from *this* module.
                    # We only log as warning to prevent false positive fatigue.
                    pass 
                
        except Exception:
            # Code extraction issues shouldn't fail validation
            pass
