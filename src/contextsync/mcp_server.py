"""ContextSync MCP Server — Model Context Protocol integration.

Exposes ContextSync's context tree as standard MCP tools that any
MCP-compliant AI client (Cursor, Claude Code, Zed) can invoke natively.

Transport: STDIO (stdin/stdout) for local IDE integration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ─── Server Setup ───────────────────────────────────────────────────────────

mcp = FastMCP("contextsync")


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


def _resolve_repo_root(path: Optional[str] = None) -> Path:
    """Resolve the repository root from a given path or CWD."""
    from git import Repo, InvalidGitRepositoryError

    target = Path(path).resolve() if path else Path.cwd()
    try:
        repo = Repo(target, search_parent_directories=True)
        return Path(repo.working_tree_dir)
    except InvalidGitRepositoryError:
        return target


def _get_walker(repo_root: Path):
    """Create a TreeWalker and build the tree for a given repo root."""
    from contextsync.config import find_config, load_config
    from contextsync.core.tree_walker import TreeWalker

    config = load_config(find_config(repo_root))
    walker = TreeWalker(repo_root, config)
    walker.build_tree()
    return walker, config


# ─── MCP Tools ──────────────────────────────────────────────────────────────


@mcp.tool()
def get_hierarchical_context(path: str) -> str:
    """Retrieve the CONTEXT.md ancestor chain for a given file or directory.

    Returns the full context hierarchy from the nearest CONTEXT.md up to
    the project root, giving the AI a complete architectural understanding
    of where it is in the codebase.

    Args:
        path: Relative or absolute path to a file or directory in the repo.
    """
    repo_root = _resolve_repo_root(path)
    walker, config = _get_walker(repo_root)

    target = Path(path).resolve()
    if not target.is_absolute():
        target = repo_root / path

    chain = walker.get_ancestor_chain(target)

    if not chain:
        return json.dumps({
            "status": "no_context",
            "message": f"No CONTEXT.md found in the ancestor chain of '{path}'. "
                       f"Run `contextsync scaffold` to generate context files.",
            "path": str(target),
        }, indent=2)

    results = []
    for node in chain:
        rel_path = str(node.dir_path.relative_to(repo_root))
        results.append({
            "directory": rel_path if rel_path != "." else "/",
            "depth": node.depth,
            "content": node.content,
            "has_children": len(node.children) > 0,
            "lateral_links": node.lateral_links,
        })

    return json.dumps({
        "status": "ok",
        "repo_root": str(repo_root),
        "context_chain": results,
        "chain_length": len(results),
    }, indent=2)


@mcp.tool()
def check_context_health(path: str = ".") -> str:
    """Check the health and coverage of CONTEXT.md files in the repository.

    Returns coverage percentage, number of context files, directories
    missing context, and overall status. Use this before large refactors
    to gauge how reliable the AI's understanding of the codebase is.

    Args:
        path: Path to the repository root (default: current directory).
    """
    repo_root = _resolve_repo_root(path)
    walker, config = _get_walker(repo_root)

    tree = walker._tree
    existing = [n for n in tree.values() if n.exists]
    needs_context = walker.get_directories_needing_context()

    total_eligible = len(existing) + len(needs_context)
    coverage = (len(existing) / total_eligible * 100) if total_eligible > 0 else 0

    # Identify stale contexts (files with very short content that may be stale)
    potentially_stale = [
        str(n.dir_path.relative_to(repo_root))
        for n in existing
        if len(n.content.strip()) < 100
    ]

    # Identify undocumented directories
    undocumented = [
        str(p.relative_to(repo_root))
        for p in needs_context[:20]  # Cap to avoid huge output
    ]

    health = "healthy" if coverage >= 80 else "degraded" if coverage >= 50 else "critical"

    return json.dumps({
        "status": health,
        "coverage_percent": round(coverage, 1),
        "total_context_files": len(existing),
        "directories_needing_context": len(needs_context),
        "total_eligible_directories": total_eligible,
        "potentially_stale_contexts": potentially_stale,
        "undocumented_directories": undocumented,
        "llm_provider": config.llm.provider,
        "llm_model": config.llm.model,
    }, indent=2)


@mcp.tool()
def trigger_scaffold(path: str, force: bool = False) -> str:
    """Generate CONTEXT.md files for a specific directory using LLM analysis.

    Analyzes the code structure (function signatures, classes, imports)
    and generates a detailed CONTEXT.md file. Use this when the AI
    encounters an undocumented module and needs to understand it.

    Args:
        path: Relative path to the directory to scaffold (e.g., "src/auth").
        force: If True, overwrite existing CONTEXT.md files.
    """
    import asyncio

    repo_root = _resolve_repo_root(path)
    _load_env(repo_root)

    from contextsync.config import find_config, load_config
    from contextsync.core.code_extractor import (
        extract_directory_structure,
        format_directory_analysis,
    )
    from contextsync.core.tree_walker import TreeWalker
    from contextsync.llm.base import ScaffoldRequest
    from contextsync.llm.litellm_adapter import LiteLLMAdapter

    config = load_config(find_config(repo_root))

    target_dir = Path(path).resolve()
    if not target_dir.is_absolute():
        target_dir = repo_root / path

    if not target_dir.is_dir():
        return json.dumps({
            "status": "error",
            "message": f"'{path}' is not a directory.",
        })

    context_path = target_dir / config.tree.filename
    if context_path.exists() and not force:
        return json.dumps({
            "status": "exists",
            "message": f"CONTEXT.md already exists at '{path}'. Use force=True to overwrite.",
            "content": context_path.read_text(encoding="utf-8"),
        })

    # Set up LLM
    model = config.llm.model
    if config.llm.provider == "gemini":
        model = f"gemini/{model}"
    elif config.llm.provider == "ollama":
        model = f"ollama/{model}"

    scaffold_max_tokens = max(config.llm.max_tokens_per_patch, 2000)
    llm = LiteLLMAdapter(
        model=model,
        temperature=config.llm.temperature,
        max_tokens=scaffold_max_tokens,
    )

    # Extract code structure
    structures = extract_directory_structure(target_dir)
    code_analysis = format_directory_analysis(target_dir, structures)

    listing = []
    for item in sorted(target_dir.iterdir()):
        if not item.name.startswith(".") and item.name != "__pycache__":
            listing.append(item.name)

    summaries = {fn: s.to_summary() for fn, s in structures.items()}

    # Get parent context
    walker = TreeWalker(repo_root, config)
    walker.build_tree()
    parent_node = walker.find_nearest_context(target_dir.parent)
    parent_context = parent_node.content if parent_node else None

    request = ScaffoldRequest(
        directory_path=str(target_dir.relative_to(repo_root)),
        directory_listing=f"{chr(10).join(listing)}\n\n--- CODE ANALYSIS ---\n{code_analysis}",
        code_summaries=summaries,
        parent_context=parent_context,
    )

    async def _run():
        return await llm.generate_scaffold(request)

    result = asyncio.run(_run())
    context_path.write_text(result.content, encoding="utf-8")

    return json.dumps({
        "status": "created",
        "path": str(context_path.relative_to(repo_root)),
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "content": result.content,
    }, indent=2)


@mcp.tool()
def propose_context_patch(diff_summary: str, path: str) -> str:
    """Propose an update to a CONTEXT.md file based on a code diff.

    Takes a summary of code changes and the path to the affected module,
    then uses the LLM to surgically patch the existing CONTEXT.md.

    Args:
        diff_summary: A text summary of what changed (e.g., "Added new login() method to AuthService").
        path: Relative path to the directory whose CONTEXT.md should be updated.
    """
    import asyncio

    repo_root = _resolve_repo_root(path)
    _load_env(repo_root)

    from contextsync.config import find_config, load_config
    from contextsync.core.tree_walker import TreeWalker
    from contextsync.llm.base import PatchRequest
    from contextsync.llm.litellm_adapter import LiteLLMAdapter

    config = load_config(find_config(repo_root))

    target_dir = Path(path).resolve()
    if not target_dir.is_absolute():
        target_dir = repo_root / path

    context_path = target_dir / config.tree.filename
    if not context_path.exists():
        return json.dumps({
            "status": "error",
            "message": f"No CONTEXT.md found at '{path}'. Run trigger_scaffold first.",
        })

    current_content = context_path.read_text(encoding="utf-8")

    # Set up LLM
    model = config.llm.model
    if config.llm.provider == "gemini":
        model = f"gemini/{model}"
    elif config.llm.provider == "ollama":
        model = f"ollama/{model}"

    llm = LiteLLMAdapter(
        model=model,
        temperature=config.llm.temperature,
        max_tokens=max(config.llm.max_tokens_per_patch, 2000),
    )

    # Build directory listing
    listing = []
    for item in sorted(target_dir.iterdir()):
        if not item.name.startswith(".") and item.name != "__pycache__":
            listing.append(item.name)

    request = PatchRequest(
        current_context=current_content,
        changed_files=[path],
        change_types=["modified"],
        changed_functions=[],
        changed_classes=[],
        directory_listing="\n".join(listing),
        diff_summary=diff_summary,
    )

    async def _run():
        return await llm.generate_patch(request)

    result = asyncio.run(_run())

    # Write the patched content
    context_path.write_text(result.patched_content, encoding="utf-8")

    return json.dumps({
        "status": "patched",
        "path": str(context_path.relative_to(repo_root)),
        "sections_modified": result.sections_modified,
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "content": result.patched_content,
    }, indent=2)


# ─── MCP Resources ──────────────────────────────────────────────────────────


@mcp.resource("contextsync://status")
def resource_status() -> str:
    """Current ContextSync health status as a resource."""
    return check_context_health()


# ─── Entry Point ────────────────────────────────────────────────────────────


def run_mcp_server():
    """Start the MCP server using STDIO transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
