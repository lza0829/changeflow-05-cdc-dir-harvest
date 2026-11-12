from pathlib import Path

import pytest

from app.config import FIXTURES_DIR
from app.engines.harvest_scan import HarvestPathError, resolve_source_dir, scan_shards
from app.engines.parse_change import parse_change_text


def test_parse_rejects_duplicate_seq_within_shard():
    text = (
        '{"seq":1,"op":"upsert","entity_key":"A","event_ts":"t"}\n'
        '{"seq":1,"op":"upsert","entity_key":"B","event_ts":"t"}\n'
    )
    with pytest.raises(ValueError, match="duplicate seq"):
        parse_change_text(text, source="x.jsonl")


def test_scan_demo_finds_three_jsonl_shards():
    root = FIXTURES_DIR / "harvest_demo"
    shards = scan_shards(root)
    assert [s.rel_path for s in shards] == ["part-01.jsonl", "part-02.jsonl", "part-03.jsonl"]
    assert all(len(s.sha256) == 64 for s in shards)


def test_scan_ignores_non_jsonl():
    root = FIXTURES_DIR / "harvest_demo"
    names = {s.filename for s in scan_shards(root)}
    assert "README.txt" not in names


def test_resolve_rejects_outside_allowed_roots(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(HarvestPathError, match="outside allowed"):
        resolve_source_dir(str(outside))


def test_resolve_rejects_remote_like_path():
    with pytest.raises(HarvestPathError):
        resolve_source_dir("s3://bucket/cdc")


def test_resolve_demo_relative_name():
    resolved = resolve_source_dir("harvest_demo")
    assert resolved == (FIXTURES_DIR / "harvest_demo").resolve()
