"""ContextSync CLI — the main entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from contextsync import __version__
from contextsync.config import (
    CONFIG_FILENAME,
    ContextSyncConfig,
    find_config,
    generate_default_config,
    load_config,
)

app = typer.Typer(
    name="contextsync",
    help="🔄 ContextSync — Change Data Capture for AI-assisted codebases.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()


def _load_env(repo_root: Path) -> None:
    """Load .env file for API keys."""
    import os

    for env_path in [repo_root / ".env", Path.cwd() / ".env"]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value and key not in os.environ:
                            os.environ[key] = value
            break


def _find_repo_root() -> Path:
    """Find the git repo root from current directory."""
    from git import Repo, InvalidGitRepositoryError

    try:
        repo = Repo(Path.cwd(), search_parent_directories=True)
        return Path(repo.working_tree_dir)
    except InvalidGitRepositoryError:
        console.print("[red]Error:[/red] Not inside a git repository.")
        raise typer.Exit(1)


@app.callback()
def main():
    """🔄 ContextSync — Keep your AI context files alive."""
    pass


@app.command()
def version():
    """Show ContextSync version."""
    console.print(f"ContextSync v{__version__}")


@app.command()
def init(
    path: Optional[Path] = typer.Argument(None, help="Project root (default: current directory)"),
):
    """Initialize ContextSync in a project.

    Creates .contextsync.yaml and sets up the local database.
    """
    project_root = (path or Path.cwd()).resolve()

    config_path = project_root / CONFIG_FILENAME
    if config_path.exists():
        console.print(f"[yellow]Config already exists:[/yellow] {config_path}")
        overwrite = typer.confirm("Overwrite?", default=False)
        if not overwrite:
            raise typer.Exit(0)

    # Write default config
    config_content = generate_default_config()
    config_path.write_text(config_content)
    console.print(f"[green]✓[/green] Created {CONFIG_FILENAME}")

    # Create .contextsync directory
    cs_dir = project_root / ".contextsync"
    cs_dir.mkdir(exist_ok=True)

    # Initialize database
    from contextsync.models.database import get_engine, init_db
    engine = get_engine(project_root)
    init_db(engine)
    console.print("[green]✓[/green] Initialized database")

    # Create .env file if it doesn't exist
    env_file = project_root / ".env"
    if not env_file.exists():
        env_file.write_text(
            "# ContextSync Environment Variables\n"
            "# Set your LLM API key below\n\n"
            "GEMINI_API_KEY=your-gemini-api-key-here\n"
            "# OPENAI_API_KEY=your-openai-api-key-here\n"
        )
        console.print("[green]✓[/green] Created .env (add your API key here!)")

    # Add .env to .gitignore
    gitignore = project_root / ".gitignore"
    ignore_entries = [".contextsync/", ".env"]
    if gitignore.exists():
        content = gitignore.read_text()
        new_entries = [e for e in ignore_entries if e not in content]
        if new_entries:
            with open(gitignore, "a") as f:
                f.write("\n# ContextSync\n" + "\n".join(new_entries) + "\n")
            console.print("[green]✓[/green] Updated .gitignore")
    else:
        gitignore.write_text("# ContextSync\n" + "\n".join(ignore_entries) + "\n")
        console.print("[green]✓[/green] Created .gitignore")

    console.print()
    console.print(Panel(
        "[bold]Next steps:[/bold]\n"
        "1. Add your API key to [bold].env[/bold]\n"
        "2. Run [bold]contextsync scaffold[/bold] to generate initial CONTEXT.md files\n"
        "3. Run [bold]contextsync run[/bold] after making code changes",
        title="ContextSync initialized! 🎉",
        border_style="green",
    ))


@app.command()
def scaffold(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing CONTEXT.md files"),
):
    """Generate initial CONTEXT.md tree for the project.

    Analyzes the codebase and creates CONTEXT.md files at appropriate
    directory levels based on the configured thresholds.
    """
    import asyncio

    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    # Load .env for API keys
    _load_env(repo_root)

    console.print("[bold]Scaffolding CONTEXT.md tree...[/bold]")

    from contextsync.core.tree_walker import TreeWalker
    from contextsync.llm.litellm_adapter import LiteLLMAdapter

    walker = TreeWalker(repo_root, config)
    tree = walker.build_tree()

    # Find directories needing context
    needs_context = walker.get_directories_needing_context()
    existing = [n for n in tree.values() if n.exists]

    console.print(f"  Existing context files: {len(existing)}")
    console.print(f"  Directories needing context: {len(needs_context)}")

    if not needs_context and not force:
        console.print("[dim]No new CONTEXT.md files needed.[/dim]")
        return

    # Set up LLM (use higher max_tokens for scaffolding — need detailed output)
    model = config.llm.model
    if config.llm.provider == "gemini":
        model = f"gemini/{model}"
    elif config.llm.provider == "ollama":
        model = f"ollama/{model}"

    scaffold_max_tokens = max(config.llm.max_tokens_per_patch, 2000)
    llm = LiteLLMAdapter(model=model, temperature=config.llm.temperature, max_tokens=scaffold_max_tokens)

    async def _scaffold():
        from contextsync.core.code_extractor import extract_directory_structure, format_directory_analysis
        from contextsync.llm.base import ScaffoldRequest

        created = 0
        for dir_path in needs_context:
            context_path = dir_path / config.tree.filename
            if context_path.exists() and not force:
                continue

            # Build directory listing
            listing = []
            try:
                for item in sorted(dir_path.iterdir()):
                    if not item.name.startswith(".") and item.name != "__pycache__":
                        listing.append(item.name)
            except PermissionError:
                continue

            # Get parent context if available
            parent_context = None
            parent_node = walker.find_nearest_context(dir_path.parent)
            if parent_node:
                parent_context = parent_node.content

            # Extract rich structural analysis from code files
            structures = extract_directory_structure(dir_path)
            code_analysis = format_directory_analysis(dir_path, structures)

            # Build summaries dict for the request (backwards compat)
            summaries = {}
            for filename, structure in structures.items():
                summaries[filename] = structure.to_summary()

            request = ScaffoldRequest(
                directory_path=str(dir_path.relative_to(repo_root)),
                directory_listing=f"{chr(10).join(listing)}\n\n--- CODE ANALYSIS ---\n{code_analysis}",
                code_summaries=summaries,
                parent_context=parent_context,
            )

            try:
                result = await llm.generate_scaffold(request)
                context_path.write_text(result.content, encoding="utf-8")
                created += 1
                console.print(
                    f"  [green]✓[/green] Created {context_path.relative_to(repo_root)} "
                    f"({result.tokens_used} tokens, ${result.cost_usd:.4f})"
                )
            except Exception as e:
                console.print(
                    f"  [red]✗[/red] Failed {dir_path.relative_to(repo_root)}: {e}"
                )

        console.print(f"\n[bold green]Created {created} CONTEXT.md files[/bold green]")

    asyncio.run(_scaffold())


@app.command()
def run(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
    from_ref: Optional[str] = typer.Option(None, "--from", help="Starting git ref"),
    to_ref: Optional[str] = typer.Option(None, "--to", help="Ending git ref"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without writing"),
):
    """Run the CDC pipeline on recent changes.

    Analyzes git diff, scores salience, generates patches via LLM,
    validates with QA, and writes updated CONTEXT.md files.
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    from contextsync.core.engine import Engine

    engine = Engine(repo_root, config, dry_run=dry_run)

    if dry_run:
        console.print("[bold yellow]DRY RUN — no files will be modified[/bold yellow]\n")

    result = engine.run(from_ref, to_ref)

    if dry_run and result.context_files_updated > 0:
        console.print(
            f"\n[yellow]Would have updated {result.context_files_updated} CONTEXT.md files.[/yellow]"
        )


