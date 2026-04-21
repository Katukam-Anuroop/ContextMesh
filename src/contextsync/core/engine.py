"""Engine — orchestrates the full CDC pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console

from contextsync.config import ContextSyncConfig, load_config
from contextsync.core.aggregator import Aggregator
from contextsync.core.diff_analyzer import DiffAnalyzer, FileChange
from contextsync.core.patcher import Patcher
from contextsync.core.qa_pipeline import QAPipeline, QAResult
from contextsync.core.salience import SalienceClassifier, SalienceResult
from contextsync.core.tree_walker import ContextNode, TreeWalker
from contextsync.llm.base import PatchResult
from contextsync.llm.litellm_adapter import LiteLLMAdapter

console = Console()


@dataclass
class PipelineStepResult:
    """Result for a single context file update."""
    context_path: str
    patch_result: Optional[PatchResult] = None
    qa_result: Optional[QAResult] = None
    salience_scores: list[SalienceResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """Complete result of a CDC pipeline run."""
    changes_detected: int = 0
    files_analyzed: int = 0
    context_files_updated: int = 0
    context_files_skipped: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    step_results: list[PipelineStepResult] = field(default_factory=list)
    surfaces_written: list[str] = field(default_factory=list)
    commit_hash: str = ""
    errors: list[str] = field(default_factory=list)


class Engine:
    """Orchestrates the full ContextSync CDC pipeline.

    Pipeline: diff → tree → salience → patch → QA → validate → write → aggregate
    """

    def __init__(
        self,
        repo_root: Path,
        config: Optional[ContextSyncConfig] = None,
        dry_run: bool = False,
    ):
        self.repo_root = repo_root.resolve()
        self.config = config or load_config()
        self.dry_run = dry_run

        # Load .env file for API keys
        self._load_env()

        # Initialize components
        self.diff_analyzer = DiffAnalyzer(self.repo_root)
        self.tree_walker = TreeWalker(self.repo_root, self.config)
        self.salience = SalienceClassifier(self.config.salience)
        self.qa = QAPipeline(self.repo_root, self.config.qa.max_diff_percent)

        # LLM adapter
        model = self.config.llm.model
        if self.config.llm.provider == "gemini":
            model = f"gemini/{model}"
        elif self.config.llm.provider == "ollama":
            model = f"ollama/{model}"

        self.llm = LiteLLMAdapter(
            model=model,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens_per_patch,
        )
        self.patcher = Patcher(self.llm, self.config)
        self.aggregator = Aggregator(self.tree_walker, self.config)

    def run(
        self,
        from_ref: Optional[str] = None,
        to_ref: Optional[str] = None,
    ) -> PipelineResult:
        """Run the full CDC pipeline synchronously."""
        return asyncio.run(self.run_async(from_ref, to_ref))

    async def run_async(
        self,
        from_ref: Optional[str] = None,
        to_ref: Optional[str] = None,
    ) -> PipelineResult:
        """Run the full CDC pipeline.

        Steps:
        1. Analyze git diff → list of FileChanges
        2. Build context tree
        3. Score salience of each change
        4. For significant changes, generate patches via LLM
        5. Run QA pipeline on patches
        6. Write updated context files (unless dry_run)
        7. Regenerate flat surface files
        """
        result = PipelineResult()
        result.commit_hash = self.diff_analyzer.get_current_hash()

        # Step 1: Analyze diff
        console.print("[bold blue]Step 1:[/] Analyzing git diff...")
        changes = self.diff_analyzer.analyze(from_ref, to_ref)
        result.changes_detected = len(changes)
        result.files_analyzed = len(changes)

        if not changes:
            console.print("[dim]No changes detected.[/dim]")
            return result

        console.print(f"  Found {len(changes)} changed files")

        # Step 2: Build context tree
        console.print("[bold blue]Step 2:[/] Building context tree...")
        tree = self.tree_walker.build_tree()
        existing_contexts = [n for n in tree.values() if n.exists]
        console.print(f"  Found {len(existing_contexts)} existing CONTEXT.md files")

        # Step 3: Score salience
        console.print("[bold blue]Step 3:[/] Scoring salience...")
        significant = self.salience.filter_significant(changes)
        console.print(
            f"  {len(significant)}/{len(changes)} changes are significant "
            f"(threshold: {self.config.salience.threshold})"
        )

        if not significant:
            console.print("[dim]No significant changes. Skipping context updates.[/dim]")
            return result

        # Step 4: Determine impacted context files
        console.print("[bold blue]Step 4:[/] Determining impacted context files...")
        significant_files = [change.path for change, _ in significant]
        impacted_nodes = self.tree_walker.get_impact_set(significant_files)
        console.print(f"  {len(impacted_nodes)} CONTEXT.md files impacted")

        # Step 5: Generate patches
        console.print("[bold blue]Step 5:[/] Generating patches via LLM...")
        for node in impacted_nodes:
            step_result = PipelineStepResult(
                context_path=str(node.path.relative_to(self.repo_root))
            )

            # Find changes relevant to this node
            node_changes = self._filter_changes_for_node(changes, node)
            if not node_changes:
                step_result.skipped = True
                step_result.skip_reason = "No relevant changes for this context"
                result.context_files_skipped += 1
                result.step_results.append(step_result)
                continue

            try:
                # Generate patch
                patch = await self.patcher.patch(
                    node=node,
                    changes=node_changes,
                    sync_hash=result.commit_hash,
                )
                step_result.patch_result = patch
                result.total_tokens += patch.tokens_used
                result.total_cost_usd += patch.cost_usd

                # Step 6: QA validation
                qa = self.qa.validate(
                    original_content=node.content,
                    patched_content=patch.patched_content,
                    directory=node.dir_path,
                )
                step_result.qa_result = qa

                if qa.passed or not qa.errors:
                    # Write the patched content
                    if not self.dry_run:
                        node.path.write_text(patch.patched_content, encoding="utf-8")
                    result.context_files_updated += 1
                    console.print(
                        f"  ✅ Updated: {node.path.relative_to(self.repo_root)}"
                        f" ({len(patch.sections_modified)} sections modified)"
                    )
                else:
                    result.context_files_skipped += 1
                    error_msg = "; ".join(e.message for e in qa.errors)
                    step_result.error = f"QA failed: {error_msg}"
                    console.print(
                        f"  ❌ QA failed: {node.path.relative_to(self.repo_root)}"
                        f" — {error_msg}"
                    )

            except Exception as e:
                step_result.error = str(e)
                result.errors.append(f"{node.path}: {e}")
                console.print(f"  ❌ Error: {node.path.relative_to(self.repo_root)} — {e}")

            result.step_results.append(step_result)

        # Step 6.5: Cross-Document Validation
        if not self.dry_run and result.context_files_updated > 0:
            console.print("[bold blue]Step 6.5:[/bold blue] Running Cross-Document Validation...")
            from contextsync.core.cross_doc_validator import CrossDocValidator
            # Rebuild tree to get latest updated files
            self.tree_walker.build_tree()
            validator = CrossDocValidator(self.repo_root, self.tree_walker)
            report = validator.validate()
            
            if report.issues:
                console.print(f"  [yellow]Found {len(report.issues)} cross-document consistency issues.[/yellow]")
                for issue in report.issues[:5]:  # limit to 5 to avoid spam
                    icon = "❌" if issue.severity == "error" else "⚠️"
                    console.print(f"    {icon} {issue.node_path.relative_to(self.repo_root)}: {issue.message}")
            else:
                console.print(f"  ✅ Context tree is vertically and laterally consistent (Health Score: {report.health_score*100:.1f}%)")

        # Step 7: Regenerate surface files
        if not self.dry_run and result.context_files_updated > 0:
            console.print("[bold blue]Step 7:[/bold blue] Regenerating surface files...")
            try:
                written = self.aggregator.write_surfaces(self.repo_root)
                result.surfaces_written = written
                console.print(f"  Written: {', '.join(written)}")
            except Exception as e:
                result.errors.append(f"Surface generation failed: {e}")

        # Summary
        console.print()
        console.print(f"[bold green]Pipeline complete:[/]")
        console.print(f"  Changes: {result.changes_detected}")
        console.print(f"  Context files updated: {result.context_files_updated}")
        console.print(f"  Context files skipped: {result.context_files_skipped}")
        console.print(f"  Tokens used: {result.total_tokens:,}")
        console.print(f"  Cost: ${result.total_cost_usd:.4f}")
        if result.errors:
            console.print(f"  [red]Errors: {len(result.errors)}[/red]")

        return result

    def _filter_changes_for_node(
        self,
        changes: list[FileChange],
        node: ContextNode,
    ) -> list[FileChange]:
        """Filter changes to only those relevant to a specific context node."""
        relevant = []
        node_rel_path = node.dir_path.relative_to(self.repo_root)

        for change in changes:
            change_path = Path(change.path)
            # Check if the changed file is under this node's directory
            try:
                change_path.relative_to(node_rel_path)
                relevant.append(change)
            except ValueError:
                pass

        return relevant

    def _load_env(self) -> None:
        """Load .env file from repo root or project root."""
        import os

        try:
            from dotenv import load_dotenv
        except ImportError:
            # python-dotenv not installed, try manual loading
            load_dotenv = None

        # Search order: repo root, then cwd
        env_locations = [
            self.repo_root / ".env",
            Path.cwd() / ".env",
        ]

        for env_path in env_locations:
            if env_path.exists():
                if load_dotenv:
                    load_dotenv(env_path)
                else:
                    # Manual .env parsing fallback
                    with open(env_path) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, _, value = line.partition("=")
                                key = key.strip()
                                value = value.strip().strip('"').strip("'")
                                if key and value and key not in os.environ:
                                    os.environ[key] = value
                break  # Use the first .env found

