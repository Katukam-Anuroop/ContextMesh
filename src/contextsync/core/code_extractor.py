"""Code Extractor — extracts structural information from source files for rich context generation.

Pulls function signatures, class definitions, docstrings, imports, decorators,
and key patterns from code files to give the LLM enough detail to generate
precise, useful CONTEXT.md files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class FunctionInfo:
    name: str
    signature: str  # full def line including args
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    is_async: bool = False
    is_class_method: bool = False
    class_name: str = ""


@dataclass
class ClassInfo:
    name: str
    bases: list[str] = field(default_factory=list)
    docstring: str = ""
    methods: list[FunctionInfo] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    class_variables: list[str] = field(default_factory=list)


@dataclass
class FileStructure:
    """Complete structural summary of a source file."""
    path: str
    language: str
    imports: list[str] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    module_docstring: str = ""
    constants: list[str] = field(default_factory=list)
    line_count: int = 0

    def to_summary(self, max_methods_per_class: int = 8) -> str:
        """Generate a concise human-readable summary for the LLM."""
        parts: list[str] = []

        # Module docstring
        if self.module_docstring:
            doc = self.module_docstring.strip().split("\n")[0]  # First line only
            parts.append(f"  Docstring: {doc}")

        # Imports (only non-stdlib)
        notable_imports = [i for i in self.imports if not i.startswith("import os")
                          and not i.startswith("import sys")
                          and not i.startswith("from __future__")]
        if notable_imports:
            parts.append(f"  Imports: {'; '.join(notable_imports[:10])}")

        # Classes with methods
        for cls in self.classes:
            bases_str = f"({', '.join(cls.bases)})" if cls.bases else ""
            parts.append(f"  class {cls.name}{bases_str}:")
            if cls.docstring:
                doc_first = cls.docstring.strip().split("\n")[0]
                parts.append(f"    \"{doc_first}\"")
            if cls.class_variables:
                parts.append(f"    Fields: {', '.join(cls.class_variables[:10])}")
            for method in cls.methods[:max_methods_per_class]:
                deco = f"  @{method.decorators[0]}" if method.decorators else ""
                async_prefix = "async " if method.is_async else ""
                parts.append(f"    {async_prefix}{method.signature}{deco}")
                if method.docstring:
                    doc_first = method.docstring.strip().split("\n")[0]
                    parts.append(f"      \"{doc_first}\"")
            if len(cls.methods) > max_methods_per_class:
                parts.append(f"    ... and {len(cls.methods) - max_methods_per_class} more methods")

        # Top-level functions
        for func in self.functions:
            deco = f"  @{func.decorators[0]}" if func.decorators else ""
            async_prefix = "async " if func.is_async else ""
            parts.append(f"  {async_prefix}{func.signature}{deco}")
            if func.docstring:
                doc_first = func.docstring.strip().split("\n")[0]
                parts.append(f"    \"{doc_first}\"")

        # Constants
        if self.constants:
            parts.append(f"  Constants: {', '.join(self.constants[:8])}")

        return "\n".join(parts) if parts else "  (empty or non-parseable)"


def extract_python_structure(file_path: Path) -> FileStructure:
    """Extract structural info from a Python file using regex-based parsing.

    This is a lightweight alternative to full AST parsing — fast enough
    for scanning hundreds of files during scaffold.
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return FileStructure(path=str(file_path), language="python")

    lines = content.split("\n")
    structure = FileStructure(
        path=str(file_path.name),
        language="python",
        line_count=len(lines),
    )

    # Module docstring (first string literal)
    stripped = content.lstrip()
    if stripped.startswith('"""') or stripped.startswith("'''"):
        quote = stripped[:3]
        end = stripped.find(quote, 3)
        if end != -1:
            structure.module_docstring = stripped[3:end].strip()

    # Imports
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("import ") or stripped_line.startswith("from "):
            structure.imports.append(stripped_line)

    # Classes and functions
    current_class: Optional[ClassInfo] = None
    current_decorators: list[str] = []
    indent_level = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped_line = line.strip()

        # Track decorators
        if stripped_line.startswith("@"):
            deco = stripped_line[1:].split("(")[0]
            current_decorators.append(deco)
            i += 1
            continue

        # Class definition
        class_match = re.match(r'^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:', stripped_line)
        if class_match and not line.startswith(" " * 4 + " "):
            name = class_match.group(1)
            bases = [b.strip() for b in (class_match.group(2) or "").split(",") if b.strip()]
            docstring = _extract_docstring(lines, i + 1)

            current_class = ClassInfo(
                name=name,
                bases=bases,
                docstring=docstring,
                decorators=current_decorators.copy(),
            )

            # Extract class variables (lines with = that aren't methods)
            for j in range(i + 1, min(i + 50, len(lines))):
                cl = lines[j].strip()
                if cl.startswith("def ") or cl.startswith("async def ") or cl.startswith("class "):
                    break
                var_match = re.match(r'^(\w+)\s*=', cl)
                if var_match and not cl.startswith("#"):
                    current_class.class_variables.append(var_match.group(1))

            structure.classes.append(current_class)
            current_decorators = []
            i += 1
            continue

        # Function/method definition
        func_match = re.match(r'^(\s*)(async\s+)?def\s+(\w+)\s*\(([^)]*)\)', stripped_line)
        if func_match:
            indent = len(func_match.group(1) or "")
            is_async = bool(func_match.group(2))
            name = func_match.group(3)
            args = func_match.group(4)

            # Get return type if present
            return_match = re.search(r'->\s*(.+?):', stripped_line)
            return_type = return_match.group(1).strip() if return_match else ""

            sig = f"def {name}({args})"
            if return_type:
                sig += f" -> {return_type}"

            docstring = _extract_docstring(lines, i + 1)

            func_info = FunctionInfo(
                name=name,
                signature=sig,
                decorators=current_decorators.copy(),
                docstring=docstring,
                is_async=is_async,
            )

            # Is this a method (indented under a class)?
            if indent >= 4 and current_class:
                func_info.is_class_method = True
                func_info.class_name = current_class.name
                current_class.methods.append(func_info)
            else:
                structure.functions.append(func_info)
                if indent == 0:
                    current_class = None  # Exited class scope

            current_decorators = []
            i += 1
            continue

        # Constants (top-level UPPER_CASE = ...)
        const_match = re.match(r'^([A-Z][A-Z0-9_]+)\s*=', stripped_line)
        if const_match and not line.startswith(" "):
            structure.constants.append(const_match.group(1))

        # Reset decorators if we hit a non-decorator, non-def, non-class line
        if stripped_line and not stripped_line.startswith("@") and not stripped_line.startswith("#"):
            if not stripped_line.startswith("def ") and not stripped_line.startswith("class ") and not stripped_line.startswith("async def "):
                current_decorators = []

        i += 1

    return structure


