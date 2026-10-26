"""Tests for the curated AI-frontier article wire."""

from __future__ import annotations

from types import SimpleNamespace

from openbiliclaw.discovery.frontier_wire import (
    FrontierWireItem,
    _arxiv_items,
    _hf_items,
    _hn_items,
    ingest_frontier_wire,
    wire_source_counts,
)

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2610.12345v1</id>
    <title>  A Long-Context Agent for Research  </title>
    <summary>We propose a long-context agent that plans and verifies its work.</summary>
    <published>2026-10-20T00:00:00Z</published>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <arxiv:primary_category term="cs.AI"/>
  </entry>
</feed>
"""

HF_PAYLOAD = [
    {
        "paper": {
            "id": "2610.12345",
            "title": "HF Daily Paper",
            "summary": "A community-curated paper abstract.",
            "authors": [{"name": "Carol"}, {"name": "Dave"}],
        },
        "publishedAt": "2026-10-20T00:00:00Z",
        "upvotes": 42,
    }
]

HN_PAYLOAD = {
    "hits": [
        {
            "objectID": "501",
            "title": "A new LLM inference trick",
            "url": "https://example.com/llm",
            "points": 250,
            "num_comments": 30,
            "author": "alice",
            "created_at": "2026-10-20T00:00:00Z",
        },
        {
            "objectID": "502",
            "title": "Best cooking tips",
            "points": 200,
        },
    ]
}


class _FakeCursor:
    def __init__(self, row: object = None) -> None:
        self._row = row

    def fetchone(self) -> object:
        return self._row


class _FakeDatabase:
    def __init__(self, *, exists: bool = False) -> None:
        self.exists = exists
        self.cached: list[tuple[str, dict[str, object]]] = []
        self.recommendations: list[dict[str, object]] = []

    @property
    def conn(self) -> SimpleNamespace:
        return SimpleNamespace(
            execute=lambda *_args, **_kwargs: _FakeCursor((1,) if self.exists else None)
        )

    def cache_content(self, bvid: str, **kwargs: object) -> None:
        self.cached.append((bvid, kwargs))

    def batch_insert_recommendations(self, items: list[dict[str, object]]) -> list[int]:
        self.recommendations.extend(items)
        return list(range(1, len(items) + 1))


def test_arxiv_parser_builds_a_paper_wire_item() -> None:
    items = _arxiv_items(ARXIV_XML, 5)

    assert len(items) == 1
    item = items[0]
    assert item.source_platform == "arxiv"
    assert item.content_id == "arxiv:2610.12345"
    assert item.content_url == "https://arxiv.org/abs/2610.12345"
    assert item.title == "A Long-Context Agent for Research"
    assert item.author_name == "Alice, Bob"
    assert "人工智能" in item.topic_label
    assert "arXiv" in item.tags


def test_hf_parser_builds_a_paper_wire_item() -> None:
    items = _hf_items(HF_PAYLOAD, 5)

    assert len(items) == 1
    assert items[0].source_platform == "huggingface"
    assert items[0].content_url == "https://huggingface.co/papers/2610.12345"
    assert items[0].source_metadata["upvotes"] == 42


def test_hn_parser_filters_non_ai_titles_and_keeps_points() -> None:
    items = _hn_items(HN_PAYLOAD, 5)

    assert len(items) == 1
    assert items[0].content_id == "hackernews:501"
    assert "250 分" in items[0].body_text
    assert items[0].source_metadata["points"] == 250


def test_ingest_writes_content_and_recommendation_rows() -> None:
    db = _FakeDatabase()
    item = FrontierWireItem(
        source_platform="arxiv",
        content_id="arxiv:2610.12345",
        content_url="https://arxiv.org/abs/2610.12345",
        title="A Paper",
        body_text="An abstract.",
        author_name="Alice",
        expression="arXiv 最新论文。",
        topic_label="AI 前沿 · 人工智能",
    )

    result = ingest_frontier_wire(db, [item])

    assert result == {"fetched": 1, "inserted": 1, "skipped": 0, "failed": 0}
    assert len(db.cached) == 1
    bvid, kwargs = db.cached[0]
    assert bvid == "arxiv:2610.12345"
    assert kwargs["source_platform"] == "arxiv"
    assert kwargs["content_type"] == "paper"
    assert kwargs["content_id"] == "2610.12345"
    assert kwargs["item_key"] == "arxiv:2610.12345"
    assert kwargs["pool_expression"] == "arXiv 最新论文。"
    assert kwargs["topic_group"] == "AI 前沿"
    assert db.recommendations[0]["bvid"] == "arxiv:2610.12345"
    assert db.recommendations[0]["topic"] == "AI 前沿 · 人工智能"


def test_ingest_skips_existing_content_identity() -> None:
    db = _FakeDatabase(exists=True)
    item = FrontierWireItem(
        source_platform="arxiv",
        content_id="arxiv:2610.12345",
        content_url="https://arxiv.org/abs/2610.12345",
        title="A Paper",
        body_text="An abstract.",
    )

    result = ingest_frontier_wire(db, [item])

    assert result == {"fetched": 1, "inserted": 0, "skipped": 1, "failed": 0}
    assert db.cached == []
    assert db.recommendations == []


def test_wire_source_counts() -> None:
    items = [
        FrontierWireItem("arxiv", "a1", "u1", "t1", "b1"),
        FrontierWireItem("arxiv", "a2", "u2", "t2", "b2"),
        FrontierWireItem("hackernews", "h1", "u3", "t3", "b3"),
    ]

    assert wire_source_counts(items) == {"arxiv": 2, "hackernews": 1}
