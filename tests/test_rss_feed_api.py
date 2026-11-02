import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from openbiliclaw.api.app import create_app, generate_rss_feed
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


def test_generate_rss_feed_xml_structure() -> None:
    items = [
        {
            "bvid": "BV123456",
            "title": "测试论文：大模型对齐实战",
            "author_name": "AI研究员",
            "source_platform": "arxiv",
            "content_url": "https://arxiv.org/abs/2401.00001",
            "description": "探讨大模型对齐中的关键技巧与评测准则。",
            "reason": "契合你对强化学习的兴趣",
            "published_at": 1730000000,
        }
    ]
    xml_str = generate_rss_feed(items, base_url="http://127.0.0.1:8420", channel_name="all")
    root = ET.fromstring(xml_str)

    assert root.tag == "rss"
    assert root.attrib.get("version") == "2.0"
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == "OpenBiliClaw 私人推荐目录"

    item_nodes = channel.findall("item")
    assert len(item_nodes) == 1
    assert item_nodes[0].findtext("title") == "测试论文：大模型对齐实战"
    assert item_nodes[0].findtext("link") == "https://arxiv.org/abs/2401.00001"
    assert item_nodes[0].findtext("author") == "AI研究员"
    assert item_nodes[0].findtext("category") == "arxiv"
    desc = item_nodes[0].findtext("description")
    assert desc is not None
    assert "探讨大模型对齐" in desc
    assert "契合你对强化学习的兴趣" in desc


def test_rss_feed_endpoint(test_client: tuple[TestClient, Database]) -> None:
    client, db = test_client
    # Empty DB response is valid XML
    res = client.get("/api/feed/rss")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    root = ET.fromstring(res.text)
    assert root.tag == "rss"
