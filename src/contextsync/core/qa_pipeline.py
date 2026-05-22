"""QA Pipeline — validates patched context files for accuracy."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class QACheck:
    """Result of a single QA check."""
    check_name: str
    passed: bool
    message: str
    severity: str = "warning"  # warning | error


@dataclass
class QAResult:
    """Aggregate result of all QA checks on a patched context file."""
    checks: list[QACheck] = field(default_factory=list)
    passed: bool = True
    requires_human_review: bool = False

    @property
    def errors(self) -> list[QACheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[QACheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]


class QAPipeline:
    """Validates patched CONTEXT.md files for accuracy and consistency."""

    def __init__(self, repo_root: Path, max_diff_percent: float = 0.5):
        self.repo_root = repo_root
        self.max_diff_percent = max_diff_percent

    def validate(
        self,
        original_content: str,
        patched_content: str,
        directory: Path,
    ) -> QAResult:
        """Run all QA checks on a patched context file.

        Args:
            original_content: Original CONTEXT.md content
            patched_content: Patched CONTEXT.md content from LLM
            directory: The directory this CONTEXT.md belongs to

        Returns:
            QAResult with all check outcomes
        """
        result = QAResult()

        # 1. Entity existence check
        self._check_entities(patched_content, directory, result)

        # 2. Schema compliance
        self._check_schema(patched_content, result)

        # 3. Diff size guard
        self._check_diff_size(original_content, patched_content, result)

        # 4. No empty sections
        self._check_empty_sections(patched_content, result)

        # 5. Metadata presence
        self._check_metadata(patched_content, result)

        # 6. Level 2+ section validation
        self._check_evolution_format(patched_content, result)
        self._check_invariant_validity(patched_content, directory, result)

        # Set overall pass/fail
        result.passed = len(result.errors) == 0
        result.requires_human_review = len(result.warnings) > 0 or not result.passed

        return result

    def _check_entities(self, content: str, directory: Path, result: QAResult) -> None:
        """Verify that file/module references in the context actually exist."""
        # Find backtick-quoted file references like `services/stripe_client.py`
        file_refs = re.findall(r'`([^`]+\.\w+)`', content)

        for ref in file_refs:
            # Skip obvious non-file references
            if ref.startswith("pip ") or ref.startswith("npm ") or "=" in ref:
                continue
            if not any(ref.endswith(ext) for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".yaml", ".yml", ".json", ".toml"]):
                continue

            # Check if file exists relative to the directory
            full_path = directory / ref
            if not full_path.exists():
                # Also check relative to repo root
                alt_path = self.repo_root / ref
                if not alt_path.exists():
                    result.checks.append(QACheck(
                        check_name="entity_existence",
                        passed=False,
                        message=f"Referenced file `{ref}` does not exist in {directory.name}/",
                        severity="warning",
                    ))

    def _check_schema(self, content: str, result: QAResult) -> None:
        """Check that the context file has required sections."""
        required_sections = ["## Purpose", "## Key Components"]

        for section in required_sections:
            if section not in content:
                result.checks.append(QACheck(
                    check_name="schema_compliance",
                    passed=False,
                    message=f"Missing required section: {section}",
                    severity="warning",
                ))

        # Check for a title (# heading)
        if not re.search(r'^#\s+\w', content, re.MULTILINE):
            result.checks.append(QACheck(
                check_name="schema_compliance",
                passed=False,
                message="Missing title heading (# ModuleName)",
                severity="warning",
            ))

    def _check_diff_size(self, original: str, patched: str, result: QAResult) -> None:
        """Flag if too much of the content changed (possible hallucination)."""
        if not original.strip():
            return  # New file, no comparison

        orig_lines = set(original.strip().split("\n"))
        patch_lines = set(patched.strip().split("\n"))

        if len(orig_lines) == 0:
            return

        changed = len(orig_lines.symmetric_difference(patch_lines))
        total = max(len(orig_lines), len(patch_lines))
        diff_ratio = changed / total

        if diff_ratio > self.max_diff_percent:
            result.checks.append(QACheck(
                check_name="diff_size_guard",
                passed=False,
                message=f"Patch changes {diff_ratio:.0%} of content (threshold: {self.max_diff_percent:.0%}). Possible hallucination — requires review.",
                severity="warning",
            ))
            result.requires_human_review = True

    def _check_empty_sections(self, content: str, result: QAResult) -> None:
        """Check for section headers with no content."""
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if line.startswith("## "):
                # Check if next non-empty line is another header or end of file
                has_content = False
                for j in range(i + 1, min(i + 5, len(lines))):
                    stripped = lines[j].strip()
                    if stripped and not stripped.startswith("##"):
                        has_content = True
                        break
                    if stripped.startswith("##"):
                        break

                if not has_content:
                    result.checks.append(QACheck(
                        check_name="empty_section",
                        passed=False,
                        message=f"Section '{line.strip()}' is empty",
                        severity="warning",
                    ))

    def _check_metadata(self, content: str, result: QAResult) -> None:
        """Check that sync metadata is present."""
        if "<!-- last_synced:" not in content:
            result.checks.append(QACheck(
                check_name="metadata",
                passed=False,
                message="Missing <!-- last_synced: --> metadata",
                severity="warning",
            ))

        if "<!-- sync_hash:" not in content:
            result.checks.append(QACheck(
                check_name="metadata",
                passed=False,
                message="Missing <!-- sync_hash: --> metadata",
                severity="warning",
            ))

    def _check_evolution_format(self, content: str, result: QAResult) -> None:
        """Validate the ## Evolution section if present."""
        if "## Evolution" not in content:
            return  # Section not present, that's fine

        # Extract evolution section content
        in_evolution = False
        dates_found: list[str] = []
        for line in content.split("\n"):
            if line.strip() == "## Evolution":
                in_evolution = True
                continue
            if in_evolution and line.startswith("## "):
                break
            if in_evolution:
                # Look for date patterns like "YYYY-MM" or "- YYYY-MM"
                date_match = re.search(r"(\d{4}-\d{2})", line)
                if date_match:
                    dates_found.append(date_match.group(1))

        # Check chronological order
        if len(dates_found) >= 2:
            for i in range(1, len(dates_found)):
                if dates_found[i] < dates_found[i - 1]:
                    result.checks.append(QACheck(
                        check_name="evolution_format",
                        passed=False,
                        message=f"Evolution dates are not chronological: {dates_found[i-1]} > {dates_found[i]}",
                        severity="warning",
                    ))
                    break

    def _check_invariant_validity(self, content: str, directory: Path, result: QAResult) -> None:
        """Validate the ## Invariants section if present — spot-check claims."""
        if "## Invariants" not in content:
            return  # Section not present, that's fine

        # Extract invariants section
        in_invariants = False
        invariant_lines: list[str] = []
        for line in content.split("\n"):
            if line.strip() == "## Invariants":
                in_invariants = True
                continue
            if in_invariants and line.startswith("## "):
                break
            if in_invariants and line.strip():
                invariant_lines.append(line.strip())

        # Spot-check: if invariants mention base classes, verify they exist
        for line in invariant_lines:
            # Look for class name references in backticks
            class_refs = re.findall(r'`([A-Z]\w+)`', line)
            for cls_name in class_refs:
                # Quick check: search for the class name in directory files
                found = False
                try:
                    for py_file in directory.glob("*.py"):
                        file_content = py_file.read_text(encoding="utf-8", errors="replace")
                        if f"class {cls_name}" in file_content or f"({cls_name})" in file_content:
                            found = True
                            break
                except Exception:
                    found = True  # Don't penalize on read errors

                if not found:
                    result.checks.append(QACheck(
                        check_name="invariant_validity",
                        passed=False,
                        message=f"Invariant mentions `{cls_name}` but it's not found in {directory.name}/",
                        severity="warning",
                    ))
