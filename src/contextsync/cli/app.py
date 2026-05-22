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
    name="contextmesh",
    help="🔄 ContextSync — Change Data Capture for AI-assisted codebases.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()

from contextsync.cli.rules import rules_app
from contextsync.cli.hooks import hooks_app
app.add_typer(rules_app)
app.add_typer(hooks_app)


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
    depth: str = typer.Option("enhanced", "--depth", "-d", help="Context depth: basic | enhanced | deep"),
    local_only: bool = typer.Option(False, "--local", "-l", help="Run in zero-API-key local mode (uses AST/static parsing, no API key required)"),
):
    """Generate initial CONTEXT.md tree for the project.

    Analyzes the codebase and creates CONTEXT.md files at appropriate
    directory levels based on the configured thresholds.

    Use --depth to control context richness:
      basic    = structural snapshot only (Level 1)
      enhanced = + Gotchas, Invariants, Evolution, Rejected Approaches (Level 2+)
      deep     = enhanced + full git history mining
    """
    import asyncio

    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    # Override depth from CLI flag
    config.enhanced.depth = depth
    if depth == "basic":
        config.enhanced.enabled = False

    # Load .env for API keys
    _load_env(repo_root)

    # Autodetect if we should run in local-only mode
    import os
    has_api_key = any(os.environ.get(k) for k in ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
    is_local_provider = config.llm.provider in ["ollama", "local"]
    
    run_local = local_only or (not has_api_key and not is_local_provider)
    
    if run_local:
        console.print("[cyan]ℹ Running in zero-API-key local scaffolding mode (deterministic AST parsing).[/cyan]")

    depth_label = {"basic": "Level 1 (structural)", "enhanced": "Level 2+ (enhanced)", "deep": "Level 2+ (deep)"}
    console.print(f"[bold]Scaffolding CONTEXT.md tree — {depth_label.get(depth, depth)}...[/bold]")

    from contextsync.core.tree_walker import TreeWalker

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

    # Set up LLM if not running in local mode
    llm = None
    if not run_local:
        model = config.llm.model
        if config.llm.provider == "gemini":
            model = f"gemini/{model}"
        elif config.llm.provider == "ollama":
            model = f"ollama/{model}"

        scaffold_max_tokens = max(config.llm.max_tokens_per_patch, 2000)
        try:
            from contextsync.llm.litellm_adapter import LiteLLMAdapter
            llm = LiteLLMAdapter(
                model=model,
                temperature=config.llm.temperature,
                max_tokens=scaffold_max_tokens,
                api_base=config.llm.api_base,
            )
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to initialize LLM: {e}. Falling back to deterministic local mode.[/yellow]")
            run_local = True

    # Initialize miners for Level 2+
    git_miner = None
    invariant_ext = None
    if config.enhanced.enabled:
        from contextsync.core.git_miner import GitMiner
        from contextsync.core.invariant_extractor import InvariantExtractor
        git_miner = GitMiner(repo_root)
        invariant_ext = InvariantExtractor(repo_root)
        console.print("  [cyan]Level 2+ miners active:[/cyan] git_miner, invariant_extractor")

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

            # Mine enhanced data for Level 2+
            evolution_data = None
            complexity_signals = None
            invariant_hints = None
            gotcha_hints = None

            if config.enhanced.enabled and git_miner:
                from contextsync.core.git_miner import (
                    format_complexity_for_llm,
                    format_evolution_for_llm,
                    format_gotcha_hints_for_llm,
                )

                if config.enhanced.generate_evolution:
                    evo = git_miner.mine_evolution(
                        dir_path,
                        max_commits=config.enhanced.evolution_max_commits,
                        max_days=config.enhanced.evolution_max_days,
                    )
                    if evo.total_commits > 0:
                        evolution_data = format_evolution_for_llm(evo)

                if config.enhanced.generate_complexity_signals:
                    signals = git_miner.mine_complexity_signals(dir_path)
                    complexity_signals = format_complexity_for_llm(signals)

                if config.enhanced.generate_gotchas:
                    hints = git_miner.mine_gotcha_hints(dir_path)
                    if hints:
                        gotcha_hints = format_gotcha_hints_for_llm(hints)

            if config.enhanced.enabled and invariant_ext:
                from contextsync.core.invariant_extractor import format_invariants_for_llm

                if config.enhanced.generate_invariants:
                    invs = invariant_ext.extract(dir_path)
                    if invs:
                        invariant_hints = format_invariants_for_llm(invs)

            if run_local:
                # Generate high-fidelity deterministic layout completely locally
                rel_dir = dir_path.relative_to(repo_root)
                content_lines = [
                    f"# Context: {dir_path.name}",
                    "",
                    "## Purpose",
                    f"Architectural context and structural map for the `{rel_dir}` module.",
                    "",
                    "## Key Components",
                    "",
                ]
                for filename, structure in sorted(structures.items()):
                    content_lines.append(f"### `{filename}`")
                    if structure.classes:
                        classes_list = ", ".join([f"`{c.name}`" for c in sorted(structure.classes, key=lambda x: x.name)])
                        content_lines.append(f"- **Classes**: {classes_list}")
                    if structure.functions:
                        funcs_list = ", ".join([f"`{f.name}`" for f in sorted(structure.functions, key=lambda x: x.name)])
                        content_lines.append(f"- **Functions**: {funcs_list}")
                    if structure.constants:
                        consts_list = ", ".join([f"`{c}`" for c in sorted(structure.constants)])
                        content_lines.append(f"- **Constants**: {consts_list}")
                    content_lines.append("")

                if gotcha_hints or invariant_hints or evolution_data:
                    content_lines.extend([
                        "## Enhanced Context (Local Mining)",
                        "",
                    ])
                    if gotcha_hints:
                        content_lines.extend([
                            "### ⚠️ Potential Gotchas",
                            gotcha_hints,
                            "",
                        ])
                    if invariant_hints:
                        content_lines.extend([
                            "### 🔒 Extracted Invariants",
                            invariant_hints,
                            "",
                        ])
                    if evolution_data:
                        content_lines.extend([
                            "### 📈 Git Evolution & Churn",
                            evolution_data,
                            "",
                        ])

                content_lines.extend([
                    "## Guided Rules & Tribal Knowledge",
                    "",
                    "> [!NOTE]",
                    "> The sections below can be populated manually or automatically updated by your AI coding assistant during active chat sessions.",
                    "",
                    "### Gotchas",
                    "- *Add known edge cases, performance constraints, or pitfalls for this module here.*",
                    "",
                    "### Invariants",
                    "- *Add architectural invariants or patterns that must always be respected here.*",
                    "",
                    "### Rejected Approaches",
                    "- *Add historical approaches that were tried but rejected and why.*",
                    "",
                ])

                result_content = "\n".join(content_lines)
                context_path.write_text(result_content, encoding="utf-8")
                created += 1
                console.print(f"  [green]✓[/green] Created {context_path.relative_to(repo_root)} (Deterministic Local Scaffolder)")
                continue

            request = ScaffoldRequest(
                directory_path=str(dir_path.relative_to(repo_root)),
                directory_listing=f"{chr(10).join(listing)}\n\n--- CODE ANALYSIS ---\n{code_analysis}",
                code_summaries=summaries,
                parent_context=parent_context,
                evolution_data=evolution_data,
                complexity_signals=complexity_signals,
                invariant_hints=invariant_hints,
                gotcha_hints=gotcha_hints,
                context_depth=depth,
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
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Single target surface file"),
    targets: Optional[str] = typer.Option(None, "--targets", help="Target set: 'all' or 'configured'"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope to a specific path"),
    setup: bool = typer.Option(False, "--setup", help="Interactive setup — choose which AI tools to generate for"),
    cursor_v2: bool = typer.Option(False, "--cursor-v2", help="Generate .cursor/rules/*.mdc directory-scoped rules"),
):
    """Compile context tree into flat files for AI tools.

    Supports all major AI coding tools:
      .cursorrules, CLAUDE.md, GEMINI.md, AGENTS.md,
      copilot-instructions.md, .windsurfrules, .clinerules

    Examples:
      contextsync aggregate                    # Write configured targets
      contextsync aggregate --targets all      # Write ALL 7 formats
      contextsync aggregate --setup            # Interactive: choose your tools
      contextsync aggregate --cursor-v2        # Generate .cursor/rules/*.mdc
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    from contextsync.config import ALL_AGGREGATOR_TARGETS, AggregatorTarget
    from contextsync.core.aggregator import Aggregator
    from contextsync.core.tree_walker import TreeWalker

    walker = TreeWalker(repo_root, config)
    aggregator = Aggregator(walker, config)

    # ── Interactive setup mode ────────────────────────────────────────────
    if setup:
        console.print("\n[bold cyan]ContextSync — Universal Delivery Setup[/bold cyan]")
        console.print("Which AI tools does your team use? Select targets to generate:\n")

        tool_names = {
            ".cursorrules": "Cursor",
            "CLAUDE.md": "Claude Code",
            "GEMINI.md": "Gemini CLI",
            "AGENTS.md": "OpenAI Codex / Generic",
            ".github/copilot-instructions.md": "GitHub Copilot",
            ".windsurfrules": "Windsurf",
            ".clinerules": "Cline",
        }

        selected: list[AggregatorTarget] = []
        for t in ALL_AGGREGATOR_TARGETS:
            name = tool_names.get(t.path, t.path)
            if typer.confirm(f"  Generate {t.path} ({name})?", default=True):
                selected.append(t)

        cursor_v2_opt = typer.confirm("\n  Generate .cursor/rules/*.mdc (directory-scoped rules)?", default=False)

        if not selected and not cursor_v2_opt:
            console.print("[yellow]No targets selected.[/yellow]")
            return

        # Write selected targets
        for t in selected:
            output = aggregator.generate_for_target(t)
            target_path = repo_root / t.path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(output, encoding="utf-8")
            lines = output.count("\n")
            console.print(f"  [green]✓[/green] {t.path} ({lines} lines, max {t.max_lines})")

        if cursor_v2_opt:
            mdc_files = aggregator.write_cursor_v2_rules(repo_root)
            for f in mdc_files:
                console.print(f"  [green]✓[/green] {f}")

        console.print(f"\n[bold green]Generated {len(selected) + (len(mdc_files) if cursor_v2_opt else 0)} context surfaces[/bold green]")
        return

    # ── Scoped output ─────────────────────────────────────────────────────
    if scope:
        content = aggregator.aggregate_scoped(repo_root / scope)
        if target:
            (repo_root / target).write_text(content, encoding="utf-8")
            console.print(f"[green]✓[/green] Written scoped context to {target}")
        else:
            console.print(content)
        return

    # ── Single target ─────────────────────────────────────────────────────
    if target:
        # Find matching target config or create a default
        matching = None
        for t in ALL_AGGREGATOR_TARGETS:
            if t.path == target:
                matching = t
                break
        if not matching:
            matching = AggregatorTarget(path=target, max_lines=500)

        output = aggregator.generate_for_target(matching)
        target_path = repo_root / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(output, encoding="utf-8")
        console.print(f"[green]✓[/green] Written {target} ({output.count(chr(10))} lines)")
        return

    # ── All targets ───────────────────────────────────────────────────────
    if targets == "all":
        console.print("[bold]Generating ALL AI tool context surfaces...[/bold]")
        written = aggregator.write_all_surfaces(repo_root)
        for surface in written:
            console.print(f"  [green]✓[/green] {surface}")
        console.print(f"\n[bold green]Generated {len(written)} context surfaces[/bold green]")
    else:
        # Default: write configured targets
        written = aggregator.write_surfaces(repo_root)
        for surface in written:
            console.print(f"  [green]✓[/green] {surface}")

    # ── Cursor v2 directory rules ─────────────────────────────────────────
    if cursor_v2:
        console.print("\n[bold]Generating Cursor v2 directory-scoped rules...[/bold]")
        mdc_files = aggregator.write_cursor_v2_rules(repo_root)
        for f in mdc_files:
            console.print(f"  [green]✓[/green] {f}")



@app.command()
def bundle(
    target: str = typer.Argument(".", help="Target directory for active deep inspection"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Project root (default: auto-detected)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="File to write XML output to"),
):
    """Generate a progressive context XML bundle.
    
    Deep-inspects the active 'target' directory for full source code,
    but compresses all other repository modules into their lightweight CONTEXT.md summaries.
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))
    
    from contextsync.core.bundler import ProgressiveBundler
    
    bundler = ProgressiveBundler(repo_root, config)
    xml_payload = bundler.generate_bundle(target)
    
    if output:
        output.write_text(xml_payload, encoding="utf-8")
        console.print(f"[green]✓[/green] Progressive context bundle saved to {output}")
    else:
        # We use standard print so users can pipe it directly (e.g. into pbcopy)
        print(xml_payload)


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
def link(
    target: str = typer.Argument(".", help="Target directory to map locally"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Project root"),
):
    """Auto-discover lateral dependency arrows using AST analysis.
    
    Reads the Python source code in the target directory and resolves out-bound 
    package imports into physical local repository directory targets.
    """
    repo_root = (path or _find_repo_root()).resolve()
    target_abs = repo_root / target
    
    from contextsync.core.dependency_graph import PythonDependencyExtractor
    import os
    
    extractor = PythonDependencyExtractor(repo_root)
    deps = extractor.extract_dependencies(target_abs)
    
    if not deps:
        console.print(f"[yellow]No external lateral dependencies found for {target}[/yellow]")
        return
        
    console.print(f"[bold]Discovered the following lateral dependencies (copy these to CONTEXT.md):[/bold]")
    for d in deps:
        rel = os.path.relpath(d, target_abs)
        console.print(f"  → {rel}")


@app.command()
def visualize(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Custom path to save visualizer HTML"),
):
    """Generate and open an interactive local graph visualizer in your browser.

    Compiles the codebase AST trees and context coverage into a single standalone HTML 
    file that is served completely offline from your local disk.
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    from contextsync.core.visualizer import ContextVisualizer

    console.print("[bold cyan]🔄 Compiling codebase context visualizer...[/bold cyan]")
    
    visualizer = ContextVisualizer(repo_root, config)
    try:
        final_path = visualizer.export_and_open(output)
        console.print(f"[bold green]✓[/bold green] Visualizer successfully saved to {final_path}")
        console.print("[green]🚀 Launching interactive visualizer in your browser automatically...[/green]")
    except Exception as e:
        console.print(f"[bold red]✗[/bold red] Failed to generate visualizer: {e}")
        raise typer.Exit(1)


@app.command()
def lint(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
    fail_on_stale: bool = typer.Option(False, "--fail-on-stale", help="Fail with exit code 1 if any stale references or errors are found"),
    fail_on_warning: bool = typer.Option(False, "--fail-on-warning", help="Fail with exit code 1 if any warning is found"),
):
    """Run context rule auditing (stale AST links and coverage gaps)."""
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))

    from contextsync.core.linter import ContextLinter

    console.print(f"[bold cyan]🔍 Auditing AI rules & context at {repo_root}...[/bold cyan]")
    linter = ContextLinter(repo_root, config)
    report = linter.run_scan()

    # Display report header with overall health and CCI
    health_color = "green" if report.health_score >= 90 else "yellow" if report.health_score >= 75 else "red"
    cci_color = "green" if report.context_coverage_index >= 80 else "yellow" if report.context_coverage_index >= 50 else "red"

    console.print()
    console.print(Panel(
        f"  [bold]Health Score:[/bold] [{health_color}]{report.health_score:.1f}%[/{health_color}]\n"
        f"  [bold]Context Coverage Index (CCI):[/bold] [{cci_color}]{report.context_coverage_index:.1f}%[/{cci_color}] ({report.covered_dirs}/{report.eligible_dirs} folders)\n"
        f"  [bold]Rules scanned:[/bold] {report.total_rules} | [bold yellow]Stale links:[/bold yellow] {report.total_stale}",
        title="[bold]ContextSync Audit Report[/bold]",
        border_style=health_color,
    ))

    if not report.issues:
        console.print("\n[bold green]✨ Excellent! No stale rule references or coverage issues found.[/bold green]")
        return

    # Print issues table
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Location", style="dim", width=40)
    table.add_column("Severity", justify="center", width=12)
    table.add_column("Type", width=20)
    table.add_column("Issue Details")

    for issue in report.issues:
        rel_file = issue.file_path.relative_to(repo_root)
        loc = f"{rel_file}:{issue.line_number}" if issue.line_number else str(rel_file)
        
        sev_str = "[red]ERROR[/red]" if issue.severity == "error" else "[yellow]WARN[/yellow]"
        type_str = f"[cyan]{issue.issue_type}[/cyan]"
        
        msg_details = issue.message
        if issue.context:
            msg_details += f"\n[dim]> {issue.context}[/dim]"
            
        table.add_row(loc, sev_str, type_str, msg_details)

    console.print()
    console.print(table)
    console.print()

    # Determine if we should fail
    has_errors = any(i.severity == "error" for i in report.issues)
    has_warnings = any(i.severity == "warning" for i in report.issues)

    if fail_on_stale and (has_errors or report.total_stale > 0):
        console.print("[bold red]🛑 Failing due to stale references or errors.[/bold red]")
        raise typer.Exit(1)
    
    if fail_on_warning and (has_errors or has_warnings):
        console.print("[bold red]🛑 Failing due to warnings or errors.[/bold red]")
        raise typer.Exit(1)


@app.command()
def validate(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
    ci: bool = typer.Option(False, "--ci", help="Output GitHub Actions formatted annotations"),
    changed_only: bool = typer.Option(False, "--changed-only", help="Only validate files modified in git diff"),
):
    """Run Cross-Document Validation manually.
    
    Checks the context tree for parent-child drift, missing bidirectional
    lateral links, and stale entity references.
    """
    repo_root = (path or _find_repo_root()).resolve()
    config = load_config(find_config(repo_root))
    
    from contextsync.core.cross_doc_validator import CrossDocValidator
    from contextsync.core.tree_walker import TreeWalker
    
    if not ci:
        console.print(f"[bold]Validating context tree at {repo_root}...[/bold]")
        
    walker = TreeWalker(repo_root, config)
    validator = CrossDocValidator(repo_root, walker)
    report = validator.validate(changed_only=changed_only)
    
    if ci:
        for issue in report.issues:
            severity = "error" if issue.severity == "error" else "warning"
            rel_path = issue.node_path.relative_to(repo_root)
            print(f"::{severity} file={rel_path}::{issue.message}")
        
        if report.errors:
            raise typer.Exit(1)
        return
        
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
        
    if report.errors:
        raise typer.Exit(1)


@app.command()
def init_ci(
    path: Optional[Path] = typer.Argument(None, help="Project root"),
):
    """Bootstrap ContextMesh GitHub Actions CI configuration.
    
    Generates a .github/workflows/contextmesh-pr.yml file to automatically
    run ContextMesh architectural validation on all Pull Requests and 
    leave inline GitHub annotations.
    """
    repo_root = (path or _find_repo_root()).resolve()
    workflows_dir = repo_root / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    
    workflow_path = workflows_dir / "contextmesh-pr.yml"
    
    workflow_content = """name: ContextMesh PR Validation
on: [pull_request]

jobs:
  validate-context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install ContextMesh CLI
        run: pip install contextmesh-cli

      - name: Validate Architectural Context Drift
        run: contextmesh validate --ci --changed-only
"""
    
    if workflow_path.exists():
        console.print(f"[yellow]⚠️ Workflow already exists at {workflow_path.relative_to(repo_root)}[/yellow]")
        return
        
    workflow_path.write_text(workflow_content, encoding="utf-8")
    console.print(f"[green]✓[/green] Injected CI workflow into {workflow_path.relative_to(repo_root)}")
    console.print("ContextMesh will now natively gate your PRs against architectural drift!")


if __name__ == "__main__":
    app()

