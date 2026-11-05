from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from openbiliclaw.api.app import create_app
from openbiliclaw.config import Config, LLMConfig, LLMProviderConfig, save_config
from openbiliclaw.storage.database import Database


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    config = Config(
        llm=LLMConfig(
            default_provider="openai",
            openai=LLMProviderConfig(api_key="sk-test", model="gpt-4o-mini"),
        ),
        data_dir=str(tmp_path),
    )
    save_config(config, tmp_path / "config.toml")
    monkeypatch.setenv("OPENBILICLAW_PROJECT_ROOT", str(tmp_path))
    db = Database(tmp_path / "test.db")
    db.initialize()
    memory = SimpleNamespace(load_cognition_updates=lambda: [])
    app = create_app(memory_manager=memory, database=db, soul_engine=object())
    return TestClient(app)


def test_blocked_authors_crud(test_client: TestClient) -> None:
    # 1. Initial list is empty
    res = test_client.get("/api/blocked-authors")
    assert res.status_code == 200
    assert res.json() == []

    # 2. Add blocked author
    res = test_client.post(
        "/api/blocked-authors",
        json={
            "author_name": "营销号小明",
            "source_platform": "bilibili",
            "author_id": "123456",
            "reason": "内容低质",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    blocked_id = data["id"]
    assert blocked_id > 0

    # 3. Check list contains item
    res = test_client.get("/api/blocked-authors")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["author_name"] == "营销号小明"
    assert items[0]["source_platform"] == "bilibili"
    assert items[0]["reason"] == "内容低质"

    # 4. Remove blocked author
    res = test_client.delete(f"/api/blocked-authors/{blocked_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # 5. List is empty again
    res = test_client.get("/api/blocked-authors")
    assert res.status_code == 200
    assert res.json() == []


def test_blocked_author_validation(test_client: TestClient) -> None:
    res = test_client.post(
        "/api/blocked-authors",
        json={"author_name": ""},
    )
    assert res.status_code == 422
