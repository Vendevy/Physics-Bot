"""SM-2 spaced repetition.

`grade` is 0..5:
  0 = blackout, 1-2 = wrong, 3 = correct with serious difficulty,
  4 = correct after hesitation, 5 = perfect recall.

Mastery score is a separate 0..1 EMA used for "weakest topic" selection.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def update_sm2(
    *,
    ease: float,
    interval_days: int,
    repetitions: int,
    grade: int,
) -> tuple[float, int, int]:
    """Return (new_ease, new_interval_days, new_repetitions)."""
    grade = max(0, min(5, grade))

    if grade < 3:
        new_reps = 0
        new_interval = 1
    else:
        new_reps = repetitions + 1
        if new_reps == 1:
            new_interval = 1
        elif new_reps == 2:
            new_interval = 6
        else:
            new_interval = max(1, round(interval_days * ease))

    new_ease = ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    new_ease = max(1.3, new_ease)

    return new_ease, new_interval, new_reps


def update_mastery(prev: float, grade: int) -> float:
    """EMA of normalized grade. grade/5, alpha=0.4."""
    target = grade / 5.0
    return round(0.6 * prev + 0.4 * target, 4)


def next_review_iso(interval_days: int) -> str:
    return (_now() + timedelta(days=interval_days)).date().isoformat()


def today_iso() -> str:
    return _now().date().isoformat()
