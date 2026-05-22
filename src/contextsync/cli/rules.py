"""ContextSync Rules Scaffolder — Auto-detects frameworks and scaffolds Cursor Rules (.mdc)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

rules_app = typer.Typer(
    name="rules",
    help="📋 Manage and bootstrap Cursor (.mdc) and Claude context rules.",
    no_args_is_help=True,
)
console = Console()


def _find_repo_root() -> Path:
    """Find the git repo root from current directory."""
    from git import Repo, InvalidGitRepositoryError

    try:
        repo = Repo(Path.cwd(), search_parent_directories=True)
        return Path(repo.working_tree_dir)
    except InvalidGitRepositoryError:
        console.print("[red]Error:[/red] Not inside a git repository.")
        raise typer.Exit(1)


# Define premium, best-practice rule templates
TEMPLATES = {
    "typescript": {
        "description": "Triggered when editing TypeScript files to enforce strict type safety and modern syntax.",
        "globs": "**/*.{ts,tsx}",
        "content": """# TypeScript Best Practices

Guidelines for writing safe, performant, and maintainable TypeScript in this project.

## Key Rules

1. **Strict Typing Required**
   - Never use `any` unless absolutely unavoidable (e.g. library integration). Use `unknown` with type guards instead.
   - Enable `strictNullChecks` and explicitly handle `null` / `undefined`.

2. **Interface vs. Type**
   - Use `interface` for public APIs, class/object structures, and anything intended to be extended.
   - Use `type` for unions, intersections, tuples, and utility mappings.

3. **Function Signatures**
   - Always specify explicit return types for public functions and exports.
   - Avoid long parameter lists; destructure parameters with interface signatures instead.

4. **Async & Promise Handling**
   - Always await Promises or handle `.catch()` blocks cleanly.
   - Utilize `Promise.all()` for concurrent operations rather than sequential awaits.
"""
    },
    "react": {
        "description": "Triggered on React code to enforce modern functional components and optimized state hooks.",
        "globs": "**/src/**/*.{js,jsx,ts,tsx}",
        "content": """# React Functional Component Guidelines

Guidelines for building clean, modular React components.

## Component Architecture

1. **Functional First**
   - Only write Functional Components using modern Hooks. Class components are strictly prohibited.
   - Use uppercase naming for component files (e.g., `Button.tsx`).

2. **State & Performance**
   - Keep state local to where it is needed. Do not lift state unnecessarily.
   - Memoize expensive calculations with `useMemo` and callbacks with `useCallback`.
   - Always supply unique, stable `key` props when mapping lists.

3. **Side Effects**
   - Restrict side effects to `useEffect` with exhaustive dependency arrays.
   - Always return clean-up functions in hooks/effects to prevent memory leaks.
"""
    },
    "nextjs": {
        "description": "Triggered in Next.js projects to enforce Server/Client component separation and route optimization.",
        "globs": "**/app/**/*.{ts,tsx,js,jsx}",
        "content": """# Next.js App Router Guidelines

Rules for Next.js React Server Components and App Router architectures.

## Best Practices

1. **Server vs. Client Components**
   - Default to React Server Components (RSC) for maximum speed and zero-JS bundle size.
   - Add `"use client"` at the very top of files ONLY when utilizing state (`useState`), interactivity, browser APIs, or custom hooks.

2. **Data Fetching**
   - Perform data fetching directly inside Server Components using async/await.
   - Secure server credentials and API keys by fetching on the server. Do not expose them to the client.

3. **Server Actions**
   - Define forms/actions using Server Actions for zero-JS progressive enhancement.
   - Use `"use server"` at the top of action files or functions.
"""
    },
    "fastapi": {
        "description": "Triggered on FastAPI Python endpoints to enforce correct async route styles and Pydantic validation.",
        "globs": "**/api/**/*.py",
        "content": """# FastAPI Service Architecture

Rules for creating secure, robust, and lightning-fast Python API routers.

## Design Patterns

1. **Pydantic Validation**
   - Always validate incoming payloads and outbound responses using Pydantic Models.
   - Use `response_model` in route decorators to filter response fields.

2. **Async Route Definitions**
   - Define routes as `async def` only when performing non-blocking operations (e.g. using `httpx`, async db queries).
   - Use standard `def` for heavy blocking synchronous library calculations (FastAPI handles these in a threadpool automatically).

3. **Dependency Injection**
   - Leverage `Depends` for reusable authentication, database sessions, and configuration injection.
