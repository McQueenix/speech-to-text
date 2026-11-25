import os
import tempfile

# Use a throwaway SQLite DB for tests — set before the app is imported.
_db_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_dir}/test.db"
os.environ["GEMINI_API_KEY"] = ""
os.environ["FINAL_WAIT_SECONDS"] = "0.5"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
