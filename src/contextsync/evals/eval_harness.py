"""Evaluation Harness — measures whether ContextSync context improves AI output.

Provides tools to:
1. Compare basic vs enhanced scaffold output (section-level diff)
2. Score CONTEXT.md quality by checking section presence and content density
3. Run structured eval tasks that measure gotcha/invariant coverage

Usage:
    python -m contextsync.evals.eval_harness --repo /path/to/repo --depth-compare
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from contextsync.core.section_ranker import parse_sections, SECTION_PRIORITY


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class SectionPresence:
    """Whether a specific section type exists and its quality metrics."""
    section_type: str
    present: bool
    line_count: int = 0
    has_specific_content: bool = False  # Not just a generic placeholder


@dataclass
class FileEvalResult:
    """Evaluation result for a single CONTEXT.md file."""
    file_path: str
    total_lines: int
    sections: list[SectionPresence]
    quality_score: float  # 0.0 to 1.0
    missing_high_value: list[str]  # High-value sections not present
    depth_level: str  # "basic" or "enhanced"


@dataclass
class ComparisonResult:
    """Side-by-side comparison of basic vs enhanced output."""
    file_path: str
    basic: FileEvalResult
    enhanced: FileEvalResult
    score_delta: float  # enhanced.quality_score - basic.quality_score
    new_sections: list[str]  # Sections in enhanced but not basic
    richer_sections: list[str]  # Sections with more content in enhanced


@dataclass
class EvalReport:
    """Full evaluation report across a repository."""
    repo_path: str
    total_files: int
    file_results: list[FileEvalResult]
    avg_quality_score: float
    section_coverage: dict[str, float]  # section_type → % of files that have it
    comparisons: list[ComparisonResult] = field(default_factory=list)


# ─── High-Value Section Checklist ────────────────────────────────────────────

# Sections that Level 2+ enhanced context should always generate
ENHANCED_SECTIONS = [
    "## Gotchas",
    "## Invariants",
    "## Evolution",
    "## Rejected Approaches",
    "## Complexity Signals",
]

# Sections that even basic context should have
BASIC_SECTIONS = [
    "## Purpose",
    "## Key Components",
    "## Relationships",
    "## Conventions",
]


# ─── Evaluation Functions ────────────────────────────────────────────────────

def evaluate_file(context_path: Path, depth_level: str = "unknown") -> FileEvalResult:
    """Evaluate a single CONTEXT.md file for quality and completeness.

    Scores based on:
    - Section presence (weighted by AI-impact priority)
    - Content density (not just headers, but actual content)
    - High-value section coverage
    """
    content = context_path.read_text(encoding="utf-8")
    sections = parse_sections(content)

    # Check which sections are present
    section_map: dict[str, SectionPresence] = {}
    for section in sections:
        if section.heading == "__header__":
            continue

        # Check if content is substantial (not just the heading)
        has_content = section.line_count > 2  # More than just the heading + blank line
        section_map[section.heading] = SectionPresence(
            section_type=section.heading,
            present=True,
            line_count=section.line_count,
            has_specific_content=has_content,
        )

    # Calculate quality score
    total_weight = 0
    earned_weight = 0

    all_expected = BASIC_SECTIONS + ENHANCED_SECTIONS
    for section_type in all_expected:
        weight = SECTION_PRIORITY.get(section_type, 50)
        total_weight += weight

        presence = section_map.get(section_type)
        if presence and presence.present:
            if presence.has_specific_content:
                earned_weight += weight
            else:
                earned_weight += weight * 0.3  # Partial credit for empty sections

    quality_score = earned_weight / total_weight if total_weight > 0 else 0.0

    # Identify missing high-value sections
    missing_high_value = []
    for section_type in ENHANCED_SECTIONS:
        if section_type not in section_map:
            missing_high_value.append(section_type)

    try:
        rel_path = str(context_path.relative_to(context_path.parent.parent))
    except ValueError:
        rel_path = str(context_path)

    return FileEvalResult(
        file_path=rel_path,
        total_lines=content.count("\n") + 1,
        sections=list(section_map.values()),
        quality_score=quality_score,
        missing_high_value=missing_high_value,
        depth_level=depth_level,
    )


def evaluate_repo(
    repo_root: Path,
    context_filename: str = "CONTEXT.md",
) -> EvalReport:
    """Evaluate all CONTEXT.md files in a repository."""
    context_files = list(repo_root.rglob(context_filename))

    file_results = []
    section_counts: dict[str, int] = {}

    for ctx_file in context_files:
        # Determine depth level from content hints
        content = ctx_file.read_text(encoding="utf-8")
        depth = "enhanced" if "## Gotchas" in content or "## Invariants" in content else "basic"

        result = evaluate_file(ctx_file, depth_level=depth)
        file_results.append(result)

        for section in result.sections:
            section_counts[section.section_type] = section_counts.get(
                section.section_type, 0
            ) + (1 if section.present else 0)

    # Calculate coverage percentages
    total = len(file_results) if file_results else 1
    section_coverage = {
        stype: count / total for stype, count in section_counts.items()
    }

    avg_score = (
        sum(r.quality_score for r in file_results) / total
        if file_results
        else 0.0
    )

    return EvalReport(
        repo_path=str(repo_root),
        total_files=len(file_results),
        file_results=file_results,
        avg_quality_score=avg_score,
        section_coverage=section_coverage,
    )


def compare_depth_levels(
    repo_root: Path,
    basic_dir: Path,
    enhanced_dir: Path,
) -> list[ComparisonResult]:
    """Compare basic vs enhanced scaffold output side-by-side.

    Expects two directories containing CONTEXT.md files generated at
    different depth levels.
    """
    comparisons = []

    for basic_file in basic_dir.rglob("CONTEXT.md"):
        rel = basic_file.relative_to(basic_dir)
        enhanced_file = enhanced_dir / rel

        if not enhanced_file.exists():
            continue

        basic_eval = evaluate_file(basic_file, depth_level="basic")
        enhanced_eval = evaluate_file(enhanced_file, depth_level="enhanced")

        # Find new sections in enhanced
        basic_section_types = {s.section_type for s in basic_eval.sections}
        enhanced_section_types = {s.section_type for s in enhanced_eval.sections}
        new_sections = list(enhanced_section_types - basic_section_types)

        # Find richer sections
        richer = []
        for es in enhanced_eval.sections:
            for bs in basic_eval.sections:
                if es.section_type == bs.section_type and es.line_count > bs.line_count * 1.5:
                    richer.append(es.section_type)

        comparisons.append(ComparisonResult(
            file_path=str(rel),
            basic=basic_eval,
            enhanced=enhanced_eval,
            score_delta=enhanced_eval.quality_score - basic_eval.quality_score,
            new_sections=new_sections,
            richer_sections=richer,
        ))

    return comparisons


# ─── CLI Report Formatter ────────────────────────────────────────────────────

def format_eval_report(report: EvalReport) -> str:
    """Format an evaluation report as human-readable text."""
    lines = [
        f"# ContextSync Evaluation Report",
        f"",
        f"**Repository**: {report.repo_path}",
        f"**Files evaluated**: {report.total_files}",
        f"**Average quality score**: {report.avg_quality_score:.1%}",
        f"",
        f"## Section Coverage",
        f"",
    ]

    for stype, coverage in sorted(
        report.section_coverage.items(),
        key=lambda x: SECTION_PRIORITY.get(x[0], 50),
        reverse=True,
    ):
        bar = "█" * int(coverage * 20) + "░" * (20 - int(coverage * 20))
        priority = SECTION_PRIORITY.get(stype, 50)
        lines.append(f"  {stype:30s} {bar} {coverage:.0%} (priority: {priority})")

    # Highlight quality distribution
    lines.extend([
        "",
        "## Quality Distribution",
        "",
    ])

    excellent = sum(1 for r in report.file_results if r.quality_score >= 0.8)
    good = sum(1 for r in report.file_results if 0.6 <= r.quality_score < 0.8)
    fair = sum(1 for r in report.file_results if 0.4 <= r.quality_score < 0.6)
    poor = sum(1 for r in report.file_results if r.quality_score < 0.4)

    lines.append(f"  Excellent (≥80%): {excellent}")
    lines.append(f"  Good (60-80%):    {good}")
    lines.append(f"  Fair (40-60%):    {fair}")
    lines.append(f"  Poor (<40%):      {poor}")

    # Top and bottom files
    sorted_files = sorted(report.file_results, key=lambda r: r.quality_score, reverse=True)

    if sorted_files:
        lines.extend(["", "## Top 5 Files"])
        for r in sorted_files[:5]:
            depth_badge = "🟢" if r.depth_level == "enhanced" else "⚪"
            lines.append(f"  {depth_badge} {r.quality_score:.0%} — {r.file_path} ({r.total_lines} lines)")

        lines.extend(["", "## Bottom 5 Files (need improvement)"])
        for r in sorted_files[-5:]:
            missing = ", ".join(r.missing_high_value) if r.missing_high_value else "none"
            lines.append(f"  ⚠️  {r.quality_score:.0%} — {r.file_path} (missing: {missing})")

    return "\n".join(lines)


def format_comparison_report(comparisons: list[ComparisonResult]) -> str:
    """Format a basic vs enhanced comparison report."""
    lines = [
        "# Basic vs Enhanced Context — Comparison Report",
        "",
        f"**Files compared**: {len(comparisons)}",
        "",
    ]

    if comparisons:
        avg_delta = sum(c.score_delta for c in comparisons) / len(comparisons)
        lines.append(f"**Average quality improvement**: +{avg_delta:.1%}")
        lines.append("")

        for comp in sorted(comparisons, key=lambda c: c.score_delta, reverse=True)[:10]:
            lines.extend([
                f"### {comp.file_path}",
                f"  Basic:    {comp.basic.quality_score:.0%} ({comp.basic.total_lines} lines)",
                f"  Enhanced: {comp.enhanced.quality_score:.0%} ({comp.enhanced.total_lines} lines)",
                f"  Delta:    +{comp.score_delta:.0%}",
            ])

            if comp.new_sections:
                lines.append(f"  New sections: {', '.join(comp.new_sections)}")
            if comp.richer_sections:
                lines.append(f"  Richer sections: {', '.join(comp.richer_sections)}")
            lines.append("")

    return "\n".join(lines)


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ContextSync Evaluation Harness")
    parser.add_argument("--repo", required=True, help="Path to repository")
    parser.add_argument("--depth-compare", action="store_true",
                        help="Compare basic vs enhanced scaffold quality")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    report = evaluate_repo(repo)
    print(format_eval_report(report))
