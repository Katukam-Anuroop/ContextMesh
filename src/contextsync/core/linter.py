"""ContextSync Linter — Deterministic validation for AI context files and Cursor rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from contextsync.config import ContextSyncConfig, load_config, find_config
from contextsync.core.tree_walker import TreeWalker


@dataclass
class LintIssue:
    file_path: Path
    line_number: Optional[int]
    severity: str  # "error" | "warning"
    issue_type: str  # "stale_reference" | "missing_frontmatter" | "read_error"
    message: str
    context: str = ""


@dataclass
class LintReport:
    issues: list[LintIssue]
    total_files_checked: int
    context_coverage_index: float
    health_score: float
    total_rules: int
    total_stale: int
    eligible_dirs: int
    covered_dirs: int


def extract_defined_entities(file_path: Path) -> tuple[set[str], set[str], set[str]]:
    """Extract (classes, functions/methods, constants) from a file.

    Uses language-specific regexes for extreme performance and zero dependencies.
    """
    classes = set()
    functions = set()
    constants = set()

    suffix = file_path.suffix.lower()
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return classes, functions, constants

    lines = content.splitlines()

    if suffix == ".py":
        for line in lines:
            stripped = line.strip()
            # Class: class ClassName(Base):
            cls_match = re.match(r"^class\s+(\w+)", stripped)
            if cls_match:
                classes.add(cls_match.group(1))
            # Function: def func_name(args): or async def func_name(args):
            func_match = re.match(r"^(?:async\s+)?def\s+(\w+)", stripped)
            if func_match:
                functions.add(func_match.group(1))
            # Constant: UPPER_CASE =
            const_match = re.match(r"^([A-Z][A-Z0-9_]+)\s*=", stripped)
            if const_match:
                constants.add(const_match.group(1))
    elif suffix in {".js", ".ts", ".jsx", ".tsx"}:
        for line in lines:
            stripped = line.strip()
            # Class: class ClassName
            cls_match = re.search(r"\bclass\s+(\w+)", stripped)
            if cls_match:
                classes.add(cls_match.group(1))
            # Function: function funcName or export function funcName
            func_match = re.search(r"\bfunction\s+(\w+)", stripped)
            if func_match:
                functions.add(func_match.group(1))
            # Arrow function: const funcName = ...
            arrow_match = re.match(r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=]+)\s*=>", stripped)
            if arrow_match:
                functions.add(arrow_match.group(1))
            # Constants
            const_match = re.match(r"^(?:export\s+)?const\s+([A-Z][A-Z0-9_]+)\s*=", stripped)
            if const_match:
                constants.add(const_match.group(1))
    elif suffix == ".go":
        for line in lines:
            stripped = line.strip()
            # Go structs (like classes): type StructName struct
            struct_match = re.match(r"^type\s+(\w+)\s+struct", stripped)
            if struct_match:
                classes.add(struct_match.group(1))
            # Go functions: func funcName(...) or func (r *Receiver) funcName(...)
            func_match = re.match(r"^func\s+(?:\([^)]*\)\s+)?(\w+)", stripped)
            if func_match:
                functions.add(func_match.group(1))
    elif suffix == ".rs":
        for line in lines:
            stripped = line.strip()
            # Rust structs/enums (like classes)
            struct_match = re.match(r"^(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)", stripped)
            if struct_match:
                classes.add(struct_match.group(1))
            # Rust functions
            func_match = re.match(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", stripped)
            if func_match:
                functions.add(func_match.group(1))

    return classes, functions, constants


class ContextLinter:
    """Deterministic, lightning-fast context and Cursor rules linter."""

    def __init__(self, repo_root: Path, config: ContextSyncConfig):
        self.repo_root = repo_root.resolve()
        self.config = config
        self.skip_dirs = {
            ".git", ".contextsync", "__pycache__", "node_modules",
            ".venv", "venv", ".env", ".tox", ".mypy_cache",
            ".pytest_cache", ".ruff_cache", "dist", "build",
            ".next", ".nuxt", "coverage", "htmlcov", "eggs", "*.egg-info",
        }
        self.code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}

    def run_scan(self) -> LintReport:
        """Scan codebase, collect AST, compile rule references, and output report."""
        all_classes: set[str] = set()
        all_functions: set[str] = set()
        all_constants: set[str] = set()
        all_files: set[str] = set()
        all_filenames: set[str] = set()

        eligible_dirs_set: set[Path] = set()
        covered_dirs_set: set[Path] = set()

        # Step 1: Walk repository to collect codebase AST and file paths
        self._collect_ast_and_files(
            self.repo_root,
            all_classes,
            all_functions,
            all_constants,
            all_files,
            all_filenames,
            eligible_dirs_set,
        )

        # Step 2: Discover and check all rule/context files
        rule_files = self._find_rule_files()
        
        # Track covered directories
        for r_file in rule_files:
            # If CONTEXT.md, it covers its directory and nested ones
            if r_file.name == "CONTEXT.md":
                covered_dirs_set.add(r_file.parent)
            elif r_file.suffix == ".mdc":
                # For MDC, parse frontmatter to see if it matches globs
                # For simplicity, if we have an MDC file, let's treat the folders matching its path/globs as covered.
                # Since .cursor/rules/*.mdc can match anywhere, we can parse its frontmatter to get target directories.
                pass

        # Step 3: Run lint rules on each rule file
        issues: list[LintIssue] = []
        for r_file in rule_files:
            file_issues = self._check_rule_file(
                r_file,
                all_classes,
                all_functions,
                all_constants,
                all_files,
                all_filenames,
            )
            issues.extend(file_issues)

        # Compute Context Coverage Index (CCI)
        eligible_count = len(eligible_dirs_set)
        # If CONTEXT.md exists in a dir, or its parent has one, it is covered
        covered_count = 0
        for d in eligible_dirs_set:
            is_covered = False
            current = d
            while current >= self.repo_root:
                if current in covered_dirs_set:
                    is_covered = True
                    break
                current = current.parent
            if is_covered:
                covered_count += 1

        cci = (covered_count / eligible_count * 100.0) if eligible_count > 0 else 100.0

        # Compute overall Health Score
        # Start at 100%, deduct points for issues (2% for warnings, 5% for errors)
        total_deduction = 0.0
        total_stale = 0
        for issue in issues:
            if issue.issue_type == "stale_reference":
                total_stale += 1
            if issue.severity == "error":
                total_deduction += 5.0
            else:
                total_deduction += 2.0

        health_score = max(0.0, 100.0 - total_deduction)

        # Weigh in Coverage Index to health score: 70% AST references health + 30% coverage index
        weighted_health = (health_score * 0.70) + (cci * 0.30)

        return LintReport(
            issues=issues,
            total_files_checked=len(rule_files),
            context_coverage_index=cci,
            health_score=weighted_health,
            total_rules=len(rule_files),
            total_stale=total_stale,
            eligible_dirs=eligible_count,
            covered_dirs=covered_count,
        )

    def _collect_ast_and_files(
        self,
        current_dir: Path,
        all_classes: set[str],
        all_functions: set[str],
        all_constants: set[str],
        all_files: set[str],
        all_filenames: set[str],
        eligible_dirs: set[Path],
    ) -> None:
        """Recursively scans repository directories, extracting AST structure."""
        try:
            items = list(current_dir.iterdir())
        except (PermissionError, FileNotFoundError):
            return

        code_files_in_dir = []
        for item in sorted(items):
            if item.is_dir():
                if item.name not in self.skip_dirs and not item.name.startswith("."):
                    self._collect_ast_and_files(
                        item,
                        all_classes,
                        all_functions,
                        all_constants,
                        all_files,
                        all_filenames,
                        eligible_dirs,
                    )
            elif item.is_file():
                if item.suffix.lower() in self.code_extensions and item.name != "__init__.py":
                    code_files_in_dir.append(item)
                    rel_path = str(item.relative_to(self.repo_root))
                    all_files.add(rel_path)
                    all_filenames.add(item.name)

                    # Extract defined AST entities
                    classes, functions, constants = extract_defined_entities(item)
                    all_classes.update(classes)
                    all_functions.update(functions)
                    all_constants.update(constants)

        # If directory has >= threshold of files, it requires context
        threshold = self.config.tree.min_files_for_context
        if len(code_files_in_dir) >= threshold:
            eligible_dirs.add(current_dir)

    def _find_rule_files(self) -> list[Path]:
        """Find all context rules (.cursor/rules/*.mdc, CONTEXT.md, CLAUDE.md)."""
        rules = []

        # 1. Walk for CONTEXT.md
        # Use simple recursive glob or TreeWalker
        walker = TreeWalker(self.repo_root, self.config)
        tree = walker.build_tree()
        for node in tree.values():
            if node.exists:
                rules.append(node.path)

        # 2. Find .cursor/rules/*.mdc
        cursor_rules_dir = self.repo_root / ".cursor" / "rules"
        if cursor_rules_dir.is_dir():
            try:
                for f in cursor_rules_dir.glob("*.mdc"):
                    if f.is_file():
                        rules.append(f)
            except Exception:
                pass

        # 3. Look for CLAUDE.md / .cursorrules in root
        for root_rule in ["CLAUDE.md", ".cursorrules", "GEMINI.md"]:
            p = self.repo_root / root_rule
            if p.is_file() and p not in rules:
                rules.append(p)

        return sorted(list(set(rules)))

    def _check_rule_file(
        self,
        file_path: Path,
        all_classes: set[str],
        all_functions: set[str],
        all_constants: set[str],
        all_files: set[str],
        all_filenames: set[str],
    ) -> list[LintIssue]:
        """Verify backticked code symbols inside a specific rule file."""
        issues: list[LintIssue] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            issues.append(
                LintIssue(
                    file_path=file_path,
                    line_number=None,
                    severity="error",
                    issue_type="read_error",
                    message=f"Failed to read file: {e}",
                )
            )
            return issues

        body = content
        frontmatter = {}
        if file_path.suffix == ".mdc":
            # Check frontmatter block
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if match:
                fm_text = match.group(1)
                body = content[match.end():]
                for line in fm_text.splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        frontmatter[k.strip()] = v.strip()

                if "globs" not in frontmatter:
                    issues.append(
                        LintIssue(
                            file_path=file_path,
                            line_number=1,
                            severity="warning",
                            issue_type="missing_frontmatter",
                            message="Cursor rule .mdc file is missing the required 'globs' frontmatter field.",
                            context=fm_text,
                        )
                    )

        lines = body.splitlines()
        ignore_words = {
            # Languages and formats
            "python", "javascript", "typescript", "json", "yaml", "bash", "sh", "html", "css", "sql", "markdown", "md",
            # Python builtins and type hints
            "str", "int", "float", "bool", "list", "dict", "set", "tuple", "any", "Any", "Optional", "Union", "None", "True", "False",
            "self", "args", "kwargs", "len", "print", "range", "open", "read", "write", "close", "sum", "max", "min", "abs", "round",
            # Common keywords
            "def", "class", "async", "await", "import", "from", "return", "pass", "lambda", "with", "as", "try", "except", "finally",
            "raise", "assert", "yield", "global", "nonlocal", "del",
            # Frameworks and libraries (FastAPI, Pydantic, HTTP, etc.)
            "fastapi", "Depends", "response_model", "httpx", "requests", "router", "app", "status", "Header", "Cookie", "Body",
            "Query", "Path", "Form", "File", "UploadFile", "BackgroundTasks", "APIRouter", "FastAPI", "BaseModel", "Field",
            "sqlalchemy", "Pydantic", "pydantic",
            # HTTP Methods
            "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "get", "post", "put", "delete", "patch", "options", "head",
            # General terms
            "__init__", "cwd", "path", "file", "dir", "v1", "v2", "true", "false", "null", "undefined", "readme", "doc", "docs"
        }

        # Match backticked items: e.g. `ClassName`, `my_func()`, `dir/file.py`
        for idx, line in enumerate(lines, 1):
            backticks = re.findall(r"`([^`\n]+)`", line)
            for term in backticks:
                term_clean = term.strip()
                if not term_clean or term_clean in ignore_words:
                    continue

                if term_clean.startswith("```") or len(term_clean) > 80:
                    continue

                # Strip trailing () or leading @ for comparison
                func_name = term_clean
                if func_name.endswith("()"):
                    func_name = func_name[:-2]
                if func_name.startswith("@"):
                    func_name = func_name[1:]

                # 1. File path reference check
                is_file_like = (
                    "." in term_clean
                    and not term_clean.startswith(".")
                    and not re.search(r"\s", term_clean)
                    and term_clean.split(".")[-1].lower() in {
                        "py", "js", "ts", "jsx", "tsx", "go", "rs", "java", "yml", "yaml", "json", "md", "toml", "css", "html"
                    }
                )

                if is_file_like:
                    found_file = False
                    if term_clean in all_files:
                        found_file = True
                    else:
                        filename = Path(term_clean).name
                        if filename in all_filenames:
                            found_file = True
                    
                    if not found_file:
                        issues.append(
                            LintIssue(
                                file_path=file_path,
                                line_number=idx,
                                severity="error",
                                issue_type="stale_reference",
                                message=f"References file '{term_clean}' which does not exist in the codebase.",
                                context=line.strip(),
                            )
                        )
                    continue

                # 2. Class check (Capitalized, alphanumeric)
                is_class_like = re.match(r"^[A-Z][a-zA-Z0-9_]*$", func_name)
                if is_class_like:
                    if func_name not in all_classes:
                        issues.append(
                            LintIssue(
                                file_path=file_path,
                                line_number=idx,
                                severity="warning",
                                issue_type="stale_reference",
                                message=f"References class '{func_name}' which is not defined in the codebase.",
                                context=line.strip(),
                            )
                        )
                    continue

                # 3. Function check (snake_case/camelCase or ends in ())
                is_func_like = re.match(r"^[a-z_][a-zA-Z0-9_]*$", func_name) or term_clean.endswith("()")
                if is_func_like:
                    if func_name not in all_functions:
                        if func_name in {
                            "len", "print", "range", "list", "dict", "set", "open", "read", "write", "close", "sum", "max",
                            "min", "abs", "round", "enumerate", "zip", "super", "next", "iter", "all", "any", "map", "filter"
                        }:
                            continue
                        issues.append(
                            LintIssue(
                                file_path=file_path,
                                line_number=idx,
                                severity="warning",
                                issue_type="stale_reference",
                                message=f"References function/method '{func_name}' which is not defined in the codebase.",
                                context=line.strip(),
                            )
                        )
                    continue

                # 4. Constant check (UPPER_CASE)
                is_const_like = re.match(r"^[A-Z][A-Z0-9_]+$", term_clean)
                if is_const_like:
                    if term_clean not in all_constants:
                        issues.append(
                            LintIssue(
                                file_path=file_path,
                                line_number=idx,
                                severity="warning",
                                issue_type="stale_reference",
                                message=f"References constant '{term_clean}' which is not defined in the codebase.",
                                context=line.strip(),
                            )
                        )
                    continue

        return issues
