"""Tests for the persistent card-text translation cache."""

from __future__ import annotations

import sqlite3

from openbiliclaw.storage.text_translation_cache import (
    TextTranslationCache,
    translation_cache_key,
)


class _MemoryDatabase:
    """Shared in-memory SQLite stand-in for ``Database.open_connection()``."""

    def __init__(self) -> None:
        self.uri = f"file:translation-cache-{id(self)}?mode=memory&cache=shared"
        self.fail_reads = False
        # A shared in-memory database disappears with its last connection, so
        # the "database" holds one open for its own lifetime.
        self.keepalive = self.open_connection()

    def open_connection(self) -> sqlite3.Connection:
        if self.fail_reads:
            raise sqlite3.OperationalError("database is locked")
        conn = sqlite3.connect(self.uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def test_cache_round_trips_renderings() -> None:
    cache = TextTranslationCache(_MemoryDatabase())  # type: ignore[arg-type]
    key = translation_cache_key("this is a tweet body")
    assert cache.get_many([key]) == {}
    assert cache.put_many({key: ("this is a tweet body", "这是一条推文")}) == 1
    assert cache.get_many([key]) == {key: "这是一条推文"}


def test_cache_key_ignores_whitespace_differences() -> None:
    assert translation_cache_key("hello   world\n") == translation_cache_key("hello world")
    assert translation_cache_key("hello world") != translation_cache_key("hello worlds")


def test_cache_survives_a_second_store_over_the_same_database() -> None:
    db = _MemoryDatabase()
    first = TextTranslationCache(db)  # type: ignore[arg-type]
    key = translation_cache_key("long english title")
    first.put_many({key: ("long english title", "很长的英文标题")})
    second = TextTranslationCache(db)  # type: ignore[arg-type]
    assert second.get_many([key]) == {key: "很长的英文标题"}


def test_cache_skips_empty_renderings_and_returns_hit_count() -> None:
    cache = TextTranslationCache(_MemoryDatabase())  # type: ignore[arg-type]
    written = cache.put_many(
        {
            translation_cache_key("kept"): ("kept", "留下"),
            translation_cache_key("dropped"): ("dropped", "   "),
        }
    )
    assert written == 1
    assert cache.get_many([translation_cache_key("dropped")]) == {}


def test_cache_reads_and_writes_degrade_to_nothing() -> None:
    """A presentation cache must never raise into the request path."""

    db = _MemoryDatabase()
    cache = TextTranslationCache(db)  # type: ignore[arg-type]
    db.fail_reads = True
    assert cache.get_many([translation_cache_key("anything")]) == {}
    assert cache.put_many({translation_cache_key("anything"): ("anything", "任何")}) == 0


def test_cache_handles_empty_input() -> None:
    cache = TextTranslationCache(_MemoryDatabase())  # type: ignore[arg-type]
    assert cache.get_many([]) == {}
    assert cache.get_many(["", "   "]) == {}
    assert cache.put_many({}) == 0


def test_cache_upsert_replaces_an_existing_rendering() -> None:
    cache = TextTranslationCache(_MemoryDatabase())  # type: ignore[arg-type]
    key = translation_cache_key("rewritten line")
    cache.put_many({key: ("rewritten line", "第一版")})
    cache.put_many({key: ("rewritten line", "第二版")})
    assert cache.get_many([key]) == {key: "第二版"}


def test_cache_truncates_the_stored_source_text_only() -> None:
    db = _MemoryDatabase()
    cache = TextTranslationCache(db)  # type: ignore[arg-type]
    source = "s" * 5000
    key = translation_cache_key(source)
    cache.put_many({key: (source, "渲染")})
    with db.open_connection() as conn:
        stored = conn.execute(
            "SELECT length(source_text) AS n FROM text_translations WHERE text_hash = ?",
            (key,),
        ).fetchone()
    assert stored is not None
    assert int(stored["n"]) == 2000
    assert cache.get_many([key]) == {key: "渲染"}
