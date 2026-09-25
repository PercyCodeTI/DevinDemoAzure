import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'test.db'}")
    monkeypatch.setenv("ADMIN_API_KEY", "chave-de-teste")
    monkeypatch.setenv("AMBIENTE", "test")
    os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

    from app.main import app

    with TestClient(app) as c:
        yield c
