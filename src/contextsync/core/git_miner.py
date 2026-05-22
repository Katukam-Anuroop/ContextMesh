"""Git History Miner — extracts temporal signals from git history for enhanced context.

Mines evolution timelines, complexity signals, and gotcha hints from commit
messages and file change patterns. Feeds into Level 2+ CONTEXT.md generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


@dataclass
class EvolutionEntry:
    """A single significant event in a module's history."""
    date: str
    summary: str
    commit_hash: str
    change_type: str


@dataclass
class EvolutionData:
    """Timeline of significant changes for a directory."""
    entries: list[EvolutionEntry] = field(default_factory=list)
    first_commit_date: str = ""
    last_commit_date: str = ""
    total_commits: int = 0


@dataclass
class ComplexitySignals:
    """Quantitative complexity indicators for a directory."""
    commits_30d: int = 0
    commits_90d: int = 0
    unique_authors: int = 0
    churn_rate: float = 0.0
    most_changed_files: list[str] = field(default_factory=list)
    bug_fix_ratio: float = 0.0
    is_active: bool = False


GOTCHA_PATTERNS = [
    (r"\b(revert|reverted)\b", "revert"),
    (r"\b(workaround|hack|kludge)\b", "workaround"),
    (r"\b(careful|caution|beware|watch out)\b", "caution"),
    (r"\b(don'?t|never|must not|do not)\b", "prohibition"),
    (r"\b(breaking|BREAKING)\b", "breaking_change"),
    (r"\b(regression|regress)\b", "regression"),
    (r"\b(edge.?case|corner.?case)\b", "edge_case"),
    (r"\b(subtle|tricky|gotcha|pitfall)\b", "gotcha"),
    (r"\b(security|vulnerability|CVE|XSS|CSRF|injection)\b", "security"),
    (r"\b(race.?condition|deadlock|thread.?safe)\b", "concurrency"),
]

SIGNIFICANT_PATTERNS = [
    (r"\b(migrat|refactor|rewrit|redesign|overhaul)\b", "migration"),
    (r"\b(deprecat|remov|delet)\b", "deprecation"),
    (r"\b(add|introduc|implement|creat)\b.*\b(api|endpoint|model|class|module)\b", "new_feature"),
    (r"\b(upgrad|bump|update)\b.*\b(version|dependency|lib)\b", "dependency_change"),
    (r"\b(rename|mov)\b", "refactor"),
]


