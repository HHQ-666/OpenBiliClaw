"""Curated high-quality AI-frontier wire.

The recommendation pool is fed by social/video platforms, which is good for
"what people are talking about" but weak on primary sources. This module adds
a small, explicitly curated wire for the ``AI 前沿`` channel:

* Hugging Face trending models — open-weight releases people can actually run.
* Hacker News (points > 100, last 14 days) — engineering-community discussion.

The wire is applied-first by design: the channel serves people who build with
models, so pure paper feeds (arXiv, Hugging Face Daily Papers) are deliberately
not fetched — their abstracts carry research signals without providing anything
runnable, and the channel's classifier demotes research-only candidates anyway.

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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from openbiliclaw.network import outbound_httpx_kwargs
from openbiliclaw.saved_sync.identity import make_item_key

if TYPE_CHECKING:
    from collections.abc import Iterable

HF_TRENDING_MODELS_URL = "https://huggingface.co/api/models"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

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
# Research write-ups are out of scope for an applied channel: the HN feed is
# here for "someone shipped / measured something you can use", not for paper
# discussion threads.
_HN_PAPER_REJECT = re.compile(
    r"arxiv|\bpaper\b|preprint|论文|预印本|\bet al\b",
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


_TOPIC_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"recommend|personaliz|ranking|user history", re.IGNORECASE), "推荐系统与个性化"),
    (re.compile(r"multi[- ]?agent|agent(?:s|ic)?\b|智能体", re.IGNORECASE), "Agent 与多智能体"),
    (
        re.compile(r"multimodal|vision[- ]language|image|video generation", re.IGNORECASE),
        "多模态与视觉生成",
    ),
    (re.compile(r"reinforcement|rlhf|rlvr|policy optimization", re.IGNORECASE), "强化学习"),
    (re.compile(r"time[- ]series|forecast", re.IGNORECASE), "时间序列与预测"),
    (re.compile(r"medical|clinical|ultrasound|health", re.IGNORECASE), "医学与健康 AI"),
    (re.compile(r"retriev|\brag\b|knowledge base", re.IGNORECASE), "检索增强与知识库"),
    (
        re.compile(r"quantiz|inference|kv[- ]cache|throughput|latency", re.IGNORECASE),
        "推理与部署优化",
    ),
    (
        re.compile(r"robot|embodied|dexterous|manipulation|\bvla\b", re.IGNORECASE),
        "具身智能与机器人",
    ),
    (re.compile(r"benchmark|evaluation|leaderboard", re.IGNORECASE), "评测与基准"),
    (
        re.compile(
            r"detector|detection|safety|ethic|alignment|privacy|security",
            re.IGNORECASE,
        ),
        "AI 安全与伦理",
    ),
    (re.compile(r"image editing|editing", re.IGNORECASE), "图像生成与编辑"),
    (re.compile(r"world model|simulation", re.IGNORECASE), "世界模型与仿真"),
    (re.compile(r"long[- ]context|context window|memory", re.IGNORECASE), "长上下文与记忆"),
    (
        re.compile(
            r"\bcode\b|\bcoding\b|programming|software engineering",
            re.IGNORECASE,
        ),
        "代码与软件工程",
    ),
    (re.compile(r"graph|structured knowledge", re.IGNORECASE), "结构化知识与图"),
    (re.compile(r"speech|audio|music", re.IGNORECASE), "语音与音频"),
)


def _wire_topics(*texts: object, limit: int = 3) -> list[str]:
    """Pick a few reader-facing Chinese topics from a wire item.

    The recommendation reason must not be the same sentence for every paper.
    A deterministic keyword pass is enough to differentiate the visible mix
    (recommendation / agents / multimodal / RL / time-series / safety / …)
    without adding another LLM call to the refresh path.
    """
    combined = " ".join(_clean(text) for text in texts)
    topics: list[str] = []
    for pattern, label in _TOPIC_RULES:
        if label in topics:
            continue
        if pattern.search(combined):
            topics.append(label)
        if len(topics) >= limit:
            break
    return topics


def _topic_phrase(topics: list[str]) -> str:
    return "、".join(topics) if topics else "前沿方法与应用"


def _merge_topics(*groups: list[str], limit: int = 3) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for label in group:
            if label not in merged:
                merged.append(label)
            if len(merged) >= limit:
                return merged
    return merged


def _reason_variant(variants: tuple[str, ...], key: str) -> str:
    """Deterministic template rotation so adjacent cards do not read alike."""
    if not variants:
        return ""
    index = sum(ord(char) for char in key) % len(variants)
    return variants[index]


def _hf_model_items(payload: object, limit: int) -> list[FrontierWireItem]:
    """Turn Hugging Face trending models into runnable-release wire items.

    A trending open-weight model is the applied counterpart of a paper: the
    reader can pull it with Ollama / vLLM or call it through an inference API
    the same day. The card therefore leads with "what you can run", not with
    an abstract.
    """
    rows = payload if isinstance(payload, list) else []
    items: list[FrontierWireItem] = []
    for row in rows:
        if not isinstance(row, dict) or len(items) >= limit:
            continue
        model_id = _clean(row.get("id") or row.get("modelId"))
        if not model_id:
            continue
        likes = int(row.get("likes") or 0)
        downloads = int(row.get("downloads") or 0)
        pipeline = _clean(row.get("pipeline_tag") or "")
        tags = [_clean(tag) for tag in (row.get("tags") or []) if _clean(tag)]
        display_name = model_id.split("/")[-1]
        published_at = _iso(row.get("createdAt") or row.get("lastModified"))
        topic = _wire_topics(display_name, pipeline, " ".join(tags[:12]))
        usage = f"下载 {downloads}" if downloads else f"{likes} 个赞"
        items.append(
            FrontierWireItem(
                source_platform="huggingface",
                content_id=f"huggingface:model:{model_id}",
                content_url=f"https://huggingface.co/{model_id}",
                title=f"{display_name} 开源模型（{model_id}）",
                body_text=(
                    f"Hugging Face 趋势开源模型 {model_id}，{usage}。"
                    f"{'任务类型：' + pipeline + '。' if pipeline else ''}"
                    "可直接用 Ollama 本地运行，或通过推理 API 接入自己的应用。"
                ),
                author_name=model_id.split("/")[0] if "/" in model_id else "Hugging Face",
                published_at=published_at,
                tags=tuple(x for x in ("Hugging Face", "开源模型", pipeline) if x),
                score=min(0.92, 0.82 + likes / 5000.0),
                topic_label="AI 前沿 · 开源模型",
                expression=_reason_variant(
                    (
                        f"Hugging Face 趋势开源模型，聚焦{_topic_phrase(topic)}；"
                        "权重公开，可以本地跑或直接接入 API。",
                        f"这个开源权重模型最近在 HF 上热度不错（{usage}），"
                        f"主题是{_topic_phrase(topic)}，适合先试个 demo 再用进项目。",
                    ),
                    model_id,
                ),
                source_metadata={
                    "wire": "huggingface",
                    "model_id": model_id,
                    "likes": likes,
                    "downloads": downloads,
                    "pipeline_tag": pipeline,
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
        if (
            not title
            or not _HN_FRONTIER_TERMS.search(title)
            or _HN_COMMENTARY.search(title)
            or _HN_PAPER_REJECT.search(title)
        ):
            continue
        object_id = _clean(row.get("objectID"))
        if not object_id:
            continue
        points = int(row.get("points") or 0)
        comments = int(row.get("num_comments") or 0)
        url = _clean(row.get("url")) or f"https://news.ycombinator.com/item?id={object_id}"
        topics = _wire_topics(title)
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
                expression=_reason_variant(
                    (
                        f"Hacker News 工程社区热帖，{points} 分、{comments} 条讨论，"
                        f"主题是{_topic_phrase(topics)}。",
                        f"Hacker News 上讨论度不错的一帖，{points} 分、{comments} 条评论，"
                        f"聚焦{_topic_phrase(topics)}。",
                    ),
                    object_id,
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
    """Fetch the applied AI feeds, skipping any source that fails.

    Two sources, both applied-first: trending open-weight models on Hugging
    Face (something you can run today) and Hacker News engineering discussion.
    Paper feeds are intentionally absent — the channel is for people building
    with models, and the classifier demotes research-only candidates anyway.

    The function is synchronous by design: the API delegates it to a worker
    thread with a wall-clock deadline. A source failure must not take the
    other one down, so every request has its own ``try`` block.
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
                HF_TRENDING_MODELS_URL,
                params={
                    "sort": "trendingScore",
                    "direction": "-1",
                    "limit": str(limit),
                    "full": "false",
                },
            )
            response.raise_for_status()
            items.extend(_hf_model_items(response.json(), limit))
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