def _extract_docstring(lines: list[str], start_idx: int) -> str:
    """Extract docstring starting after a def/class line."""
    if start_idx >= len(lines):
        return ""

    # Look for docstring in the next few lines
    for i in range(start_idx, min(start_idx + 3, len(lines))):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            if stripped.endswith(quote) and len(stripped) > 6:
                return stripped[3:-3].strip()
            # Multi-line docstring
            doc_lines = [stripped[3:]]
            for j in range(i + 1, min(i + 20, len(lines))):
                if quote in lines[j]:
                    doc_lines.append(lines[j].strip().replace(quote, ""))
                    return "\n".join(doc_lines).strip()
                doc_lines.append(lines[j].strip())
            return "\n".join(doc_lines).strip()
        elif stripped.startswith('"') or stripped.startswith("'"):
            return stripped.strip("\"'")
        else:
            break  # Not a docstring
    return ""


def extract_file_structure(file_path: Path) -> Optional[FileStructure]:
    """Extract structure from any supported file type."""
    suffix = file_path.suffix.lower()

    if suffix == ".py":
        return extract_python_structure(file_path)

    # For non-Python files, return a basic structure with first meaningful lines
    if suffix in {".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")

            structure = FileStructure(
                path=str(file_path.name),
                language=suffix.lstrip("."),
                line_count=len(lines),
            )

            # Extract imports
            for line in lines[:50]:
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    structure.imports.append(stripped)
                elif stripped.startswith("const ") or stripped.startswith("export "):
                    if "require(" in stripped or "import" in stripped:
                        structure.imports.append(stripped)

            return structure
        except Exception:
            pass

    return None


def extract_directory_structure(
    dir_path: Path,
    max_files: int = 30,
) -> dict[str, FileStructure]:
    """Extract structural info from all code files in a directory.

    Returns: dict of filename -> FileStructure
    """
    structures: dict[str, FileStructure] = {}
    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}

    try:
        files = sorted([
            f for f in dir_path.iterdir()
            if f.is_file() and f.suffix in code_extensions
            and f.name != "__init__.py"
        ])
    except (PermissionError, FileNotFoundError):
        return structures

    for file_path in files[:max_files]:
        structure = extract_file_structure(file_path)
        if structure:
            structures[file_path.name] = structure

    # Also process __init__.py if it has content
    init_file = dir_path / "__init__.py"
    if init_file.exists():
        try:
            content = init_file.read_text(errors="replace")
            if len(content.strip()) > 10:  # Non-trivial __init__
                structure = extract_python_structure(init_file)
                if structure:
                    structures["__init__.py"] = structure
        except Exception:
            pass

    return structures


def format_directory_analysis(
    dir_path: Path,
    structures: dict[str, FileStructure],
) -> str:
    """Format the directory analysis into a rich string for the LLM prompt."""
    parts = [f"Directory: {dir_path.name}/"]

    for filename, structure in sorted(structures.items()):
        parts.append(f"\n### {filename} ({structure.line_count} lines)")
        parts.append(structure.to_summary())

    return "\n".join(parts)
