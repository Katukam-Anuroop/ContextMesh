"""Watcher — Live filesystem monitoring for automatic context updates."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from threading import Timer
from typing import Optional

from rich.console import Console
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from contextsync.config import ContextSyncConfig
from contextsync.core.engine import Engine

console = Console()


class ContextSyncEventHandler(FileSystemEventHandler):
    """Handles file system events and debounces them before triggering the pipeline."""

    def __init__(
        self,
        repo_root: Path,
        config: ContextSyncConfig,
        debounce_seconds: float = 2.0,
    ):
        self.repo_root = repo_root
        self.config = config
        self.debounce_seconds = debounce_seconds

        self._timer: Optional[Timer] = None
        self._changed_files: set[str] = set()
        self._engine = Engine(repo_root, config, dry_run=False)

        # Standard exclusions
        self._exclusions = {
            ".git",
            ".contextsync",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            "env",
            ".env",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "dist",
            "build",
        }
        self._exclude_files = {self.config.tree.filename, ".cursorrules", "AGENTS.md"}

    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        try:
            rel_path = path.relative_to(self.repo_root)
        except ValueError:
            return True

        if rel_path.name in self._exclude_files:
            return True

        for part in rel_path.parts:
            if part in self._exclusions:
                return True

        # Only care about source code extensions to avoid triggering on log files, etc.
        valid_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".md", ".json", ".yaml", ".yml"}
        if path.is_file() and path.suffix not in valid_extensions and path.suffix != "":
            return True

        return False

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Catch all events, filter them, and add to the queue."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if self._should_ignore(path):
            return

        # Handle file renames
        if hasattr(event, "dest_path"):
            dest_path = Path(event.dest_path)
            if not self._should_ignore(dest_path):
                self._add_to_queue(str(dest_path))

        self._add_to_queue(str(path))

    def _add_to_queue(self, path: str) -> None:
        """Add a file path to the debounce queue."""
        self._changed_files.add(path)

        # Reset the timer
        if self._timer:
            self._timer.cancel()

        self._timer = Timer(self.debounce_seconds, self._flush_queue)
        self._timer.start()

    def _flush_queue(self) -> None:
        """Execute the engine async run with the collected files."""
        if not self._changed_files:
            return

        files_to_process = self._changed_files.copy()
        self._changed_files.clear()

        rel_paths = []
        for f in files_to_process:
            try:
                rel = Path(f).relative_to(self.repo_root)
                rel_paths.append(str(rel))
            except ValueError:
                pass

        if not rel_paths:
            return

        console.print(f"\n[dim]{time.strftime('%H:%M:%S')}[/dim] [bold blue]Changes detected in {len(rel_paths)} files...[/bold blue]")

        # We pass the changed files through git diff by analyzing local uncommitted changes
        # The engine currently uses diff_analyzer which compares HEAD. 
        # For watch mode, we compare working tree to HEAD.
        try:
            asyncio.run(self._engine.run_async(from_ref="HEAD", to_ref=None))
        except Exception as e:
            console.print(f"[red]Engine failed during auto-update: {e}[/red]")


class ContextSyncWatcher:
    """Manages the watchdog observer for the repository."""

    def __init__(self, repo_root: Path, config: ContextSyncConfig, debounce_seconds: float = 2.0):
        self.repo_root = repo_root.resolve()
        self.event_handler = ContextSyncEventHandler(self.repo_root, config, debounce_seconds)
        self.observer = Observer()

    def start(self) -> None:
        """Start the file watcher."""
        self.observer.schedule(self.event_handler, str(self.repo_root), recursive=True)
        self.observer.start()

        console.print(f"[bold green]👀 ContextSync Watcher started in {self.repo_root}[/]")
        console.print(f"[dim]Monitoring for changes. Press Ctrl+C to stop.[/dim]\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop the file watcher."""
        console.print("\n[dim]Stopping watcher...[/dim]")
        self.observer.stop()
        self.observer.join()
