"""Curated keyword seeds for the AI-frontier channel.

The channel's first version is a classifier over the existing candidate pool
(``recommendation/frontier.py``). A narrow channel can run dry even when the
general pool is healthy, so this module provides a small, platform-aware
keyword pack that the API can inject into the normal discovery keyword store.
The regular fetch pipeline then claims those words exactly like planner-
generated keywords — no separate crawler, no bypass of admission/eval.

Keep the pack short and specific: model releases, benchmarks, open weights,
inference/agent engineering. Broad words like "AI" or "人工智能" produce the
tutorial/marketing noise the classifier is trying to filter out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

AI_FRONTIER_SEED_REASON = "ai_frontier_channel_seed"
AI_FRONTIER_INTEREST_LABEL = "AI 前沿"

# Platform-specific phrasing matters: Bilibili/Weibo/linux.do searches are
# Chinese, YouTube/GitHub/Reddit searches are English. The same concept is
# deliberately expressed differently per platform.
FRONTIER_SEED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bilibili": (
        "Gemini 4 实测",
        "DeepSeek V4 实测",
        "Kimi K3 实测",
        "大模型 基准 评测",
        "AI Agent 实测",
        "开源大模型 本地部署",
        "多模态大模型 发布",
    ),
    "youtube": (
        "Gemini 4 Argon",
        "GPT-6.1 Sol",
        "Claude Opus 5.5",
        "DeepSeek V4.1",
        "Kimi K3.1",
        "LLM benchmark",
        "AI agent benchmark",
        "open weights model",
    ),
    "github": (
        "LLM inference",
        "AI agent framework",
        "open weights",
        "multimodal model",
        "vLLM",
        "agent harness",
    ),
    "linuxdo": (
        "大模型 发布",
        "AI 前沿",
        "开源模型 权重",
        "推理框架",
        "Gemini 4",
        "Agent 工具",
    ),
    "v2ex": (
        "大模型 发布",
        "AI Agent",
        "开源模型",
        "推理加速",
    ),
    "weibo": (
        "大模型 发布",
        "AI 前沿",
        "Gemini 4",
        "开源模型",
    ),
    "douyin": (
        "AI 前沿",
        "大模型 发布",
        "AI Agent 实测",
    ),
    "xiaohongshu": (
        "AI 前沿",
        "大模型 实测",
        "AI Agent",
    ),
    "zhihu": (
        "大模型 发布",
        "AI Agent",
        "开源大模型",
        "模型评测",
    ),
    "twitter": (
        "Gemini 4",
        "GPT-6",
        "Claude Opus",
        "DeepSeek",
        "Kimi",
        "open weights",
    ),
    "reddit": (
        "LocalLLaMA",
        "open weights",
        "LLM benchmark",
        "AI agent",
    ),
}


def enabled_frontier_platforms(sources: object | None) -> list[str]:
    """Return the seed platforms whose source config is enabled.

    ``None`` means "no config available" (tests/CLI): return every platform.
    A missing attribute is treated as disabled, not as enabled, so a typo in
    a platform name cannot silently start work on an unsupported source.
    """
    if sources is None:
        return list(FRONTIER_SEED_KEYWORDS)
    platforms: list[str] = []
    for platform in FRONTIER_SEED_KEYWORDS:
        source_config = getattr(sources, platform, None)
        if source_config is None:
            continue
        if bool(getattr(source_config, "enabled", False)):
            platforms.append(platform)
    return platforms


def seed_frontier_keywords(
    database: Any,
    profile_digest: str,
    *,
    sources: object | None = None,
    platforms: Sequence[str] | None = None,
) -> int:
    """Insert the curated frontier keywords as pending discovery keywords.

    Returns the number of rows actually inserted. Existing in-flight rows are
    ignored by ``insert_pending_keywords``; used/expired history does not
    block a later re-seed, which is intentional: the channel needs a steady
    trickle, and the caller throttles the call.
    """
    digest = str(profile_digest or "").strip()
    if not digest:
        return 0
    targets = list(platforms) if platforms is not None else enabled_frontier_platforms(sources)
    inserted = 0
    for platform in targets:
        words = FRONTIER_SEED_KEYWORDS.get(str(platform).strip())
        if not words:
            continue
        metadata: Mapping[str, Mapping[str, object]] = {
            word: {
                "source_interest": AI_FRONTIER_INTEREST_LABEL,
                "generation_reason": AI_FRONTIER_SEED_REASON,
                "query_kind": "regular",
            }
            for word in words
        }
        inserted += int(
            database.insert_pending_keywords(
                platform,
                words,
                digest,
                metadata_by_keyword=metadata,
            )
        )
    return inserted