@app.command()
def status(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
):
    """Show context health status.

    Displays freshness, coverage, and quality metrics.
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    from contextsync.core.tree_walker import TreeWalker

    walker = TreeWalker(repo_root, config)
    tree = walker.build_tree()

    existing = [n for n in tree.values() if n.exists]
    potential = walker.get_directories_needing_context()

    # Count directories with code
    code_dirs = [p for p, n in tree.items() if not n.exists or n.exists]
    total_eligible = len(existing) + len(potential)
    coverage = (len(existing) / total_eligible * 100) if total_eligible > 0 else 0

    # Build status table
    table = Table(title="ContextSync Status", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Context files", str(len(existing)))
    table.add_row("Directories needing context", str(len(potential)))
    table.add_row("Coverage", f"{coverage:.0f}%")
    table.add_row("Tree depth", str(config.tree.max_depth))
    table.add_row("LLM provider", config.llm.provider)
    table.add_row("LLM model", config.llm.model)
    table.add_row("Security mode", config.security.mode.value)

    console.print(table)

    if existing:
        console.print("\n[bold]Context files:[/bold]")
        for node in sorted(existing, key=lambda n: str(n.path)):
            rel = node.path.relative_to(repo_root)
            size = len(node.content)
            console.print(f"  📄 {rel} ({size} chars)")


@app.command()
def aggregate(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Target surface file"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope to a specific path"),
):
    """Compile context tree into flat files (.cursorrules, AGENTS.md)."""
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    from contextsync.core.aggregator import Aggregator
    from contextsync.core.tree_walker import TreeWalker

    walker = TreeWalker(repo_root, config)
    aggregator = Aggregator(walker, config)

    if scope:
        content = aggregator.aggregate_scoped(repo_root / scope)
        if target:
            (repo_root / target).write_text(content, encoding="utf-8")
            console.print(f"[green]✓[/green] Written scoped context to {target}")
        else:
            console.print(content)
    else:
        written = aggregator.write_surfaces(repo_root)
        for surface in written:
            console.print(f"[green]✓[/green] Written {surface}")


@app.command()
def mcp_serve():
    """Start the MCP server for AI IDE integration.

    Exposes ContextSync tools via the Model Context Protocol (STDIO transport).
    Connect from Cursor, Claude Code, or any MCP-compatible client.
    """
    from contextsync.mcp_server import run_mcp_server

    run_mcp_server()

@app.command()
def watch(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
    debounce: float = typer.Option(2.0, help="Debounce window in seconds (default: 2.0)"),
):
    """Watch for file changes and auto-update context.
    
    Runs continuously, monitoring the codebase for file saves.
    When a change is detected, it runs the CDC pipeline automatically
    after a short debounce window.
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))
    
    from contextsync.core.watcher import ContextSyncWatcher
    
    watcher = ContextSyncWatcher(repo_root, config, debounce_seconds=debounce)
    watcher.start()


