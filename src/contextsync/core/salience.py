"""Salience Classifier — scores how important a change is for context updates."""

from __future__ import annotations

from dataclasses import dataclass

from contextsync.config import ChangeType as ConfigChangeType, SalienceConfig
from contextsync.core.diff_analyzer import ChangeType, FileChange


# Weight matrix: how much each change type contributes to salience
CHANGE_TYPE_WEIGHTS: dict[ChangeType, float] = {
    ChangeType.NEW_MODULE: 0.9,
    ChangeType.DELETED_MODULE: 0.9,
    ChangeType.API_CHANGE: 0.8,
    ChangeType.DEPENDENCY_CHANGE: 0.6,
    ChangeType.CONFIG_CHANGE: 0.5,
    ChangeType.REFACTOR: 0.4,
    ChangeType.BUGFIX: 0.2,
}


@dataclass
class SalienceResult:
    """Result of salience scoring for a file change."""
    file_path: str
    score: float
    should_update: bool
    reason: str
    change_type: ChangeType


class SalienceClassifier:
    """Scores the salience (importance) of code changes for context updates.

    Uses a rule-based approach with configurable weights and thresholds.
    """

    def __init__(self, config: SalienceConfig):
        self.config = config
        self.threshold = config.threshold

        # Map config change types to engine change types
        self._always_update = {
            ChangeType(ct.value) for ct in config.always_update_on
        }
        self._never_update = {
            ChangeType(ct.value) for ct in config.never_update_on
        }

    def score(self, change: FileChange) -> SalienceResult:
        """Score a single file change.

        Scoring formula:
            base_score = change_type_weight
            + line_bonus (0-0.1 based on change size)
            + function_bonus (0.1 per changed function, max 0.3)
            + class_bonus (0.15 per changed class, max 0.3)
            + import_bonus (0.05 per import change, max 0.2)
        """
        # Override: always update
        if change.change_type in self._always_update:
            return SalienceResult(
                file_path=change.path,
                score=1.0,
                should_update=True,
                reason=f"always_update_on: {change.change_type.value}",
                change_type=change.change_type,
            )

        # Override: never update
        if change.change_type in self._never_update:
            return SalienceResult(
                file_path=change.path,
                score=0.0,
                should_update=False,
                reason=f"never_update_on: {change.change_type.value}",
                change_type=change.change_type,
            )

        # Base score from change type
        base_score = CHANGE_TYPE_WEIGHTS.get(change.change_type, 0.3)

        # Line count bonus (larger changes are more salient)
        total_lines = change.added_lines + change.deleted_lines
        line_bonus = min(total_lines / 200, 0.1)  # Max 0.1 for 200+ lines

        # Function change bonus
        func_bonus = min(len(change.changed_functions) * 0.1, 0.3)

        # Class change bonus
        class_bonus = min(len(change.changed_classes) * 0.15, 0.3)

        # Import change bonus
        import_changes = len(change.new_imports) + len(change.removed_imports)
        import_bonus = min(import_changes * 0.05, 0.2)

        # Final score (capped at 1.0)
        score = min(base_score + line_bonus + func_bonus + class_bonus + import_bonus, 1.0)
        should_update = score >= self.threshold

        reason_parts = [f"type={change.change_type.value}({base_score:.2f})"]
        if func_bonus > 0:
            reason_parts.append(f"funcs={len(change.changed_functions)}(+{func_bonus:.2f})")
        if class_bonus > 0:
            reason_parts.append(f"classes={len(change.changed_classes)}(+{class_bonus:.2f})")
        if import_bonus > 0:
            reason_parts.append(f"imports={import_changes}(+{import_bonus:.2f})")
        if line_bonus > 0:
            reason_parts.append(f"lines={total_lines}(+{line_bonus:.2f})")

        return SalienceResult(
            file_path=change.path,
            score=round(score, 3),
            should_update=should_update,
            reason=", ".join(reason_parts),
            change_type=change.change_type,
        )

    def score_batch(self, changes: list[FileChange]) -> list[SalienceResult]:
        """Score a batch of file changes."""
        return [self.score(change) for change in changes]

    def filter_significant(self, changes: list[FileChange]) -> list[tuple[FileChange, SalienceResult]]:
        """Return only changes that are significant enough for context update."""
        results = []
        for change in changes:
            result = self.score(change)
            if result.should_update:
                results.append((change, result))
        return results
