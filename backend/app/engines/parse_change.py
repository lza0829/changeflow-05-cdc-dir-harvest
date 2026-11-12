from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_change_fixture(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"fixture missing: {path}")
    events: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid jsonl at line {line_no}: {exc}") from exc
        for key in ("seq", "op", "entity_key", "event_ts"):
            if key not in obj:
                raise ValueError(f"missing {key} at line {line_no}")
        op = str(obj["op"]).lower()
        if op not in ("upsert", "delete"):
            raise ValueError(f"unsupported op at line {line_no}: {op}")
        events.append(
            {
                "seq": int(obj["seq"]),
                "op": op,
                "entity_key": str(obj["entity_key"]),
                "event_ts": str(obj["event_ts"]),
                "payload": obj.get("payload") or {},
            }
        )
    events.sort(key=lambda e: e["seq"])
    return events
