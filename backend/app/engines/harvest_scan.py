from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.config import HARVEST_ALLOWED_ROOTS, FIXTURES_DIR


CDC_SUFFIXES = (".jsonl",)
MAX_SHARD_BYTES = 32 * 1024 * 1024


class HarvestPathError(ValueError):
    pass


@dataclass(frozen=True)
class ScannedShard:
    filename: str
    rel_path: str
    path: Path
    sha256: str
    size_bytes: int


def resolve_source_dir(source_dir: str) -> Path:
    """把用户输入的目录解析为已存在的本机绝对路径，并限制在允许根内。"""
    if not source_dir or not source_dir.strip():
        raise HarvestPathError("source_dir is required")
    raw = source_dir.strip()
    candidate = Path(raw).expanduser()
    roots: list[Path] = [FIXTURES_DIR]
    roots.extend(HARVEST_ALLOWED_ROOTS)
    if not candidate.is_absolute():
        # 相对路径：先按仓库夹具根解析；不存在再按 DATA_DIR。
        resolved = None
        for root in roots:
            trial = (root / candidate).resolve()
            if trial.exists():
                resolved = trial
                break
        if resolved is None:
            resolved = (FIXTURES_DIR / candidate).resolve()
    else:
        resolved = candidate.resolve()

    if not resolved.exists():
        raise HarvestPathError(f"source_dir not found: {raw}")
    if not resolved.is_dir():
        raise HarvestPathError(f"source_dir is not a directory: {raw}")

    allowed = False
    for root in roots:
        try:
            resolved.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise HarvestPathError(
            f"source_dir outside allowed local roots: {resolved}"
        )
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_shards(source_dir: Path) -> list[ScannedShard]:
    """递归扫描目录下的 CDC jsonl 分片（只读本机文件系统，不跟随符号链接）。"""
    if not source_dir.is_dir():
        raise HarvestPathError(f"not a directory: {source_dir}")
    shards: list[ScannedShard] = []
    for dirpath, _dirnames, filenames in _walk_sorted(source_dir):
        for filename in filenames:
            if not filename.lower().endswith(CDC_SUFFIXES):
                continue
            path = dirpath / filename
            try:
                if path.is_symlink():
                    continue
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > MAX_SHARD_BYTES:
                continue
            rel = path.relative_to(source_dir).as_posix()
            shards.append(
                ScannedShard(
                    filename=filename,
                    rel_path=rel,
                    path=path,
                    sha256=_sha256_file(path),
                    size_bytes=stat.st_size,
                )
            )
    shards.sort(key=lambda s: s.rel_path)
    return shards


def _walk_sorted(source_dir: Path):
    # 确定性遍历：目录名按字典序，避免不同机器顺序差异。
    for dirpath, dirnames, filenames in sorted(
        ((Path(dp), dn, fn) for dp, dn, fn in _os_walk(source_dir)),
        key=lambda t: str(t[0]),
    ):
        dirnames.sort()
        filenames.sort()
        yield dirpath, dirnames, filenames


def _os_walk(root: Path):
    import os

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        yield Path(dirpath), dirnames, filenames
