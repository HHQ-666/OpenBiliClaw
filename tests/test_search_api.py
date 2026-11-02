from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from openbiliclaw.api.app import create_app
from openbiliclaw.config import Config, LLMConfig, LLMProviderConfig, save_config
from openbiliclaw.storage.database import Database


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[TestClient, Database]:
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
    return TestClient(app), db


def test_search_content_database_and_api(test_client: tuple[TestClient, Database]) -> None:
    client, db = test_client

    # Insert items into content_cache
    db.conn.execute(
        """
        INSERT INTO content_cache (
            bvid, item_key, title, author_name, up_name, source_platform,
            description, pool_topic_label, relevance_score
        ) VALUES
        (
            'BV_S1', 'bilibili:BV_S1', 'Python 高性能异步架构设计与实践',
            '老李聊架构', '老李聊架构', 'bilibili',
            '全面解析 asyncio 与 uvloop 的性能边界。', '编程技术', 0.92
        ),
        (
            'BV_S2', 'arxiv:2402.1234', 'Direct Preference Optimization for LLMs',
            'Rafailov et al.', '', 'arxiv',
            'A lightweight approach to fine-tuning language models with human feedback.',
            '机器学习', 0.95
        ),
        (
            'BV_S3', 'bilibili:BV_S3', '劣质营销号标题党日常',
            '营销号大本营', '营销号大本营', 'bilibili',
            '毫无价值的内容。', '搞笑', 0.1
        )
        """
    )
    db.conn.commit()

    # Search for "异步"
    res = client.get("/api/search?q=异步")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["bvid"] == "BV_S1"
    assert "Python" in items[0]["title"]

    # Search for "LLM"
    res = client.get("/api/search?q=LLM")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["bvid"] == "BV_S2"

    # Search empty string
    res = client.get("/api/search?q=")
    assert res.status_code == 200
    assert res.json() == []

    # Block an author and verify it gets excluded from search
    db.add_blocked_author("营销号大本营", source_platform="bilibili")
    res = client.get("/api/search?q=营销号")
    assert res.status_code == 200
    assert res.json() == []
