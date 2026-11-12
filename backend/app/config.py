import os
from pathlib import Path

APP_NAME = "Changeflow"
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_FILENAME = "app.db"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# 默认巡检演示目录：仓库内多分片夹具。
HARVEST_DEMO_DIR = "harvest_demo"

# 允许被巡检的本机目录根。只允许本机目录 / 仓库夹具，不接受远程路径。
# 可通过 HARVEST_ROOTS 追加（os.pathsep 分隔），例如额外挂载的本地 CDC 落地目录。
HARVEST_ROOT_OFFICIAL = FIXTURES_DIR
_extra_roots = [
    Path(p).expanduser().resolve()
    for p in os.environ.get("HARVEST_ROOTS", "").split(os.pathsep)
    if p.strip()
]
HARVEST_ALLOWED_ROOTS: tuple[Path, ...] = (FIXTURES_DIR, DATA_DIR.resolve(), *_extra_roots)
