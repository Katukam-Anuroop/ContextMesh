"""Section Ranker — prioritizes CONTEXT.md sections by AI impact.

When outputting to token-constrained targets (e.g., .cursorrules at 300 lines),
we can't include everything. This module scores sections by how much they
help AI agents write correct code, and truncates intelligently.

Key insight: AI can read code to learn structure (## Key Components),
but CANNOT discover gotchas, invariants, or rejected approaches from code alone.
Those sections have the highest information gain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ─── Section Priority ───────────────────────────────────────────────────────

# Higher score = more valuable to AI agents.
# Rationale:
#   - Gotchas/Invariants: Prevents mistakes AI can't see in code → highest value
#   - Conventions/Rejected: Style and anti-patterns → high value
#   - Relationships/Purpose: Module understanding → medium value
#   - Key Components/Evolution: AI can read code / not actionable → low value

SECTION_PRIORITY: dict[str, int] = {
    "## Gotchas": 100,
    "## Invariants": 95,
    "## Rejected Approaches": 90,
    "## Caveats": 85,
    "## Conventions": 80,
    "## Decisions": 75,
    "## Architecture Decisions": 75,
    "## Relationships": 70,
    "## Purpose": 60,
    "## Key Components": 30,
    "## Evolution": 20,
    "## Complexity Signals": 10,
}

# Default priority for unknown sections
DEFAULT_PRIORITY = 50


@dataclass
class RankedSection:
    """A parsed section with its priority score."""

    heading: str
    content: str
    priority: int
    line_count: int


def parse_sections(content: str) -> list[RankedSection]:
    """Parse a CONTEXT.md file into ranked sections.

    Splits on ## headings, preserves the # title and metadata as a
    special high-priority section.
    """
    lines = content.split("\n")
    sections: list[RankedSection] = []

    current_heading = "__header__"
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            # Save previous section
            if current_lines:
                section_content = "\n".join(current_lines)
                priority = _get_priority(current_heading)
                sections.append(RankedSection(
                    heading=current_heading,
                    content=section_content,
                    priority=priority,
                    line_count=len(current_lines),
                ))

            current_heading = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines:
        section_content = "\n".join(current_lines)
        priority = _get_priority(current_heading)
        sections.append(RankedSection(
            heading=current_heading,
            content=section_content,
            priority=priority,
            line_count=len(current_lines),
        ))

    return sections


def rank_and_truncate(content: str, max_lines: int) -> str:
    """Keep highest-priority sections within a line budget.

    Strategy:
    1. Parse into sections
    2. Always keep the header (# title + metadata)
    3. Sort remaining sections by priority (descending)
    4. Greedily add sections until line budget is exhausted
    5. If we can't fit a full section, add a summary note

    Args:
        content: Full CONTEXT.md content
        max_lines: Maximum lines allowed in output

    Returns:
        Truncated content with highest-value sections preserved
    """
    sections = parse_sections(content)

    if not sections:
        return content

    # Always keep the header section
    header = None
    body_sections = []
    for s in sections:
        if s.heading == "__header__":
            header = s
        else:
            body_sections.append(s)

    # Check if we're already under budget
    total_lines = sum(s.line_count for s in sections)
    if total_lines <= max_lines:
        return content

    # Sort body sections by priority (highest first)
    body_sections.sort(key=lambda s: s.priority, reverse=True)

    # Greedily add sections
    result_parts: list[str] = []
    lines_used = 0

    if header:
        result_parts.append(header.content)
        lines_used += header.line_count

    included_sections: list[str] = []
    omitted_sections: list[str] = []

    for section in body_sections:
        if lines_used + section.line_count <= max_lines - 3:  # Reserve 3 lines for footer
            result_parts.append(section.content)
            lines_used += section.line_count
            included_sections.append(section.heading)
        else:
            omitted_sections.append(section.heading)

    # Add a note about omitted sections
    if omitted_sections:
        omitted_list = ", ".join(omitted_sections)
        result_parts.append(
            f"\n<!-- Sections omitted for brevity: {omitted_list}. "
            f"See CONTEXT.md files for full context. -->"
        )

    return "\n".join(result_parts)


def rank_multi_file(
    contents: list[tuple[str, str]],
    max_lines: int,
) -> str:
    """Rank and merge multiple CONTEXT.md files into a single output.

    Used when aggregating the full tree into a flat file.

    Args:
        contents: List of (relative_path, content) tuples
        max_lines: Total line budget for the merged output

    Returns:
        Merged content with highest-priority sections from all files
    """
    # Parse all sections with their source path
    all_sections: list[tuple[str, RankedSection]] = []

    for rel_path, content in contents:
        sections = parse_sections(content)
        for section in sections:
            all_sections.append((rel_path, section))

    # Separate headers from body sections
    headers: list[tuple[str, RankedSection]] = []
    bodies: list[tuple[str, RankedSection]] = []

    for path, section in all_sections:
        if section.heading == "__header__":
            headers.append((path, section))
        else:
            bodies.append((path, section))

    # Sort body sections by priority
    bodies.sort(key=lambda x: x[1].priority, reverse=True)

    # Build output
    result_parts: list[str] = []
    lines_used = 0

    # Include headers (module titles) first — each gets a source marker
    for path, header in headers:
        marker = f"<!-- From: {path} -->"
        section_text = f"{marker}\n{header.content}"
        section_lines = section_text.count("\n") + 1

        if lines_used + section_lines <= max_lines * 0.4:  # Headers get 40% of budget
            result_parts.append(section_text)
            lines_used += section_lines

    result_parts.append("\n---\n")
    lines_used += 3

    # Fill remaining budget with highest-priority body sections
    for path, section in bodies:
        if lines_used + section.line_count <= max_lines - 3:
            source_marker = f"<!-- {path} -->"
            result_parts.append(f"{source_marker}\n{section.content}")
            lines_used += section.line_count + 1

    return "\n".join(result_parts)


def _get_priority(heading: str) -> int:
    """Look up section priority, handling variations."""
    if heading == "__header__":
        return 200  # Always keep the header

    # Exact match
    if heading in SECTION_PRIORITY:
        return SECTION_PRIORITY[heading]

    # Fuzzy match (case-insensitive, strip extra text)
    heading_lower = heading.lower().strip()
    for key, priority in SECTION_PRIORITY.items():
        if key.lower() in heading_lower:
            return priority

    return DEFAULT_PRIORITY