"""
    },
    "python": {
        "description": "Triggered on any Python file to enforce clean syntax, type hinting, and robust error checking.",
        "globs": "**/*.py",
        "content": """# Python Guidelines

Universal style and formatting guidelines for Python code in this repository.

## Coding Style

1. **PEP 8 Compliance**
   - Use 4 spaces for indentation.
   - Limit lines to 79/88 characters.
   - Use snake_case for functions/methods and CamelCase for classes.

2. **Type Hints**
   - Enforce explicit type hinting on all function signatures (e.g., `def run(path: Path) -> str`).
   - Use Python 3.10+ union style (e.g., `str | None` instead of `Optional[str]`).

3. **Docstrings**
   - Write descriptive Google-style or Sphinx-style docstrings for all public modules, classes, and methods.
"""
    }
}


def detect_frameworks(repo_root: Path) -> list[str]:
    """Detects technologies and frameworks utilized in the codebase."""
    frameworks = []

    # 1. Package.json inspection (Node/Frontend)
    package_json = repo_root / "package.json"
    if package_json.is_file():
        try:
            content = json.loads(package_json.read_text(encoding="utf-8"))
            deps = {
                **content.get("dependencies", {}),
                **content.get("devDependencies", {})
            }
            if "next" in deps:
                frameworks.append("nextjs")
            if "react" in deps:
                frameworks.append("react")
            if "typescript" in deps:
                frameworks.append("typescript")
        except Exception:
            pass

    # 2. Python backend inspection
    py_files = list(repo_root.rglob("*.py"))
    if py_files:
        frameworks.append("python")
        
        # Check requirements.txt, pyproject.toml
        req_txt = repo_root / "requirements.txt"
        pyproject = repo_root / "pyproject.toml"
        is_fastapi = False
        
        if req_txt.is_file():
            try:
                text = req_txt.read_text(encoding="utf-8")
                if "fastapi" in text.lower():
                    is_fastapi = True
            except Exception:
                pass
                
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8")
                if "fastapi" in text.lower():
                    is_fastapi = True
            except Exception:
                pass
                
        if is_fastapi or any("fastapi" in f.name for f in py_files):
            frameworks.append("fastapi")

    return sorted(list(set(frameworks)))


@rules_app.command()
def scaffold(
    path: Optional[Path] = typer.Argument(None, help="Project root (default: current directory)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing rules if they already exist"),
):
    """Automatically detect frameworks and scaffold Cursor `.mdc` rules.

    Analyzes workspace project manifests and exports high-quality, framework-aware
    Cursor Rules inside the `.cursor/rules/` directory with proper glob triggers.
    """
    repo_root = (path or _find_repo_root()).resolve()
    
    console.print(f"[bold cyan]🔍 Detecting frameworks in codebase at {repo_root}...[/bold cyan]")
    detected = detect_frameworks(repo_root)
    
    if not detected:
        console.print("[yellow]⚠️ No major supported frameworks detected. Scaffolding general Python/TypeScript guidelines...[/yellow]")
        # Default fallback
        detected = ["python", "typescript"]

    # Target directory
    rules_dir = repo_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    scaffolded_count = 0
    for name in detected:
        if name not in TEMPLATES:
            continue
        
        rule_file = rules_dir / f"{name}.mdc"
        if rule_file.exists() and not force:
            console.print(f"  [dim]Skipped {name}.mdc (already exists). Use --force to overwrite.[/dim]")
            continue

        template = TEMPLATES[name]
        
        # Build YAML frontmatter block
        frontmatter = (
            "---\n"
            f"description: {template['description']}\n"
            f"globs: {template['globs']}\n"
            "---\n"
        )
        
        full_content = frontmatter + template["content"]
        rule_file.write_text(full_content, encoding="utf-8")
        scaffolded_count += 1
        console.print(f"  [green]✓[/green] Scaffolded [bold]{name}.mdc[/bold] (globs: `{template['globs']}`)")

    console.print()
    console.print(Panel(
        f"  [bold]Rules Directory:[/bold] .cursor/rules/\n"
        f"  [bold]Rules Scaffolded:[/bold] {scaffolded_count}\n\n"
        "Cursor will now dynamically load these rules automatically when files matching "
        "their globs are active! 🚀",
        title="[bold green]Cursor Rules Scaffolded Successfully! 🎉[/bold green]",
        border_style="green",
    ))
