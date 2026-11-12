import os
import tempfile
from pathlib import Path

# 必须在导入 app 之前设定，db.DB_PATH 在模块导入时解析。
_TMP_DATA = Path(tempfile.mkdtemp(prefix="changeflow-tests-"))
os.environ["DATA_DIR"] = str(_TMP_DATA)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    from app import db, seed

    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    seed.init_db()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
