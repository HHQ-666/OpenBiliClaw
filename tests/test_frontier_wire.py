"""Tests for the curated AI-frontier article wire."""

from __future__ import annotations

from types import SimpleNamespace

from openbiliclaw.discovery.frontier_wire import (
    FrontierWireItem,
    _hf_model_items,
    _hn_items,
    _wire_topics,
    ingest_frontier_wire,
    wire_source_counts,
)

HF_MODELS_PAYLOAD = [
    {
        "id": "Qwen/Qwen3-32B",
        "likes": 420,
        "downloads": 120000,
        "pipeline_tag": "text-generation",
        "tags": ["text-generation", "qwen3", "conversational"],
        "createdAt": "2026-10-20T00:00:00Z",
    },
    {
        "id": "org/model-without-metadata",
        "likes": 0,
    },
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


def test_hf_model_parser_builds_a_runnable_release_item() -> None:
    items = _hf_model_items(HF_MODELS_PAYLOAD, 5)

    assert len(items) == 2
    item = items[0]
    assert item.source_platform == "huggingface"
    assert item.content_id == "huggingface:model:Qwen/Qwen3-32B"
    assert item.content_url == "https://huggingface.co/Qwen/Qwen3-32B"
    assert item.title.startswith("Qwen3-32B 开源模型")
    assert item.topic_label == "AI 前沿 · 开源模型"
    assert "本地运行" in item.body_text
    assert "下载 120000" in item.body_text
    assert item.source_metadata["model_id"] == "Qwen/Qwen3-32B"

    # A row without likes/downloads still renders a reason sentence.
    assert items[1].content_id == "huggingface:model:org/model-without-metadata"
    assert items[1].expression


def test_hn_parser_filters_non_ai_titles_and_keeps_points() -> None:
    items = _hn_items(HN_PAYLOAD, 5)

    assert len(items) == 1
    assert items[0].content_id == "hackernews:501"
    assert "250 分" in items[0].body_text
    assert items[0].source_metadata["points"] == 250


def test_hn_parser_rejects_paper_discussion_threads() -> None:
    payload = {
        "hits": [
            {
                "objectID": "601",
                "title": "arXiv paper on sparse attention (2026)",
                "points": 300,
            },
            {
                "objectID": "602",
                "title": "Open-weight LLM you can run on a laptop",
                "points": 320,
            },
        ]
    }

    items = _hn_items(payload, 5)

    assert [item.content_id for item in items] == ["hackernews:602"]


def test_ingest_writes_content_and_recommendation_rows() -> None:
    db = _FakeDatabase()
    item = FrontierWireItem(
        source_platform="huggingface",
        content_id="huggingface:model:org/model",
        content_url="https://huggingface.co/org/model",
        title="A Paper",
        body_text="An abstract.",
        author_name="Alice",
        expression="开源权重模型。",
        topic_label="AI 前沿 · 人工智能",
    )

    result = ingest_frontier_wire(db, [item])

    assert result == {"fetched": 1, "inserted": 1, "skipped": 0, "failed": 0}
    assert len(db.cached) == 1
    bvid, kwargs = db.cached[0]
    assert bvid == "huggingface:model:org/model"
    assert kwargs["source_platform"] == "huggingface"
    assert kwargs["content_type"] == "article"
    assert kwargs["content_id"] == "model:org/model"
    assert kwargs["item_key"] == "huggingface:model:org/model"
    assert kwargs["pool_expression"] == "开源权重模型。"
    assert kwargs["topic_group"] == "AI 前沿"
    assert db.recommendations[0]["bvid"] == "huggingface:model:org/model"
    assert db.recommendations[0]["topic"] == "AI 前沿 · 人工智能"


def test_ingest_skips_existing_content_identity() -> None:
    db = _FakeDatabase(exists=True)
    item = FrontierWireItem(
        source_platform="huggingface",
        content_id="huggingface:model:org/model",
        content_url="https://huggingface.co/org/model",
        title="A Paper",
        body_text="An abstract.",
    )

    result = ingest_frontier_wire(db, [item])

    assert result == {"fetched": 1, "inserted": 0, "skipped": 1, "failed": 0}
    assert db.cached == []
    assert db.recommendations == []


def test_wire_source_counts() -> None:
    items = [
        FrontierWireItem("huggingface", "a1", "u1", "t1", "b1"),
        FrontierWireItem("huggingface", "a2", "u2", "t2", "b2"),
        FrontierWireItem("hackernews", "h1", "u3", "t3", "b3"),
    ]

    assert wire_source_counts(items) == {"huggingface": 2, "hackernews": 1}


def test_wire_topics_are_deterministic_and_distinct() -> None:
    assert _wire_topics("DuoLM personalized recommendation", "user history") == ["推荐系统与个性化"]
    assert _wire_topics("DISC time-series dataset similarity", "forecasting") == ["时间序列与预测"]
    assert _wire_topics("A generic title", "no known topic") == []
    assert _wire_topics("SliderEdit++ image editing", "instruction-based editing")[:2] == [
        "多模态与视觉生成",
        "图像生成与编辑",
    ]
