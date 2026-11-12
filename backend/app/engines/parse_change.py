from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_change_text(text: str, *, source: str = "<text>") -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid jsonl in {source} at line {line_no}: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"invalid jsonl in {source} at line {line_no}: not an object")
        for key in ("seq", "op", "entity_key", "event_ts"):
            if key not in obj:
                raise ValueError(f"missing {key} in {source} at line {line_no}")
        op = str(obj["op"]).lower()
        if op not in ("upsert", "delete"):
            raise ValueError(f"unsupported op in {source} at line {line_no}: {op}")
        try:
            seq = int(obj["seq"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"non-integer seq in {source} at line {line_no}") from exc
        events.append(
            {
                "seq": seq,
                "op": op,
                "entity_key": str(obj["entity_key"]),
                "event_ts": str(obj["event_ts"]),
                "payload": obj.get("payload") or {},
            }
        )
    seen: set[int] = set()
    for event in events:
        if event["seq"] in seen:
            raise ValueError(f"duplicate seq {event['seq']} within {source}")
        seen.add(event["seq"])
    events.sort(key=lambda e: e["seq"])
    return events


def parse_change_fixture(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"fixture missing: {path}")
    return parse_change_text(path.read_text(encoding="utf-8"), source=str(path))
