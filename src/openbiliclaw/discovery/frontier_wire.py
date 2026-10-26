"""Curated high-quality AI-frontier wire.

The recommendation pool is fed by social/video platforms, which is good for
"what people are talking about" but weak on primary sources. This module adds
a small, explicitly curated wire for the ``AI 前沿`` channel:

* arXiv (cs.AI / cs.CL / cs.LG) — primary research, latest submissions.
* Hugging Face Daily Papers — community-curated research picks.
* Hacker News (points > 100, last 14 days) — engineering-community discussion.

Items are inserted as normal ``content_cache`` rows with a deterministic
Chinese recommendation copy, then a normal ``recommendations`` history row.
They therefore keep working with feedback, saving, the channel classifier and
the existing card surfaces; no separate reader is introduced. The wire is
throttled by the API caller and skips any content identity already stored.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from openbiliclaw.network import outbound_httpx_kwargs
from openbiliclaw.saved_sync.identity import make_item_key

if TYPE_CHECKING:
    from collections.abc import Iterable

ARXIV_URL = "https://export.arxiv.org/api/query"
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

_ARXIV_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
logger = logging.getLogger(__name__)

_HN_FRONTIER_TERMS = re.compile(
    r"(?<![a-z0-9])(?:llm|llms|model|models|agent|agents|claude|gpt|gemini|"
    r"deepseek|qwen|kimi|llama|mistral|open[- ]weight|inference|neural|"
    r"transformer|multimodal|benchmark|training|fine[- ]tun|quantiz|reasoning|"
    r"context window|mcp|alignment|diffusion|vla|robot)(?![a-z0-9])",
    re.IGNORECASE,
)
_HN_COMMENTARY = re.compile(
    r"controversial take|is a tool|opinion|essay|hiring|policy|regulation|"
    r"lawsuit|copyright|layoffs|stock|funding|interview",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FrontierWireItem:
    """One curated article before it enters the local content cache."""

    source_platform: str
    content_id: str
    content_url: str
    title: str
    body_text: str
    author_name: str = ""
    published_at: str = ""
    tags: tuple[str, ...] = ()
    score: float = 0.0
    topic_label: str = "AI 前沿 · 论文"
    expression: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)


def _clean(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _iso(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _arxiv_items(payload: str, limit: int) -> list[FrontierWireItem]:
    root = ET.fromstring(payload)
    items: list[FrontierWireItem] = []
    for entry in root.findall("a:entry", _ARXIV_NS)[:limit]:
        raw_id = _clean(entry.findtext("a:id", default="", namespaces=_ARXIV_NS))
        paper_id = raw_id.rsplit("/", 1)[-1]
        paper_id = re.sub(r"v\d+$", "", paper_id)
        title = _clean(entry.findtext("a:title", default="", namespaces=_ARXIV_NS))
        summary = _clean(entry.findtext("a:summary", default="", namespaces=_ARXIV_NS))
        if not paper_id or not title:
            continue
        authors = [
            _clean(node.text)
            for node in entry.findall("a:author/a:name", _ARXIV_NS)
            if _clean(node.text)
        ]
        primary = entry.find("arxiv:primary_category", _ARXIV_NS)
        category = _clean(primary.get("term") if primary is not None else "")
        category_label = {
            "cs.AI": "人工智能",
            "cs.CL": "计算语言学",
            "cs.LG": "机器学习",
        }.get(category, "AI 研究")
        items.append(
            FrontierWireItem(
                source_platform="arxiv",
                content_id=f"arxiv:{paper_id}",
                content_url=f"https://arxiv.org/abs/{paper_id}",
                title=title,
                body_text=summary,
                author_name=", ".join(authors[:3]),
                published_at=_iso(entry.findtext("a:published", default="", namespaces=_ARXIV_NS)),
                tags=tuple(x for x in ("arXiv", category, category_label) if x),
                score=0.9,
                topic_label=f"AI 前沿 · {category_label}",
                expression=(
                    f"arXiv 最新论文，方向是{category_label}。摘要已附在卡片里，"
                    "适合先扫一遍方法和结论，再决定要不要细读。"
                ),
                source_metadata={"wire": "arxiv", "category": category, "authors": authors[:8]},
            )
        )
    return items


def _hf_items(payload: object, limit: int) -> list[FrontierWireItem]:
    rows = payload if isinstance(payload, list) else []
    items: list[FrontierWireItem] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        raw_paper = row.get("paper")
        paper: dict[str, Any] = raw_paper if isinstance(raw_paper, dict) else {}
        paper_id = _clean(paper.get("id") or row.get("id"))
        title = _clean(row.get("title") or paper.get("title"))
        summary = _clean(paper.get("summary") or row.get("summary"))
        if not paper_id or not title:
            continue
        authors = [
            _clean(author.get("name"))
            for author in (paper.get("authors") or [])
            if isinstance(author, dict) and _clean(author.get("name"))
        ]
        upvotes = row.get("upvotes")
        items.append(
            FrontierWireItem(
                source_platform="huggingface",
                content_id=f"huggingface:{paper_id}",
                content_url=f"https://huggingface.co/papers/{paper_id}",
                title=title,
                body_text=summary,
                author_name=", ".join(authors[:3]),
                published_at=_iso(row.get("publishedAt") or paper.get("publishedAt")),
                tags=("Hugging Face", "Daily Papers"),
                score=0.88,
                topic_label="AI 前沿 · 论文",
                expression=(
                    "Hugging Face 今日热门论文，社区讨论度很高。摘要已附在卡片里，"
                    "适合先看方法和结论，判断是否值得跟进。"
                ),
                source_metadata={
                    "wire": "huggingface",
                    "upvotes": upvotes,
                    "authors": authors[:8],
                },
            )
        )
    return items


def _hn_items(payload: object, limit: int) -> list[FrontierWireItem]:
    rows = payload.get("hits") if isinstance(payload, dict) else []
    items: list[FrontierWireItem] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        title = _clean(row.get("title"))
        if not title or not _HN_FRONTIER_TERMS.search(title) or _HN_COMMENTARY.search(title):
            continue
        object_id = _clean(row.get("objectID"))
        if not object_id:
            continue
        points = int(row.get("points") or 0)
        comments = int(row.get("num_comments") or 0)
        url = _clean(row.get("url")) or f"https://news.ycombinator.com/item?id={object_id}"
        items.append(
            FrontierWireItem(
                source_platform="hackernews",
                content_id=f"hackernews:{object_id}",
                content_url=url,
                title=title,
                body_text=(
                    f"Hacker News 热帖，{points} 分、{comments} 条讨论。"
                    "适合看一线工程师在关心什么。"
                ),
                author_name=_clean(row.get("author")) or "Hacker News",
                published_at=_iso(row.get("created_at")),
                tags=("Hacker News",),
                score=min(0.9, 0.75 + points / 10000.0),
                topic_label="AI 前沿 · 社区",
                expression=(
                    f"Hacker News 工程社区热帖，{points} 分、{comments} 条讨论。"
                    "适合看一线工程师在关心什么。"
                ),
                source_metadata={
                    "wire": "hackernews",
                    "points": points,
                    "comments": comments,
                    "hn_id": object_id,
                },
            )
        )
        if len(items) >= limit:
            break
    return items


def fetch_frontier_wire(*, limit_per_source: int = 8) -> list[FrontierWireItem]:
    """Fetch the three public feeds, skipping any source that fails.

    The function is synchronous by design: the API delegates it to a worker
    thread with a wall-clock deadline. A source failure must not take the
    other two down, so every request has its own ``try`` block.
    """
    limit = max(1, min(int(limit_per_source), 20))
    items: list[FrontierWireItem] = []
    timeout = httpx.Timeout(12.0, connect=5.0)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        **outbound_httpx_kwargs(),
    ) as client:
        try:
            response = client.get(
                ARXIV_URL,
                params={
                    "search_query": "cat:cs.AI OR cat:cs.CL OR cat:cs.LG",
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": str(limit),
                },
            )
            response.raise_for_status()
            items.extend(_arxiv_items(response.text, limit))
        except (httpx.HTTPError, ET.ParseError, ValueError):
            pass
        try:
            response = client.get(HF_DAILY_PAPERS_URL, params={"limit": str(limit)})
            response.raise_for_status()
            items.extend(_hf_items(response.json(), limit))
        except (httpx.HTTPError, ValueError):
            pass
        try:
            since = int((datetime.now(UTC) - timedelta(days=14)).timestamp())
            response = client.get(
                HN_SEARCH_URL,
                params={
                    "query": "AI",
                    "tags": "story",
                    "numericFilters": f"points>100,created_at_i>{since}",
                    "hitsPerPage": "40",
                },
            )
            response.raise_for_status()
            items.extend(_hn_items(response.json(), limit))
        except (httpx.HTTPError, ValueError):
            pass

    # Stable identity de-dup inside one fetch (feeds can repeat a paper).
    seen: set[str] = set()
    output: list[FrontierWireItem] = []
    for item in items:
        if item.content_id in seen:
            continue
        seen.add(item.content_id)
        output.append(item)
    return output


def ingest_frontier_wire(
    database: Any,
    items: Iterable[FrontierWireItem],
) -> dict[str, int]:
    """Store wire items and their recommendation-history rows.

    Returns ``{"fetched", "inserted", "skipped", "failed"}``. The wire uses the
    same ``content_cache`` + ``recommendations`` tables as a normal serve, so
    feedback, saving, dedup and the channel classifier all work unchanged.
    """
    fetched = 0
    inserted = 0
    skipped = 0
    failed = 0
    for item in items:
        fetched += 1
        try:
            existing = database.conn.execute(
                "SELECT 1 FROM content_cache WHERE bvid = ? LIMIT 1",
                (item.content_id,),
            ).fetchone()
            if existing is not None:
                skipped += 1
                continue
            raw_content_id = (
                item.content_id.split(":", 1)[-1] if ":" in item.content_id else item.content_id
            )
            item_key = make_item_key(item.source_platform, raw_content_id, item.content_url)
            database.cache_content(
                item.content_id,
                item_key=item_key,
                title=item.title,
                description=item.body_text[:1200],
                body_text=item.body_text,
                source="ai-frontier-wire",
                source_platform=item.source_platform,
                content_id=raw_content_id,
                content_url=item.content_url,
                # Keep the wire on the long-established `article` text-card path. The
                # classifier still treats arXiv/Hugging Face articles as paper-like,
                # but a browser carrying a slightly older card renderer sees a
                # readable excerpt instead of a blank cover slot.
                content_type="article",
                up_name=item.author_name,
                author_name=item.author_name,
                published_at=item.published_at,
                tags=json.dumps(list(item.tags), ensure_ascii=False),
                pool_expression=item.expression,
                pool_topic_label=item.topic_label,
                style_key="tech_analysis",
                topic_group="AI 前沿",
                topic_key=item.topic_label,
                relevance_score=item.score,
                candidate_tier="primary",
                source_metadata=item.source_metadata,
            )
            database.batch_insert_recommendations(
                [
                    {
                        "bvid": item.content_id,
                        "item_key": item_key,
                        "expression": item.expression,
                        "topic": item.topic_label,
                        "confidence": item.score,
                        "presented": 0,
                    }
                ]
            )
            inserted += 1
        except Exception as exc:
            logger.warning("frontier wire ingest failed for %s: %s", item.content_id, exc)
            failed += 1
    return {
        "fetched": fetched,
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
    }


def wire_source_counts(items: Iterable[FrontierWireItem]) -> dict[str, int]:
    """Small helper for the API response/tests."""
    counts: dict[str, int] = {}
    for item in items:
        counts[item.source_platform] = counts.get(item.source_platform, 0) + 1
    return counts
