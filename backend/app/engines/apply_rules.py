from __future__ import annotations

from typing import Any


def next_expected_seq(cursor: int) -> int:
    return int(cursor) + 1


def classify_event(
    *,
    event: dict[str, Any],
    cursor: int,
    already_applied: bool,
    gap_policy: str = "stop_quarantine",
) -> str:
    """默认策略：连续序应用；缺口停并隔离；重复序跳过。"""
    seq = int(event["seq"])
    if already_applied or seq <= cursor:
        return "skipped_duplicate"
    expected = next_expected_seq(cursor)
    if seq > expected:
        if gap_policy == "skip_gap":
            return "apply"  # 预留给 0-1；seed 默认 stop_quarantine
        return "quarantine_gap"
    if seq < expected:
        return "skipped_duplicate"
    return "apply"
