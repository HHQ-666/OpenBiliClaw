"""Digest API routes: archive list/detail/latest + manual run-now trigger."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from openbiliclaw.api.app import create_app
from openbiliclaw.config import Config, LLMConfig, LLMProviderConfig, save_config
from openbiliclaw.storage.database import Database

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


def _make_client(monkeypatch: MonkeyPatch, tmp_path: Path) -> tuple[TestClient, Database]:
    config = Config(
        llm=LLMConfig(
            default_provider="openai",
            openai=LLMProviderConfig(api_key="sk-test", model="gpt-4o-mini"),
        ),
        data_dir=str(tmp_path),
    )
    save_config(config, tmp_path / "config.toml")
    monkeypatch.setenv("OPENBILICLAW_PROJECT_ROOT", str(tmp_path))
    db = Database(tmp_path / "digest.db")
    db.initialize()
    memory = SimpleNamespace(load_cognition_updates=lambda: [])
    app = create_app(memory_manager=memory, database=db, soul_engine=object())
    return TestClient(app), db


def _insert_pool_row(db: Database, bvid: str, title: str) -> None:
    db.conn.execute(
        """INSERT INTO content_cache
               (bvid, title, content_url, source_platform, pool_status,
                pool_expression, pool_topic_label, style_key, topic_group,
                relevance_score)
           VALUES (?, ?, ?, 'bilibili', 'fresh', ?, 'AI', 'tech', 'ai', 0.9)""",
        (bvid, title, f"https://www.bilibili.com/video/{bvid}", f"很对{title}口味"),
    )
    db.conn.commit()


def test_digest_routes_404_when_empty(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)

    assert client.get("/api/digest").json()["issues"] == []
    assert client.get("/api/digest/latest").status_code == 404
    assert client.get("/api/digest/999").status_code == 404


def test_run_now_creates_and_lists_issue(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, db = _make_client(monkeypatch, tmp_path)
    _insert_pool_row(db, "BV1test1", "测试视频")

    response = client.post("/api/digest/run-now")

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["issue"]["item_count"] == 1
    assert body["issue"]["payload"]["top_picks"][0]["title"] == "测试视频"

    listed = client.get("/api/digest").json()["issues"]
    assert len(listed) == 1
    assert listed[0]["digest_date"] == datetime.now().strftime("%Y-%m-%d")

    latest = client.get("/api/digest/latest")
    assert latest.status_code == 200
    assert latest.json()["title"] == body["issue"]["title"]

    detail = client.get(f"/api/digest/{body['issue']['id']}")
    assert detail.status_code == 200
    assert detail.json()["body_text"].startswith("【高分推荐】")


def test_run_now_without_content_reports_not_created(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)

    response = client.post("/api/digest/run-now")

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is False
    assert "没有可汇总" in body["message"]
    assert body["issue"] is None


def test_run_now_records_delivery_results(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, db = _make_client(monkeypatch, tmp_path)
    _insert_pool_row(db, "BV1test2", "测试视频2")
    # Simulate configured-but-failing channels via config webhook URL; the
    # channel POST will fail fast on an unroutable host — but to keep the test
    # hermetic, point it at the local test server itself (404 route → HTTP 404
    # counts as channel failure detail, no external network).
    client.put(
        "/api/config",
        json={"digest": {"webhook_url": "http://127.0.0.1:9/digest-hook"}},
    )

    response = client.post("/api/digest/run-now")

    body = response.json()
    assert body["created"] is True
    assert body["delivery"][0]["channel"] == "webhook"
    assert body["delivery"][0]["ok"] is False
    stored = db.get_latest_digest_issue()
    assert stored is not None
    assert stored["delivery"][0]["ok"] is False