@app.command()
def validate(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
):
    """Run Cross-Document Validation manually.
    
    Checks the context tree for parent-child drift, missing bidirectional
    lateral links, and stale entity references.
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))
    
    from contextsync.core.cross_doc_validator import CrossDocValidator
    from contextsync.core.tree_walker import TreeWalker
    
    console.print(f"[bold]Validating context tree at {repo_root}...[/bold]")
    walker = TreeWalker(repo_root, config)
    validator = CrossDocValidator(repo_root, walker)
    report = validator.validate()
    
    console.print(f"\n[bold]Validation Report[/bold] (Health Score: {report.health_score*100:.1f}%)")
    console.print(f"Nodes checked: {report.total_nodes_checked}")
    
    if not report.issues:
        console.print("\n[green]✅ Tree is fully consistent. No issues found.[/green]")
        return
        
    console.print(f"\n[bold yellow]Found {len(report.issues)} issues:[/bold yellow]\n")
    for issue in report.issues:
        color = "red" if issue.severity == "error" else "yellow"
        icon = "❌" if issue.severity == "error" else "⚠️"
        rel_path = issue.node_path.relative_to(repo_root)
        console.print(f"[{color}]{icon} {rel_path}[/{color}]: {issue.message}")


if __name__ == "__main__":
    app()
