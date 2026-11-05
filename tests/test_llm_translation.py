"""Tests for display-time card text translation (prompt, parsing, budgeting)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from openbiliclaw.llm.translation import (
    MAX_TEXTS_PER_CALL,
    MAX_TRANSLATABLE_CHARS,
    build_translation_messages,
    chunk_translation_entries,
    needs_translation,
    parse_translation_items,
    translatable_excerpt,
    translate_batch,
)


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, content: str = "", *, raises: Exception | None = None) -> None:
        self.content = content
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    async def complete_structured_task(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return _Response(self.content)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("this is pure f*cking insane", True),
        ("7 RAG Design Patterns You Should Know", True),
        ("PostgreSQL connection pool tuning notes", True),
        # Already readable: a Chinese card must never spend an LLM call.
        ("这条推文在聊 RAG 的检索策略", False),
        # Fragments, numbers, and links carry no meaning worth a call.
        ("v2.0", False),
        ("https://x.com/foo/status/123", False),
        ("3.4k", False),
        ("🎉🎉🎉", False),
        ("", False),
        ("   ", False),
        # Mixed scripts are handled by the translation itself, not by the card.
        ("RAG 是什么", False),
    ],
)
def test_needs_translation_only_for_readable_foreign_text(text: str, expected: bool) -> None:
    assert needs_translation(text) is expected


def test_translatable_excerpt_caps_length_and_keeps_words_whole() -> None:
    long_text = " ".join(f"word{index}" for index in range(400))
    excerpt = translatable_excerpt(long_text)
    assert len(excerpt) <= MAX_TRANSLATABLE_CHARS
    assert long_text.startswith(excerpt)
    # Cut on a boundary: no half word reaches the model.
    assert not excerpt.endswith("wor")
    assert " " not in excerpt[-1]


def test_translatable_excerpt_leaves_short_text_untouched() -> None:
    assert translatable_excerpt("  hello world  ") == "hello world"


def test_chunk_translation_entries_respects_item_and_char_budgets() -> None:
    entries = [(str(index), "x" * 100) for index in range(MAX_TEXTS_PER_CALL * 2 + 1)]
    batches = chunk_translation_entries(entries)
    assert [len(batch) for batch in batches] == [
        MAX_TEXTS_PER_CALL,
        MAX_TEXTS_PER_CALL,
        1,
    ]

    huge = [(str(index), "y" * 2000) for index in range(4)]
    char_batches = chunk_translation_entries(huge)
    assert all(sum(len(text) for _, text in batch) <= 3000 for batch in char_batches)
    assert sum(len(batch) for batch in char_batches) == 4


def test_chunk_translation_entries_keeps_one_oversized_entry_alone() -> None:
    batches = chunk_translation_entries([("a", "z" * 5000)])
    assert batches == [[("a", "z" * 5000)]]


def test_build_translation_messages_carries_ids_and_static_system_prompt() -> None:
    messages = build_translation_messages([("0", "hello world"), ("1", "second line")])
    assert messages[0]["role"] == "system"
    assert "json" in messages[0]["content"]
    user = messages[1]["content"]
    assert '<item id="0">' in user
    assert '<item id="1">' in user
    assert "hello world" in user


def test_parse_translation_items_reads_id_keyed_payload() -> None:
    payload = json.dumps(
        {
            "translations": [
                {"id": "0", "zh": "这是纯粹疯了"},
                {"id": "1", "zh": "第二个"},
                {"id": "9", "zh": "不该出现"},
            ]
        }
    )
    assert parse_translation_items(payload, ["0", "1"]) == {
        "0": "这是纯粹疯了",
        "1": "第二个",
    }


def test_parse_translation_items_tolerates_wrapped_and_partial_payloads() -> None:
    assert parse_translation_items('[{"id": "a", "translation": "甲"}]', ["a"]) == {"a": "甲"}
    # An id the model never answered is absent, not empty — the caller keeps
    # the original text for it.
    assert parse_translation_items('[{"id": "a", "zh": "甲"}]', ["a", "b"]) == {"a": "甲"}
    assert parse_translation_items("not json at all", ["a"]) == {}
    assert parse_translation_items("", ["a"]) == {}


@pytest.mark.asyncio
async def test_translate_batch_returns_renderings_and_uses_the_translation_caller() -> None:
    llm = _FakeLLM(json.dumps([{"id": "0", "zh": "零"}, {"id": "1", "zh": "一"}]))
    rendered = await translate_batch(llm, [("0", "zero"), ("1", "one")])
    assert rendered == {"0": "零", "1": "一"}
    call = llm.calls[0]
    assert call["caller"] == "recommendation.translate_card_text"
    assert call["reasoning_effort"] == ""
    assert call["inject_core_memory"] is False


@pytest.mark.asyncio
async def test_translate_batch_swallows_provider_failure() -> None:
    llm = _FakeLLM(raises=RuntimeError("provider exploded"))
    assert await translate_batch(llm, [("0", "zero")]) == {}


@pytest.mark.asyncio
async def test_translate_batch_gives_up_on_timeout() -> None:
    class _SlowLLM:
        async def complete_structured_task(self, **_kwargs: Any) -> _Response:
            await asyncio.sleep(1)
            return _Response("[]")

    assert await translate_batch(_SlowLLM(), [("0", "zero")], timeout=0.01) == {}


@pytest.mark.asyncio
async def test_translate_batch_no_ops_without_a_service_or_entries() -> None:
    assert await translate_batch(None, [("0", "zero")]) == {}
    assert await translate_batch(_FakeLLM("[]"), []) == {}
    assert await translate_batch(object(), [("0", "zero")]) == {}
