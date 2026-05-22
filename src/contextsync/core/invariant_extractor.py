"""Invariant Extractor — extracts verifiable rules from code patterns.

Analyzes source files to discover implicit invariants: type patterns,
decorator constraints, naming conventions, base class requirements, and
assertion patterns from tests. These become the ## Invariants section
in Level 2+ CONTEXT.md files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from contextsync.core.code_extractor import extract_directory_structure, FileStructure


@dataclass
class Invariant:
    """A verifiable rule extracted from code patterns."""
    rule_id: str
    description: str
    source: str          # "naming_convention" | "base_class" | "decorator" | "type_hint" | "test_assertion"
    confidence: float    # 0.0-1.0
    affected_files: list[str] = field(default_factory=list)
    example: str = ""    # example code showing the pattern


class InvariantExtractor:
    """Extracts verifiable rules from code patterns in a directory."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def extract(self, dir_path: Path) -> list[Invariant]:
        """Extract all invariants from a directory's code files.

        Runs multiple extraction strategies and deduplicates results.
        """
        invariants: list[Invariant] = []

        structures = extract_directory_structure(dir_path)
        if not structures:
            return invariants

        invariants.extend(self._extract_base_class_patterns(structures))
        invariants.extend(self._extract_decorator_patterns(structures))
        invariants.extend(self._extract_naming_conventions(structures, dir_path))
        invariants.extend(self._extract_type_hint_patterns(structures))

        # Also check for test files in sibling test directories
        test_invariants = self._extract_test_assertions(dir_path)
        invariants.extend(test_invariants)

        # Deduplicate by rule_id
        seen: set[str] = set()
        unique: list[Invariant] = []
        for inv in invariants:
            if inv.rule_id not in seen:
                seen.add(inv.rule_id)
                unique.append(inv)

        return unique

    def _extract_base_class_patterns(self, structures: dict[str, FileStructure]) -> list[Invariant]:
        """If all/most classes inherit from a common base, that's an invariant."""
        invariants: list[Invariant] = []
        base_counts: dict[str, list[str]] = {}  # base_name -> [file1, file2, ...]

        for filename, structure in structures.items():
            for cls in structure.classes:
                for base in cls.bases:
                    base_name = base.split(".")[-1]  # strip module prefix
                    if base_name not in ("object", "Exception", "ABC"):
                        base_counts.setdefault(base_name, []).append(filename)

        total_files_with_classes = sum(1 for s in structures.values() if s.classes)
        if total_files_with_classes == 0:
            return invariants

        for base_name, files in base_counts.items():
            ratio = len(files) / total_files_with_classes
            if len(files) >= 2 and ratio >= 0.5:
                invariants.append(Invariant(
                    rule_id=f"base-class-{base_name.lower()}",
                    description=f"Classes in this module should inherit from `{base_name}`",
                    source="base_class",
                    confidence=min(ratio, 0.9),
                    affected_files=files,
                    example=f"class MyClass({base_name}): ...",
                ))

        return invariants

    def _extract_decorator_patterns(self, structures: dict[str, FileStructure]) -> list[Invariant]:
        """If decorators are consistently used, they indicate constraints."""
        invariants: list[Invariant] = []
        decorator_counts: dict[str, int] = {}
        total_methods = 0

        for structure in structures.values():
            for cls in structure.classes:
                for method in cls.methods:
                    total_methods += 1
                    for deco in method.decorators:
                        deco_name = deco.split("(")[0]
                        decorator_counts[deco_name] = decorator_counts.get(deco_name, 0) + 1

        if total_methods == 0:
            return invariants

        # Common constraint decorators
        constraint_decorators = {
            "login_required": "All views require authentication",
            "permission_required": "Views enforce permission checks",
            "transaction.atomic": "Database operations are wrapped in transactions",
            "csrf_protect": "Views are CSRF-protected",
            "require_http_methods": "Views restrict HTTP methods",
            "cached_property": "Expensive computations are cached as properties",
            "abstractmethod": "Subclasses must implement abstract methods",
        }

        for deco, count in decorator_counts.items():
            if deco in constraint_decorators and count >= 2:
                invariants.append(Invariant(
                    rule_id=f"decorator-{deco.replace('.', '-')}",
                    description=constraint_decorators[deco],
                    source="decorator",
                    confidence=0.7,
                    example=f"@{deco}",
                ))

        return invariants

    def _extract_naming_conventions(self, structures: dict[str, FileStructure], dir_path: Path) -> list[Invariant]:
        """Detect consistent naming patterns that imply invariants."""
        invariants: list[Invariant] = []

        # Check for suffix patterns (e.g., _cents, _bytes, _ms)
        suffix_counts: dict[str, int] = {}
        for structure in structures.values():
            for cls in structure.classes:
                for var in cls.class_variables:
                    for suffix in ["_cents", "_bytes", "_ms", "_seconds", "_count", "_id", "_uuid", "_pk"]:
                        if var.endswith(suffix):
                            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1

        suffix_meanings = {
            "_cents": "Monetary amounts are stored as integers in cents (never float)",
            "_bytes": "Size values are stored as raw byte counts",
            "_ms": "Time durations are stored in milliseconds",
            "_seconds": "Time durations are stored in seconds",
        }

        for suffix, count in suffix_counts.items():
            if count >= 2 and suffix in suffix_meanings:
                invariants.append(Invariant(
                    rule_id=f"naming-{suffix.lstrip('_')}",
                    description=suffix_meanings[suffix],
                    source="naming_convention",
                    confidence=0.6,
                    example=f"amount{suffix}: int = 1999",
                ))

        # Check for consistent file naming patterns
        py_files = [f for f in dir_path.iterdir() if f.suffix == ".py" and f.name != "__init__.py"] if dir_path.exists() else []
        if len(py_files) >= 3:
            # Check if all files follow a pattern (e.g., all lowercase, all match module names)
            all_lowercase = all(f.stem == f.stem.lower() for f in py_files)
            if all_lowercase:
                invariants.append(Invariant(
                    rule_id="naming-lowercase-files",
                    description="All Python files use lowercase_with_underscores naming",
                    source="naming_convention",
                    confidence=0.8,
                    affected_files=[f.name for f in py_files[:5]],
                ))

        return invariants

    def _extract_type_hint_patterns(self, structures: dict[str, FileStructure]) -> list[Invariant]:
        """Extract invariants from consistent type annotation usage."""
        invariants: list[Invariant] = []

        # Check if all public methods have return type annotations
        total_public_methods = 0
        annotated_methods = 0

        for structure in structures.values():
            for cls in structure.classes:
                for method in cls.methods:
                    if not method.name.startswith("_"):
                        total_public_methods += 1
                        if "->" in method.signature:
                            annotated_methods += 1

            for func in structure.functions:
                if not func.name.startswith("_"):
                    total_public_methods += 1
                    if "->" in func.signature:
                        annotated_methods += 1

        if total_public_methods >= 3:
            ratio = annotated_methods / total_public_methods
            if ratio >= 0.7:
                invariants.append(Invariant(
                    rule_id="type-hints-required",
                    description="Public functions and methods should have return type annotations",
                    source="type_hint",
                    confidence=ratio,
                    example="def process(self, data: bytes) -> Result: ...",
                ))

        return invariants

    def _extract_test_assertions(self, dir_path: Path) -> list[Invariant]:
        """Look for test files and extract assertion patterns as invariants."""
        invariants: list[Invariant] = []

        # Common test directory patterns
        test_dirs = [
            dir_path / "tests",
            dir_path.parent / "tests",
            dir_path.parent / "tests" / dir_path.name,
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            test_files = [f for f in test_dir.iterdir() if f.name.startswith("test_") and f.suffix == ".py"]
            for test_file in test_files[:5]:  # cap
                try:
                    content = test_file.read_text(encoding="utf-8", errors="replace")
                    # Look for isinstance assertions
                    isinstance_checks = re.findall(
                        r"assert\s+isinstance\(.*?,\s*(\w+)\)", content
                    )
                    for type_name in set(isinstance_checks):
                        if type_name[0].isupper():
                            invariants.append(Invariant(
                                rule_id=f"test-type-{type_name.lower()}",
                                description=f"Return values are validated as `{type_name}` instances in tests",
                                source="test_assertion",
                                confidence=0.7,
                                affected_files=[test_file.name],
                            ))

                    # Look for assertRaises patterns (error handling invariants)
                    error_types = re.findall(
                        r"(?:assertRaises|pytest\.raises)\((\w+)\)", content
                    )
                    for error_type in set(error_types):
                        if error_type[0].isupper():
                            invariants.append(Invariant(
                                rule_id=f"test-error-{error_type.lower()}",
                                description=f"Invalid operations should raise `{error_type}`",
                                source="test_assertion",
                                confidence=0.6,
                                affected_files=[test_file.name],
                            ))
                except Exception:
                    pass

        return invariants


def format_invariants_for_llm(invariants: list[Invariant]) -> str:
    """Format extracted invariants as text for inclusion in LLM prompts."""
    if not invariants:
        return "(no code invariants detected)"

    parts = ["Auto-extracted code invariants:"]
    for inv in invariants:
        conf = f"{inv.confidence:.0%}"
        parts.append(f"- [{inv.source}] {inv.description} (confidence: {conf})")
        if inv.example:
            parts.append(f"  Example: {inv.example}")

    return "\n".join(parts)
