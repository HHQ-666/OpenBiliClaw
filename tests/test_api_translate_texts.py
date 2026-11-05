"""Tests for /api/translate-texts — the card-text Chinese rendering endpoint."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from openbiliclaw.api.app import create_app
from openbiliclaw.storage.text_translation_cache import translation_cache_key

if TYPE_CHECKING:
    from pathlib import Path


class _MemoryDatabase:
    """Shared in-memory SQLite stand-in for ``Database.open_connection()``."""

    def __init__(self) -> None:
        self.uri = f"file:translate-api-{id(self)}?mode=memory&cache=shared"
        self.keepalive = self.open_connection()

    def open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """Records calls and answers with a per-batch JSON rendering."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raises = raises

    async def complete_structured_task(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        # Echo one rendering per requested id, so tests can assert on the wire
        # contract (ids in, ids out) rather than on a canned array.
        user_input = str(kwargs.get("user_input", ""))
        ids = [
            line.split('"')[1] for line in user_input.splitlines() if line.startswith("<item id=")
        ]
        return _Response(json.dumps([{"id": item_id, "zh": f"译文{item_id}"} for item_id in ids]))


class _FakeRecommendationEngine:
    def __init__(self, llm: Any) -> None:
        self._llm = llm


def _build_client(
    database: Any,
    *,
    llm: Any | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            memory_manager=object(),
            database=database,
            soul_engine=object(),
            recommendation_engine=(_FakeRecommendationEngine(llm) if llm is not None else None),
        )
    )


@pytest.fixture(autouse=True)
def _isolate_runtime_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep create_app() route tests independent from local credentials."""

    from openbiliclaw.config import Config, save_config

    project_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENBILICLAW_PROJECT_ROOT", str(project_root))
    cfg = Config()
    cfg.llm.default_provider = "ollama"
    cfg.llm.ollama.model = "llama3"
    save_config(cfg, project_root / "config.toml")


def test_chinese_and_fragment_text_never_reach_the_llm() -> None:
    llm = _FakeLLM()
    client = _build_client(_MemoryDatabase(), llm=llm)
    resp = client.post(
        "/api/translate-texts",
        json={
            "items": [
                {"id": "0", "text": "这条已经是中文了"},
                {"id": "1", "text": "v2.0"},
                {"id": "2", "text": "https://x.com/foo/status/1"},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"translations": {}, "pending": [], "cached": False}
    assert llm.calls == []


def test_cache_hit_answers_without_calling_the_llm() -> None:
    database = _MemoryDatabase()
    source = "7 RAG Design Patterns You Should Know"
    with database.open_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS text_translations ("
            "text_hash TEXT PRIMARY KEY, source_text TEXT NOT NULL DEFAULT '', "
            "text_zh TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO text_translations (text_hash, source_text, text_zh) VALUES (?, ?, ?)",
            (translation_cache_key(source), source, "你该知道的 7 种 RAG 设计模式"),
        )
        conn.commit()

    llm = _FakeLLM()
    client = _build_client(database, llm=llm)
    resp = client.post("/api/translate-texts", json={"items": [{"id": "a", "text": source}]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["translations"] == {"a": "你该知道的 7 种 RAG 设计模式"}
    assert body["pending"] == []
    assert body["cached"] is True
    assert llm.calls == []


def test_cold_cache_translates_then_serves_the_next_request_from_cache() -> None:
    database = _MemoryDatabase()
    llm = _FakeLLM()
    client = _build_client(database, llm=llm)
    payload = {
        "items": [
            {"id": "title", "text": "PostgreSQL connection pool tuning notes"},
            {"id": "body", "text": "I thought PostgreSQL's connection pool was the bottleneck."},
        ]
    }
    first = client.post("/api/translate-texts", json=payload).json()
    assert first["translations"] == {"title": "译文0", "body": "译文1"}
    assert first["pending"] == []
    assert len(llm.calls) == 1

    second = client.post("/api/translate-texts", json=payload).json()
    assert second["translations"] == {"title": "译文0", "body": "译文1"}
    assert second["cached"] is True
    # The whole point of the cache: a re-render costs no further LLM calls.
    assert len(llm.calls) == 1


def test_identical_texts_collapse_onto_one_translation() -> None:
    llm = _FakeLLM()
    client = _build_client(_MemoryDatabase(), llm=llm)
    resp = client.post(
        "/api/translate-texts",
        json={
            "items": [
                {"id": "0", "text": "same english sentence here"},
                {"id": "1", "text": "same   english sentence here"},
            ]
        },
    ).json()
    assert resp["translations"] == {"0": "译文0", "1": "译文0"}
    # One cache key, so one item on the wire (the excerpt deduplicates too).
    assert llm.calls[0]["user_input"].count("<item id=") == 1


def test_without_a_chat_capable_llm_the_original_text_is_kept() -> None:
    client = _build_client(_MemoryDatabase())
    resp = client.post(
        "/api/translate-texts",
        json={"items": [{"id": "0", "text": "an english sentence to render"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["translations"] == {}
    # Pending tells the caller "ask again later", not "this failed".
    assert body["pending"] == ["0"]


def test_llm_failure_degrades_to_pending_instead_of_an_error() -> None:
    llm = _FakeLLM(raises=RuntimeError("provider exploded"))
    client = _build_client(_MemoryDatabase(), llm=llm)
    resp = client.post(
        "/api/translate-texts",
        json={"items": [{"id": "0", "text": "an english sentence to render"}]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"translations": {}, "pending": ["0"], "cached": False}


def test_request_budget_leaves_the_rest_pending() -> None:
    """A cold 20-card tray cannot hold the request for a dozen batches."""

    llm = _FakeLLM()
    client = _build_client(_MemoryDatabase(), llm=llm)
    items = [
        {"id": str(index), "text": f"english card text number {index} for the tray"}
        for index in range(20)
    ]
    body = client.post("/api/translate-texts", json={"items": items}).json()
    # 8 per call, at most 2 calls per request.
    assert len(llm.calls) == 2
    assert len(body["translations"]) == 16
    assert len(body["pending"]) == 4
    # The deferred ids are exactly the ones with no rendering yet.
    assert set(body["pending"]).isdisjoint(body["translations"])

    # The next render picks the rest up (and the cache keeps the first 16 free).
    second = client.post("/api/translate-texts", json={"items": items}).json()
    assert sorted(int(key) for key in second["translations"]) == list(range(20))
    assert second["pending"] == []


def test_response_rejects_extra_fields_and_oversized_batches() -> None:
    client = _build_client(_MemoryDatabase())
    assert (
        client.post(
            "/api/translate-texts",
            json={"items": [{"id": "0", "text": "an english sentence", "junk": 1}]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/translate-texts",
            json={"items": [{"id": str(i), "text": "english sentence here"} for i in range(61)]},
        ).status_code
        == 422
    )
    assert client.post("/api/translate-texts", json={"items": []}).status_code == 200
