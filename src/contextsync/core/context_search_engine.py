"""Context Search Engine — keyword-based search across all CONTEXT.md sections.

Phase 1: Keyword + section-type matching (zero external dependencies).
Phase 2 (future): Add embedding-based semantic search via Chroma/FAISS.

Each section is indexed by:
  - Section type (Gotchas, Invariants, Conventions, etc.)
  - Keywords extracted from content
  - Module path (for scoping)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from contextsync.core.tree_walker import ContextNode, TreeWalker


@dataclass
class SearchResult:
    """A single search result — one section from one CONTEXT.md file."""

    module_path: str         # e.g., "django/db/backends/oracle"
    section_type: str        # e.g., "## Gotchas"
    content: str             # Full section content
    relevance_score: float   # 0.0 to 1.0
    line_count: int


@dataclass
class IndexedSection:
    """A section in the search index."""

    module_path: str
    section_type: str
    content: str
    keywords: set[str]
    line_count: int


class ContextSearchEngine:
    """Searches across all CONTEXT.md sections using keyword matching.

    Usage:
        engine = ContextSearchEngine(tree_walker)
        engine.index()
        results = engine.search("webhook handling", section_types=["## Gotchas"])
    """

    def __init__(self, tree_walker: TreeWalker):
        self.tree_walker = tree_walker
        self.repo_root = tree_walker.repo_root
        self._index: list[IndexedSection] = []
        self._indexed = False

    def index(self) -> int:
        """Build search index from the context tree.

        Returns number of sections indexed.
        """
        tree = self.tree_walker.build_tree()
        self._index = []

        for node in tree.values():
            if not node.exists or not node.content:
                continue

            try:
                rel_path = str(node.dir_path.relative_to(self.repo_root))
            except ValueError:
                rel_path = str(node.dir_path)

            sections = self._parse_sections(node.content)
            for section_type, content in sections:
                keywords = self._extract_keywords(content)
                self._index.append(IndexedSection(
                    module_path=rel_path if rel_path != "." else "/",
                    section_type=section_type,
                    content=content,
                    keywords=keywords,
                    line_count=content.count("\n") + 1,
                ))

        self._indexed = True
        return len(self._index)

    def search(
        self,
        query: str,
        scope: str | None = None,
        section_types: list[str] | None = None,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Search indexed sections.

        Args:
            query: Natural language search query
            scope: Limit to sections under this path (e.g., "django/db/")
            section_types: Filter to specific section types (e.g., ["## Gotchas"])
            max_results: Maximum results to return

        Returns:
            List of SearchResults sorted by relevance
        """
        if not self._indexed:
            self.index()

        query_keywords = self._extract_keywords(query)
        if not query_keywords:
            return []

        results: list[SearchResult] = []

        for section in self._index:
            # Scope filter
            if scope and not section.module_path.startswith(scope):
                continue

            # Section type filter
            if section_types and section.section_type not in section_types:
                continue

            # Score by keyword overlap
            score = self._score_match(query_keywords, section.keywords, query, section.content)
            if score > 0.0:
                results.append(SearchResult(
                    module_path=section.module_path,
                    section_type=section.section_type,
                    content=section.content,
                    relevance_score=score,
                    line_count=section.line_count,
                ))

        # Sort by relevance
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:max_results]

    def get_sections_by_type(
        self,
        section_type: str,
        scope: str | None = None,
    ) -> list[SearchResult]:
        """Get all sections of a specific type, optionally scoped.

        Useful for collecting all ## Invariants or all ## Gotchas.
        """
        if not self._indexed:
            self.index()

        results: list[SearchResult] = []

        for section in self._index:
            if section.section_type != section_type:
                continue
            if scope and not section.module_path.startswith(scope):
                continue

            results.append(SearchResult(
                module_path=section.module_path,
                section_type=section.section_type,
                content=section.content,
                relevance_score=1.0,
                line_count=section.line_count,
            ))

        return results

    def get_all_section_types(self) -> dict[str, int]:
        """Return a count of each section type in the index."""
        if not self._indexed:
            self.index()

        counts: dict[str, int] = {}
        for section in self._index:
            counts[section.section_type] = counts.get(section.section_type, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    # ── Internal helpers ─────────────────────────────────────────────────

    def _parse_sections(self, content: str) -> list[tuple[str, str]]:
        """Parse CONTEXT.md content into (section_type, content) pairs."""
        lines = content.split("\n")
        sections: list[tuple[str, str]] = []

        current_type = "__header__"
        current_lines: list[str] = []

        for line in lines:
            if line.startswith("## "):
                if current_lines:
                    sections.append((current_type, "\n".join(current_lines)))
                current_type = line.strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_type, "\n".join(current_lines)))

        return sections

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract searchable keywords from text.

        Extracts:
        - Regular words (lowercased, 3+ chars)
        - Backtick-enclosed identifiers (preserved case)
        - CamelCase words split into parts
        """
        keywords: set[str] = set()

        # Extract backtick identifiers (code references)
        backtick_refs = re.findall(r'`([^`]+)`', text)
        for ref in backtick_refs:
            keywords.add(ref.lower())
            # Also add parts of dotted paths
            for part in ref.split("."):
                if len(part) >= 2:
                    keywords.add(part.lower())

        # Extract regular words
        words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text)
        for word in words:
            lower = word.lower()
            if len(lower) >= 3 and lower not in _STOP_WORDS:
                keywords.add(lower)

            # Split CamelCase
            parts = re.findall(r'[A-Z][a-z]+|[a-z]+', word)
            for part in parts:
                if len(part) >= 3 and part.lower() not in _STOP_WORDS:
                    keywords.add(part.lower())

        return keywords

    def _score_match(
        self,
        query_kw: set[str],
        section_kw: set[str],
        query_text: str,
        section_text: str,
    ) -> float:
        """Score how well a section matches a query.

        Scoring factors:
        1. Keyword overlap (Jaccard-like)
        2. Exact phrase match bonus
        3. Section type bonus (Gotchas > Key Components for actionability)
        """
        if not query_kw or not section_kw:
            return 0.0

        # Keyword overlap
        overlap = query_kw & section_kw
        if not overlap:
            return 0.0

        # Jaccard-like score (normalized by query size, not union)
        keyword_score = len(overlap) / len(query_kw)

        # Exact phrase bonus — if query appears verbatim in section
        phrase_bonus = 0.0
        query_lower = query_text.lower()
        if query_lower in section_text.lower():
            phrase_bonus = 0.3

        # Combine (cap at 1.0)
        return min(keyword_score + phrase_bonus, 1.0)


# Minimal stop word list — only filter truly useless words
_STOP_WORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all",
    "can", "had", "her", "was", "one", "our", "out", "has",
    "have", "been", "from", "this", "that", "they", "with",
    "will", "each", "make", "like", "when", "than", "them",
    "into", "some", "then", "what", "their", "which", "about",
    "would", "these", "other", "could", "should", "there",
})
