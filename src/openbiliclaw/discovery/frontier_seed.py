"""Curated keyword seeds for the AI-frontier channel.

The channel's first version is a classifier over the existing candidate pool
(``recommendation/frontier.py``). A narrow channel can run dry even when the
general pool is healthy, so this module provides a small, platform-aware
keyword pack that the API can inject into the normal discovery keyword store.
The regular fetch pipeline then claims those words exactly like planner-
generated keywords — no separate crawler, no bypass of admission/eval.

Keep the pack short and specific and *applied*: AI coding tools, agent/MCP
workflows, app integration, local-run tooling, indie builds. Model-release and
benchmark words were removed together with the paper feeds — they produced the
news cards this channel's reader never asked for. Broad words like "AI" or
"人工智能" produce the tutorial/marketing noise the classifier filters out.
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
        "Claude Code 实战",
        "Cursor 进阶技巧",
        "Codex 工作流",
        "MCP 工具 实战",
        "AI 编程 提效",
        "AI 做小工具",
    ),
    "youtube": (
        "Claude Code workflow",
        "Cursor tips",
        "MCP server tutorial",
        "build AI app with Next.js",
        "Vercel AI SDK",
        "vibe coding",
    ),
    "github": (
        "AI coding agent",
        "MCP server",
        "claude code",
        "AI app boilerplate",
        "LLM app SDK",
    ),
    "linuxdo": (
        "Claude Code",
        "Cursor",
        "AI 编程",
        "MCP",
        "免费 API 额度",
        "自建 AI 工具",
    ),
    "v2ex": (
        "AI 编程工具",
        "Claude Code",
        "Cursor",
        "独立开发",
    ),
    "weibo": (
        "AI 编程",
        "Cursor",
        "Claude Code",
    ),
    "douyin": (
        "AI 编程 提效",
        "AI 做工具",
    ),
    "xiaohongshu": (
        "AI 编程",
        "Cursor 使用",
    ),
    "zhihu": (
        "AI 编程 工具",
        "如何用 AI 做产品",
        "AI 独立开发",
    ),
    "twitter": (
        "Claude Code",
        "Cursor",
        "MCP",
        "vibe coding",
        "AI agent",
    ),
    "reddit": (
        "ClaudeAI",
        "cursor",
        "mcp",
        "vibecoding",
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