class GitMiner:
    """Extracts temporal context from git history for a directory."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        try:
            from git import Repo
            self.repo = Repo(repo_root)
            self._available = True
        except Exception:
            self._available = False

    def mine_evolution(self, dir_path: Path, max_commits: int = 50, max_days: int = 90) -> EvolutionData:
        """Extract timeline of architecturally significant changes for a directory."""
        if not self._available:
            return EvolutionData()

        data = EvolutionData()
        rel_path = str(dir_path.relative_to(self.repo_root))
        if rel_path == ".":
            rel_path = ""

        try:
            since_date = (datetime.now(timezone.utc) - timedelta(days=max_days)).strftime("%Y-%m-%d")
            log_args = [f"--max-count={max_commits}", f"--since={since_date}", "--format=%H|%ai|%s", "--"]
            if rel_path:
                log_args.append(f"{rel_path}/")

            log_output = self.repo.git.log(*log_args)
            if not log_output.strip():
                return data

            lines = log_output.strip().split("\n")
            data.total_commits = len(lines)

            if lines:
                first_parts = lines[-1].split("|", 2)
                last_parts = lines[0].split("|", 2)
                if len(first_parts) >= 2:
                    data.first_commit_date = first_parts[1].split()[0]
                if len(last_parts) >= 2:
                    data.last_commit_date = last_parts[1].split()[0]

            for line in lines:
                parts = line.split("|", 2)
                if len(parts) < 3:
                    continue
                commit_hash = parts[0][:7]
                date_str = parts[1].split()[0]
                message = parts[2].strip()
                change_type = self._classify_significance(message)
                if change_type:
                    summary = self._clean_commit_message(message)
                    data.entries.append(EvolutionEntry(
                        date=date_str[:7], summary=summary,
                        commit_hash=commit_hash, change_type=change_type,
                    ))

            # Deduplicate by month + change_type
            seen: set[tuple[str, str]] = set()
            deduped = []
            for entry in data.entries:
                key = (entry.date, entry.change_type)
                if key not in seen:
                    seen.add(key)
                    deduped.append(entry)
            data.entries = deduped[:10]
        except Exception:
            pass

        return data

    def mine_complexity_signals(self, dir_path: Path) -> ComplexitySignals:
        """Extract complexity indicators for a directory."""
        if not self._available:
            return ComplexitySignals()

        signals = ComplexitySignals()
        rel_path = str(dir_path.relative_to(self.repo_root))
        if rel_path == ".":
            rel_path = ""

        try:
            now = datetime.now(timezone.utc)
            since_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            since_90d = (now - timedelta(days=90)).strftime("%Y-%m-%d")

            log_args_base = ["--format=%H|%ai|%s|%an", "--"]
            if rel_path:
                log_args_base.append(f"{rel_path}/")

            log_90d = self.repo.git.log(f"--since={since_90d}", *log_args_base)
            lines_90d = [l for l in log_90d.strip().split("\n") if l.strip()] if log_90d.strip() else []
            signals.commits_90d = len(lines_90d)

            log_30d = self.repo.git.log(f"--since={since_30d}", *log_args_base)
            lines_30d = [l for l in log_30d.strip().split("\n") if l.strip()] if log_30d.strip() else []
            signals.commits_30d = len(lines_30d)
            signals.is_active = signals.commits_30d > 0

            authors: set[str] = set()
            bug_fix_count = 0
            for line in lines_90d:
                parts = line.split("|", 3)
                if len(parts) >= 4:
                    authors.add(parts[3].strip())
                    msg = parts[2].lower()
                    if any(p in msg for p in ["fix", "bug", "patch", "hotfix", "resolve"]):
                        bug_fix_count += 1

            signals.unique_authors = len(authors)
            signals.bug_fix_ratio = bug_fix_count / max(len(lines_90d), 1)

            try:
                stat_output = self.repo.git.log(
                    f"--since={since_90d}", "--name-only", "--format=", "--",
                    f"{rel_path}/" if rel_path else ".",
                )
                if stat_output.strip():
                    file_counts: dict[str, int] = {}
                    for fname in stat_output.strip().split("\n"):
                        fname = fname.strip()
                        if fname and not fname.endswith("CONTEXT.md"):
                            basename = Path(fname).name
                            file_counts[basename] = file_counts.get(basename, 0) + 1
                    sorted_files = sorted(file_counts.items(), key=lambda x: -x[1])
                    signals.most_changed_files = [f for f, _ in sorted_files[:5]]
                    total_changes = sum(file_counts.values())
                    unique_files = len(file_counts)
                    months = max(signals.commits_90d / 30, 1)
                    signals.churn_rate = round(total_changes / max(unique_files, 1) / months, 2)
            except Exception:
                pass
        except Exception:
            pass

        return signals

    def mine_gotcha_hints(self, dir_path: Path, max_commits: int = 100) -> list[str]:
        """Scan commit messages for patterns that hint at gotchas/footguns."""
        if not self._available:
            return []

        rel_path = str(dir_path.relative_to(self.repo_root))
        if rel_path == ".":
            rel_path = ""

        hints: list[str] = []
        try:
            log_args = [f"--max-count={max_commits}", "--format=%s", "--"]
            if rel_path:
                log_args.append(f"{rel_path}/")
            log_output = self.repo.git.log(*log_args)
            if not log_output.strip():
                return hints
            for line in log_output.strip().split("\n"):
                msg = line.strip()
                if not msg:
                    continue
                for pattern, category in GOTCHA_PATTERNS:
                    if re.search(pattern, msg, re.IGNORECASE):
                        hints.append(f"[{category}] {msg}")
                        break
        except Exception:
            pass

        seen: set[str] = set()
        unique = []
        for h in hints:
            if h not in seen:
                seen.add(h)
                unique.append(h)
        return unique[:15]

    def _classify_significance(self, message: str) -> Optional[str]:
        """Check if a commit message indicates an architecturally significant change."""
        msg_lower = message.lower()
        for pattern, change_type in SIGNIFICANT_PATTERNS:
            if re.search(pattern, msg_lower):
                return change_type
        return None

    def _clean_commit_message(self, message: str) -> str:
        """Clean up a commit message for display in evolution log."""
        msg = re.sub(r"^(feat|fix|refactor|chore|docs|ci|test|perf)(\(.*?\))?:\s*", "", message)
        if msg:
            msg = msg[0].upper() + msg[1:]
        if len(msg) > 100:
            msg = msg[:97] + "..."
        return msg


def format_evolution_for_llm(data: EvolutionData) -> str:
    """Format evolution data as text for inclusion in LLM prompts."""
    if not data.entries and data.total_commits == 0:
        return "(no git history available)"
    parts = [
        f"Total commits in window: {data.total_commits}",
        f"Date range: {data.first_commit_date} to {data.last_commit_date}",
        "", "Significant changes:",
    ]
    for entry in data.entries:
        parts.append(f"- {entry.date} [{entry.change_type}]: {entry.summary} ({entry.commit_hash})")
    if not data.entries:
        parts.append("- No architecturally significant changes detected in recent history")
    return "\n".join(parts)


def format_complexity_for_llm(signals: ComplexitySignals) -> str:
    """Format complexity signals as text for inclusion in LLM prompts."""
    activity = "active" if signals.is_active else "dormant"
    parts = [
        f"Activity: {activity} ({signals.commits_30d} commits in 30d, {signals.commits_90d} in 90d)",
        f"Contributors: {signals.unique_authors} unique authors (90d)",
        f"Bug-fix ratio: {signals.bug_fix_ratio:.0%} of recent commits are fixes",
        f"Churn rate: {signals.churn_rate} changes/file/month",
    ]
    if signals.most_changed_files:
        parts.append(f"Hottest files: {', '.join(signals.most_changed_files)}")
    return "\n".join(parts)


def format_gotcha_hints_for_llm(hints: list[str]) -> str:
    """Format gotcha hints as text for inclusion in LLM prompts."""
    if not hints:
        return "(no gotcha patterns found in commit history)"
    parts = ["Commit messages suggesting pitfalls or non-obvious behavior:"]
    for hint in hints:
        parts.append(f"- {hint}")
    return "\n".join(parts)
