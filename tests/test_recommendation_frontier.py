"""Tests for the AI-frontier channel classifier."""

from __future__ import annotations

from types import SimpleNamespace

from openbiliclaw.recommendation.frontier import (
    AI_FRONTIER_CHANNEL,
    FRONTIER_SCORE_THRESHOLD,
    assess_ai_frontier,
    assess_ai_frontier_content,
    assess_ai_frontier_row,
)


def test_release_with_versioned_model_is_frontier() -> None:
    assessment = assess_ai_frontier(
        title="Gemini 4 Argon 正式发布，基准第一",
        description="1M 上下文，Agent 能力大幅提升。",
        source_platform="bilibili",
        content_type="video",
    )

    assert assessment.is_frontier
    assert assessment.score >= FRONTIER_SCORE_THRESHOLD
    assert "前沿模型" in assessment.tags


def test_research_paper_without_an_applied_angle_is_not_frontier() -> None:
    # The channel is applied-first: a paper abstract with no tooling /
    # workflow / repo angle answers a question this reader does not have.
    assessment = assess_ai_frontier(
        title="Long-MDR: Long-Context RL for Multimodal Deep-Research Agents",
        description="arXiv 2610.05195，128K 上下文、75+ 工具轮次。",
        source_platform="github",
        content_type="paper",
    )

    assert not assessment.is_frontier
    assert assessment.score < FRONTIER_SCORE_THRESHOLD
    assert "论文研究" in assessment.tags


def test_paper_with_shipped_tooling_angle_stays_frontier() -> None:
    # Paper + open-source repo + a way to run it today is exactly the useful
    # intersection: research depth that arrives with something usable.
    assessment = assess_ai_frontier(
        title="Long-MDR 论文开源：128K 上下文的 LLM Agent 工具，支持 Ollama 本地运行",
        description="论文附带开源项目与 SDK，可直接接入自己的应用。",
        source_platform="huggingface",
        content_type="paper",
    )

    assert assessment.is_frontier
    assert "应用与工具" in assessment.tags


def test_applied_tooling_headline_is_frontier() -> None:
    assessment = assess_ai_frontier(
        title="Claude Code 工作流实战：用 MCP 把内部 API 接进前端项目",
        description="一步步配置 SDK、写好工具定义，并踩了几个权限坑。",
        source_platform="linuxdo",
        content_type="post",
    )

    assert assessment.is_frontier
    assert "应用与工具" in assessment.tags


def test_generic_ai_industry_commentary_is_not_frontier() -> None:
    assessment = assess_ai_frontier(
        title="为什么科技公司不再需要那么多印度工程师：AI 正在改变 IT 外包",
        description="AI 对全球 IT 外包和程序员就业的影响。",
        source_platform="youtube",
        content_type="video",
    )

    assert not assessment.is_frontier
    assert assessment.score < FRONTIER_SCORE_THRESHOLD


def test_ai_tutorial_marketing_is_not_frontier() -> None:
    assessment = assess_ai_frontier(
        title="AI 绘画教程：零基础月入过万，保姆级变现玩法",
        description="教你用 AI 做副业，附全套课程。",
        source_platform="bilibili",
        content_type="video",
    )

    assert not assessment.is_frontier


def test_personal_post_mentioning_a_model_only_in_body_is_not_frontier() -> None:
    assessment = assess_ai_frontier(
        title="聊聊这一年，我在这里的探索、改变和输出",
        body="这一年我用了很多 DeepSeek、Claude 和 Gemini，也部署了不少服务。",
        source_platform="linuxdo",
        content_type="post",
    )

    assert not assessment.is_frontier


def test_repository_that_merely_uses_models_is_not_frontier() -> None:
    assessment = assess_ai_frontier(
        title="ToolJet/ToolJet",
        description=(
            "Open-source enterprise app generation platform with AI agents, "
            "Claude Code, Codex and Cursor over MCP."
        ),
        tags=["ai-agents", "claude-code", "mcp", "low-code"],
        source_platform="github",
        content_type="repository",
    )

    assert not assessment.is_frontier


def test_text_post_with_versioned_model_and_eval_passes() -> None:
    assessment = assess_ai_frontier(
        title="Kimi K3.1 Pro 正式发布，Terminal-Bench 4.0 65.7%",
        description="3T 级开放权重，1M 上下文。",
        source_platform="twitter",
        content_type="tweet",
    )

    assert assessment.is_frontier
    assert "前沿模型" in assessment.tags


