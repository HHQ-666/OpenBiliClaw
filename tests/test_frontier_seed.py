"""Tests for the AI-frontier curated keyword seed."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from openbiliclaw.discovery.frontier_seed import (
    AI_FRONTIER_INTEREST_LABEL,
    AI_FRONTIER_SEED_REASON,
    FRONTIER_SEED_KEYWORDS,
    enabled_frontier_platforms,
    seed_frontier_keywords,
)

if TYPE_CHECKING:
    from pathlib import Path


def _sources(**enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        **{
            "bilibili": SimpleNamespace(enabled=enabled.get("bilibili", False)),
            "youtube": SimpleNamespace(enabled=enabled.get("youtube", False)),
            "github": SimpleNamespace(enabled=enabled.get("github", False)),
            "linuxdo": SimpleNamespace(enabled=enabled.get("linuxdo", False)),
            "weibo": SimpleNamespace(enabled=enabled.get("weibo", False)),
        }
    )


class _FakeKeywordStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.inserted = 0

    def insert_pending_keywords(
        self,
        platform: str,
        keywords: tuple[str, ...],
        digest: str,
        *,
        keyword_kind: str = "regular",
        metadata_by_keyword: object = None,
    ) -> int:
        self.calls.append(
            {
                "platform": platform,
                "keywords": keywords,
                "digest": digest,
                "keyword_kind": keyword_kind,
                "metadata": metadata_by_keyword,
            }
        )
        self.inserted += len(keywords)
        return len(keywords)


def test_enabled_frontier_platforms_only_returns_enabled_sources() -> None:
    platforms = enabled_frontier_platforms(_sources(youtube=True, github=True, linuxdo=True))

    assert platforms == ["youtube", "github", "linuxdo"]


def test_enabled_frontier_platforms_missing_config_is_disabled() -> None:
    # The fake SourcesConfig has no twitter/reddit attributes; those seeds
    # must not be attempted just because the module knows their keywords.
    platforms = enabled_frontier_platforms(_sources(youtube=True))

    assert "twitter" not in platforms
    assert "reddit" not in platforms


def test_seed_frontier_keywords_inserts_enabled_platforms_with_provenance() -> None:
    store = _FakeKeywordStore()

    inserted = seed_frontier_keywords(
        store,
        "digest-123",
        sources=_sources(youtube=True, bilibili=True),
    )

    assert inserted == len(FRONTIER_SEED_KEYWORDS["youtube"]) + len(
        FRONTIER_SEED_KEYWORDS["bilibili"]
    )
    assert [call["platform"] for call in store.calls] == ["bilibili", "youtube"]
    for call in store.calls:
        metadata = call["metadata"]
        assert isinstance(metadata, dict)
        for word in call["keywords"]:
            assert metadata[word]["source_interest"] == AI_FRONTIER_INTEREST_LABEL
            assert metadata[word]["generation_reason"] == AI_FRONTIER_SEED_REASON
        assert call["digest"] == "digest-123"
        assert call["keyword_kind"] == "regular"


def test_seed_frontier_keywords_skips_empty_digest() -> None:
    store = _FakeKeywordStore()

    assert seed_frontier_keywords(store, "  ", sources=_sources(youtube=True)) == 0
    assert store.calls == []


def test_seed_frontier_keywords_platform_override() -> None:
    store = _FakeKeywordStore()

    inserted = seed_frontier_keywords(store, "digest", platforms=["github", "unknown"])

    assert inserted == len(FRONTIER_SEED_KEYWORDS["github"])
    assert [call["platform"] for call in store.calls] == ["github"]


def test_seed_frontier_keywords_writes_real_pending_rows(
    tmp_path: Path,
) -> None:
    from openbiliclaw.storage.database import Database

    db = Database(tmp_path / "test.db")
    db.initialize()
    try:
        inserted = seed_frontier_keywords(db, "digest-real", platforms=["github"])

        assert inserted == len(FRONTIER_SEED_KEYWORDS["github"])
        assert db.count_pending_keywords("github", "digest-real") == inserted
    finally:
        db.close()


def test_frontier_seed_pack_has_no_generic_ai_only_queries() -> None:
    for platform, words in FRONTIER_SEED_KEYWORDS.items():
        assert words, platform
        assert len(words) <= 10, platform
        for word in words:
            assert word.strip()
            assert word not in {"AI", "人工智能", "大模型"}, (platform, word)
