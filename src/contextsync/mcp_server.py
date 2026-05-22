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

mcp = FastMCP("contextmesh")


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


def _get_search_engine(repo_root: Path):
    """Create and index a ContextSearchEngine for a repo."""
    from contextsync.core.context_search_engine import ContextSearchEngine

    walker, config = _get_walker(repo_root)
    engine = ContextSearchEngine(walker)
    engine.index()
    return engine


# ─── MCP Tools — Universal Context Query ────────────────────────────────────


@mcp.tool()
def context_search(query: str, scope: str = ".", max_results: int = 5) -> str:
    """Search for relevant context across the entire codebase.

    Uses keyword matching to find the most relevant gotchas, invariants,
    conventions, and architectural context for a given task or topic.

    Works with ANY MCP-compliant client: Claude Code, Cursor, Gemini CLI,
    GitHub Copilot, Windsurf, Cline, or custom agents.

    Args:
        query: Natural language description of what you're working on
               (e.g., "webhook handling", "database migration", "auth flow",
                "Oracle CLOB", "payment processing")
        scope: Limit search to a subtree (e.g., "django/db/backends/").
               Use "." for repo-wide search.
        max_results: Maximum sections to return (default: 5)
    """
    repo_root = _resolve_repo_root()
    engine = _get_search_engine(repo_root)

    scope_path = None if scope == "." else scope
    results = engine.search(query, scope=scope_path, max_results=max_results)

    if not results:
        return json.dumps({
            "status": "no_results",
            "message": f"No context sections matching '{query}' found.",
            "suggestion": "Try broader search terms or check if CONTEXT.md files exist "
                          "(run `contextsync scaffold`).",
        }, indent=2)

    output = []
    for r in results:
        output.append({
            "module": r.module_path,
            "section": r.section_type,
            "relevance": round(r.relevance_score, 2),
            "content": r.content.strip(),
        })

    return json.dumps({
        "status": "ok",
        "query": query,
        "scope": scope,
        "results_count": len(output),
        "results": output,
    }, indent=2)


@mcp.tool()
def context_invariants(path: str = ".") -> str:
    """Get all code invariants, rules, and gotchas for a module.

    Returns only ## Invariants and ## Gotchas sections from the context tree.
    Use this BEFORE writing code to understand what constraints apply.

    These are rules the AI CANNOT discover by reading code alone —
    they represent hard-won team knowledge about what breaks.

    Args:
        path: Module path to get invariants for (e.g., "django/db/backends/oracle/").
              Use "." for all invariants in the repo.
    """
    repo_root = _resolve_repo_root()
    engine = _get_search_engine(repo_root)

    scope_path = None if path == "." else path

    invariants = engine.get_sections_by_type("## Invariants", scope=scope_path)
    gotchas = engine.get_sections_by_type("## Gotchas", scope=scope_path)
    caveats = engine.get_sections_by_type("## Caveats", scope=scope_path)

    all_rules = invariants + gotchas + caveats

    if not all_rules:
        return json.dumps({
            "status": "no_invariants",
            "message": f"No invariants or gotchas found for '{path}'.",
            "suggestion": "Run `contextsync scaffold --depth enhanced` to generate invariant sections.",
        }, indent=2)

    output = []
    for r in all_rules:
        output.append({
            "module": r.module_path,
            "type": r.section_type,
            "content": r.content.strip(),
        })

    return json.dumps({
        "status": "ok",
        "path": path,
        "total_rules": len(output),
        "rules": output,
    }, indent=2)


@mcp.tool()
def context_conventions(path: str = ".") -> str:
    """Get coding conventions and rejected approaches for a module.

    Returns ## Conventions, ## Rejected Approaches, and ## Decisions sections.
    Use this to match existing code style and avoid anti-patterns.

    Args:
        path: Module path (e.g., "django/db/"). Use "." for repo-wide conventions.
    """
    repo_root = _resolve_repo_root()
    engine = _get_search_engine(repo_root)

    scope_path = None if path == "." else path

    conventions = engine.get_sections_by_type("## Conventions", scope=scope_path)
    rejected = engine.get_sections_by_type("## Rejected Approaches", scope=scope_path)
    decisions = engine.get_sections_by_type("## Decisions", scope=scope_path)
    arch_decisions = engine.get_sections_by_type("## Architecture Decisions", scope=scope_path)

    all_conv = conventions + rejected + decisions + arch_decisions

    if not all_conv:
        return json.dumps({
            "status": "no_conventions",
            "message": f"No conventions or rejected approaches found for '{path}'.",
        }, indent=2)

    output = []
    for r in all_conv:
        output.append({
            "module": r.module_path,
            "type": r.section_type,
            "content": r.content.strip(),
        })

    return json.dumps({
        "status": "ok",
        "path": path,
        "total_conventions": len(output),
        "conventions": output,
    }, indent=2)


# ─── MCP Tools — Existing ──────────────────────────────────────────────────


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
def generate_progressive_bundle(path: str) -> str:
    """Generate a Progressive Context XML payload for the AI model.
    
    Provides FULL raw source code for the specified working directory (path),
    but highly compressed CONTEXT.md semantic summaries for the rest of the repository.
    This gives the AI 100% architectural awareness using 90% fewer tokens.
    
    Args:
        path: Relative path to the active directory the user is coding in (e.g., "src/core").
              Use "." for the repository root if no specific focus is needed.
    """
    repo_root = _resolve_repo_root(path)
    _load_env(repo_root)
    
    from contextsync.config import find_config, load_config
    config = load_config(find_config(repo_root))
    
    from contextsync.core.bundler import ProgressiveBundler
    
    bundler = ProgressiveBundler(repo_root, config)
    # The bundler expects a relative path payload to resolve the ContextNode
    # Handle "." explicitly
    target_rel = path if path != "." else ""
    return bundler.generate_bundle(target_rel)


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

    # AST Auto-Lateral graph mapping
    from contextsync.core.dependency_graph import PythonDependencyExtractor
    extractor = PythonDependencyExtractor(repo_root)
    ast_deps = extractor.extract_dependencies(target_dir)
    
    auto_links_prompt = ""
    if ast_deps:
        import os
        links = []
        for d in ast_deps:
            try:
                rel = os.path.relpath(d, target_dir)
                links.append(f"→ {rel}")
            except Exception:
                pass
        
        auto_links_prompt = (
            "CRITICAL AST INSTRUCTION: The following lateral folder dependencies were physically discovered "
            "via static abstract syntax tree parsing of the local python imports. You MUST include these "
            "exact lines inside the ## Relationships section of the output:\n" + "\n".join(links)
        )

    # Modify the directory listing to include the hardcoded prompt override
    combined_payload = f"{chr(10).join(listing)}\n\n--- CODE ANALYSIS ---\n{code_analysis}\n\n{auto_links_prompt}"

    request = ScaffoldRequest(
        directory_path=str(target_dir.relative_to(repo_root)),
        directory_listing=combined_payload,
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
        code_diff=diff_summary,
        changed_files=[path],
        change_types=["modified"],
        changed_functions=[],
        changed_classes=[],
        directory_listing="\n".join(listing),
        preserved_sections=config.preserved_sections,
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