def test_row_and_content_wrappers_share_the_same_score() -> None:
    row = {
        "title": "DeepSeek-V4.1-Flash-1017 开源，DeepSWE 77.0",
        "description": "552B MoE，输入激活 8B。",
        "topic": "前沿模型",
        "source_platform": "bilibili",
        "content_type": "video",
        "tags": '["大模型", "deepseek"]',
        "up_name": "技术博主",
    }
    content = SimpleNamespace(
        title=row["title"],
        description=row["description"],
        body_text="",
        topic_group=row["topic"],
        topic_key="",
        pool_topic_label="",
        tags=["大模型", "deepseek"],
        source_platform="bilibili",
        content_type="video",
        up_name="技术博主",
        author_name="",
    )

    by_row = assess_ai_frontier_row(row)
    by_content = assess_ai_frontier_content(content)

    assert by_row.is_frontier
    assert by_row.score == by_content.score
    assert by_row.tags == by_content.tags


def test_channel_constant_is_stable_for_api_and_ui() -> None:
    assert AI_FRONTIER_CHANNEL == "ai_frontier"


def test_arxiv_article_without_tooling_angle_is_not_frontier() -> None:
    # arXiv/Hugging Face papers are stored as `article`; the old paper-like
    # prior let them into the channel on research signals alone. The applied
    # gate now keeps a bare method paper out while the research tag survives
    # for diagnostics.
    assessment = assess_ai_frontier(
        title="A New Method for Long-Context Agents",
        description="arXiv paper with 128K context and benchmark results.",
        source_platform="arxiv",
        content_type="article",
    )

    assert not assessment.is_frontier
    assert "论文研究" in assessment.tags


def test_paper_mentioning_api_only_in_abstract_is_not_frontier() -> None:
    # A paper abstract routinely says "API"/"SDK" in passing; that must not
    # count as an applied angle. The tool has to be in the headline itself.
    assessment = assess_ai_frontier(
        title="A Unified Library and Benchmark for Robust Reinforcement Learning",
        description=(
            "We propose RobustRLlib, exposing a single API and an SDK that "
            "researchers can call from their training scripts. Experiments show "
            "state-of-the-art robustness across datasets."
        ),
        source_platform="arxiv",
        content_type="paper",
    )

    assert not assessment.is_frontier


def test_english_tool_names_do_not_match_inside_ordinary_words() -> None:
    # "discipline" used to satisfy `cline`, letting a pure paper through the
    # applied gate with a fake 应用与工具 tag.
    assessment = assess_ai_frontier(
        title="Clause-Anchored Corpus for Professional Ethics",
        description="This discipline increasingly relies on large language models.",
        source_platform="huggingface",
        content_type="article",
    )

    assert not assessment.is_frontier
    assert "应用与工具" not in assessment.tags


def test_deep_infra_internals_without_a_tool_angle_is_not_frontier() -> None:
    # The user cannot act on attention-kernel trivia; without a headline-level
    # tool angle an infra deep-dive is not channel material.
    assessment = assess_ai_frontier(
        title="A tricky LLM interview question",
        body=(
            "You serve a reasoning model on vLLM and it runs out of GPU memory. "
            "PagedAttention splits GPU memory into 16-token physical blocks, so "
            "evicting 90% of the KV cache frees almost nothing."
        ),
        source_platform="twitter",
        content_type="tweet",
    )

    assert not assessment.is_frontier


def test_ai_career_chatter_is_not_frontier() -> None:
    assessment = assess_ai_frontier(
        title="As an AI Engineer. Please learn",
        body="If you learn AI Infrastructure Engineering, you will never be unemployed.",
        source_platform="twitter",
        content_type="tweet",
    )

    assert not assessment.is_frontier


def test_infra_deep_dive_with_a_headline_tool_angle_stays_frontier() -> None:
    # "本地部署实战" in the headline is the builder angle: the reader can act.
    assessment = assess_ai_frontier(
        title="2026 本地大模型横评：13 款开源模型，4000 元机器本地部署实战",
        description="Qwen3.6、Gemma 4 实测，Ollama 一键跑起来。",
        source_platform="youtube",
        content_type="video",
    )

    assert assessment.is_frontier
