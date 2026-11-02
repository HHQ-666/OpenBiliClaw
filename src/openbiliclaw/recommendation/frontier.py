"""Heuristic AI-frontier classifier for cross-platform recommendation content.

The product's "AI 前沿" channel is a *view over the existing candidate pool*,
not a new upstream source: the pool already carries Bilibili, YouTube, X,
GitHub, Zhihu, linux.do, Weibo and other platforms, but the general feed's
top-20 window dilutes specialist AI content. This module scores a candidate
from text signals so the channel can filter the full servable pool without an
extra LLM call on the serve hot path.

The classifier is deliberately conservative. A generic "AI" mention is not
enough, and neither is a tool that merely *uses* a model (an "AI-powered
low-code platform" or a Claude Code quota monitor). A candidate must carry a
frontier anchor: a versioned model plus a release/eval/research signal, a
paper, or a specific inference/training engineering term. Marketing and
tutorial language is penalised so the channel does not collapse into the
"本地部署保姆级教程" genre.

The channel is *applied-first*: its reader builds applications with models,
so a tool / SDK / workflow / product angle earns a bonus, while research-only
artifacts (arXiv abstract tone, dataset-and-ablation papers) are capped below
the threshold unless they also ship something usable. The score is additive
and explainable so a false positive can be diagnosed from the returned
``matched`` terms.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

AI_FRONTIER_CHANNEL = "ai_frontier"
AI_FRONTIER_LABEL = "AI 前沿"

# Tuned against the real pool: versioned-model release notes and papers clear
# this comfortably; AI-adjacent tools and generic industry commentary do not.
FRONTIER_SCORE_THRESHOLD = 6.0

TAG_MODEL = "前沿模型"
TAG_RESEARCH = "论文研究"
TAG_ENGINEERING = "开源工程"
TAG_INFRA = "推理与算力"
TAG_AGENT = "Agent"
TAG_MULTIMODAL = "多模态"
TAG_SAFETY = "安全与对齐"
TAG_APPLIED = "应用与工具"

_MODEL_WITH_VERSION = re.compile(
    r"(?<![a-z0-9])("
    r"gpt|gemini|claude|opus|sonnet|haiku|fable|deepseek|kimi|qwen|glm|minimax|"
    r"llama|mistral|grok|gemma|muse|beam|ornith|mercury|nemotron|phi|"
    r"step|seed|spark|longcat|internlm|baichuan|command"
    r")[-_ ]?[kv]?\d[\w.]*",
    re.IGNORECASE,
)
_MODEL_FAMILY = re.compile(
    r"(?<![a-z0-9])("
    r"gpt|gemini|claude|opus|sonnet|haiku|fable|deepseek|kimi|qwen|glm|minimax|"
    r"llama|mistral|grok|gemma|muse|beam|ornith|mercury|nemotron|phi|"
    r"longcat|internlm|baichuan"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)
_CN_MODEL = re.compile(
    r"通义千问|通义|千问|文心一言|文心|混元|豆包|星火|智谱|清言|日日新|"
    r"书生|悟道|阶跃|月之暗面|零一万物|百川|商汤|昆仑万维|天工|紫东太初"
)
_SIZE_OR_CONTEXT = re.compile(
    r"\d+(?:\.\d+)?\s*(?:b|m|k|t)\b|"
    r"\d+(?:\.\d+)?\s*[万亿]\s*参数|"
    r"\d+\s*(?:k|m)\s*(?:context|上下文)|"
    r"(?:context|上下文)\s*(?:window|长度)?\s*[:：]?\s*\d+",
    re.IGNORECASE,
)

_RELEASE = re.compile(
    r"发布|推出|上线|开源|开放权重|开放|权重|model\s*card|技术报告|技术博客|"
    r"release|launch|introducing|open[- ]weight|weights",
    re.IGNORECASE,
)
_RELEASE_ANCHOR = re.compile(
    r"发布|推出|上线|开放权重|权重|model\s*card|技术报告|技术博客|"
    r"release|launch|introducing|open[- ]weight|weights",
    re.IGNORECASE,
)
_EVAL = re.compile(
    r"基准|评测|实测|跑分|得分|分数|榜单|排行榜|benchmark|bench\b|sota|"
    r"state[- ]of[- ]the[- ]art|leaderboard|eval(?:uation)?\b",
    re.IGNORECASE,
)
_EVAL_ANCHOR = re.compile(
    r"基准|benchmark|bench\b|sota|state[- ]of[- ]the[- ]art|leaderboard",
    re.IGNORECASE,
)
_RESEARCH = re.compile(
    r"arxiv|\b论文\b|\bpaper\b|预印本|消融|ablation|\bdataset\b|数据集|"
    r"technical report|技术报告",
    re.IGNORECASE,
)
_ENGINEERING = re.compile(
    r"推理|inference|预训练|post[- ]?train|\btraining\b|微调|fine[- ]?tun|"
    r"rlhf|rlvr|量化|quantiz|kv[- ]?cache|长上下文|long[- ]context|"
    r"context window|吞吐|throughput|tokens?\s*(?:per\s*second|/s)|\btps\b|"
    r"vllm|sglang|llama\.cpp|算子|kernel|\bmoe\b|稀疏|sparsity|蒸馏|distill|"
    r"部署|deploy|显存|gpu|算力|加速",
    re.IGNORECASE,
)
_ENGINEERING_ANCHOR = re.compile(
    r"推理|inference|预训练|post[- ]?train|rlhf|rlvr|微调|fine[- ]?tun|"
    r"量化|quantiz|kv[- ]?cache|长上下文|long[- ]context|context window|"
    r"吞吐|throughput|tokens?\s*(?:per\s*second|/s)|\btps\b|vllm|sglang|"
    r"llama\.cpp|算子|kernel|\bmoe\b|稀疏|sparsity|蒸馏|distill",
    re.IGNORECASE,
)
_AGENT = re.compile(
    r"(?<![a-z0-9])ai[- ]?agents?(?![a-z0-9])|llm[- ]?agents?(?![a-z0-9])|"
    r"智能体|tool[- ]?use|function[- ]?call|mcp\b|computer[- ]?use|"
    r"代码智能体|coding[- ]?agent|codex|claude[- ]?code|cursor|copilot|aider|"
    r"autogen|langgraph|多智能体|multi[- ]?agent",
    re.IGNORECASE,
)
_AGENT_ANCHOR = re.compile(
    r"(?<![a-z0-9])ai[- ]?agents?(?![a-z0-9])|llm[- ]?agents?(?![a-z0-9])|"
    r"智能体|tool[- ]?use|function[- ]?call|mcp\b|computer[- ]?use|"
    r"代码智能体|coding[- ]?agent|claude[- ]?code|codex",
    re.IGNORECASE,
)
_MULTIMODAL = re.compile(
    r"多模态|multimodal|视觉|vision|图像生成|视频生成|文生图|文生视频|"
    r"语音合成|语音识别|tts|asr|世界模型|world[- ]?model|具身|embodied|"
    r"机器人|robot|vla\b",
    re.IGNORECASE,
)
_SAFETY = re.compile(
    r"对齐|alignment|安全|safety|红队|red[- ]?team|prompt[- ]?injection|"
    r"越狱|jailbreak|幻觉|hallucination",
    re.IGNORECASE,
)
_GENERIC_AI = re.compile(
    r"(?<![a-z0-9])ai(?![a-z0-9])|人工智能|大模型|大语言模型|llm|"
    r"机器学习|深度学习|神经网络|生成式|genai|agi|算法",
    re.IGNORECASE,
)
# Hard marketing / engagement bait. These are the terms that turn a model
# release into a tutorial-channel video; the user's profile explicitly rejects
# this genre, so they must not be able to ride a model name over the threshold.
_BLOCK_NEGATIVE = re.compile(r"越狱|无审查|白嫖|破解", re.IGNORECASE)
_HARD_NEGATIVE = re.compile(
    r"零成本|零基础|保姆级|全网最|一键部署|一键搭建|彻底免费|杀疯了|逆天|"
    r"炸裂|封神|震惊|完美版|手把手|不会写代码|全民|小白|卧槽|"
    r"工具清单|宝藏|大厂人|自媒体博主|微信机器人|QQ机器人|聊天机器人|"
    r"课程|训练营|变现|副业|赚钱|月入|引流|广告|优惠|羊毛|福利|免费领|"
    r"ai\s*绘画|换脸|写真|算命|风水|情感|婚恋|国考|考公|家常菜|美食|"
    r"旅游|汽车|战列舰|缅北|八卦|明星|带货|直播带货|"
    r"tutorial|lesson\s*\d+|course|awesome[- ]|curated list|collection of",
    re.IGNORECASE,
)
_SOFT_NEGATIVE = re.compile(
    r"教程|入门|科普|盘点|合集|排行|推荐|清单|宝藏|一周|大事件|早报|日报|周报|汇总|"
    r"lesson|course",
    re.IGNORECASE,
)

# ── Applied vs academic ──────────────────────────────────────────────
# Who this channel is for: an application developer who builds with models
# (AI coding tools, SDKs, agents, indie products) — not a research lab. What
# makes a candidate useful is therefore a tool, workflow, API, product launch
# or build log. Pure research artifacts carry enough research/eval/model
# signals to clear the threshold on their own while answering no question
# this reader actually has, so they are demoted unless they also carry a
# practical angle (open-source repo, runnable demo, deployable tool).
_APPLIED = re.compile(
    r"插件|工作流|workflow|上手|实战|踩坑|"
    r"开源项目|open[- ]?source|\bsdk\b|\bapi\b|\bcli\b|\bide\b|"
    r"cursor|claude[- ]?code|codex|windsurf|cline|aider|\bv0\b|lovable|\bbolt\b|"
    r"n8n|dify|coze|扣子|langflow|flowise|obsidian|notion|"
    r"浏览器扩展|chrome\s*extension|ollama|lm[- ]?studio|localai|llama\.cpp|"
    r"comfyui|webui|本地运行|一键运行|搭建|配置|自动化|"
    r"前端|react|next\.js|\bvue\b|typescript|tailwind|独立开发|小工具|小产品",
    re.IGNORECASE,
)
_ACADEMIC = re.compile(
    r"arxiv|预印本|preprint|论文|\bpaper\b|"
    r"消融|ablation|数据集|\bdataset\b|"
    r"state[- ]of[- ]the[- ]art|\bsota\b|"
    r"we propose|we introduce|we present|proposed method|experimental results|"
    r"实验结果|对比实验|\bbaseline\b|基线|et al\.|\babstract\b|摘要",
    re.IGNORECASE,
)

# Official labs and established technical explainers. A small prior, not a
# substitute for the content signals above; it only breaks ties between two
# otherwise-similar candidates.
_AUTHOR_PRIOR = (
    "openai",
    "anthropic",
    "google deepmind",
    "deepmind",
    "meta ai",
    "deepseek",
    "moonshot",
    "qwen",
    "minimax",
    "mistral",
    "nvidia",
    "two minute papers",
    "ai explained",
    "yannic kilcher",
    "bycloud",
    "andrej karpathy",
)


@dataclass(frozen=True)
class FrontierAssessment:
    """One candidate's frontier score and the evidence behind it."""

    score: float = 0.0
    tags: tuple[str, ...] = ()
    matched: tuple[str, ...] = ()

    @property
    def is_frontier(self) -> bool:
        return self.score >= FRONTIER_SCORE_THRESHOLD


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _as_tags(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [value] if value.strip() else []
        value = parsed
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


_MODEL_ANY = re.compile(
    r"gpt|gemini|claude|opus|sonnet|haiku|fable|deepseek|kimi|qwen|glm|minimax|"
    r"llama|mistral|grok|gemma|muse|beam|ornith|mercury|nemotron|phi|"
    r"longcat|internlm|baichuan|通义|千问|文心|混元|豆包|星火|智谱|月之暗面|阶跃",
    re.IGNORECASE,
)


def _near_model(text: str, pattern: re.Pattern[str], *, window: int = 100) -> bool:
    """Whether ``pattern`` appears within ``window`` chars of a model mention.

    Frontier language is local: "Introducing Gemini 4 Argon" is a release;
    "ChatGPT → Idea → Launch Plan" is a workflow list that happens to contain
    the word "launch". Proximity is the cheapest way to tell them apart without
    a second LLM call.
    """
    for match in _MODEL_ANY.finditer(text):
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        if pattern.search(text[start:end]):
            return True
    return False


def _match_group(
    pattern: re.Pattern[str],
    *,
    title: str,
    body: str,
    topic: str,
) -> tuple[float, str]:
    """Return (multiplier, matched-text) for the best location of a group."""
    match = pattern.search(title)
    if match:
        return 1.5, match.group(0)
    match = pattern.search(body)
    if match:
        return 1.0, match.group(0)
    match = pattern.search(topic)
    if match:
        return 1.2, match.group(0)
    return 0.0, ""


def _dedupe(items: Iterable[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        if item and item not in output:
            output.append(item)
    return output


def assess_ai_frontier(
    *,
    title: object = "",
    body: object = "",
    description: object = "",
    topic: object = "",
    tags: object = (),
    source_platform: object = "",
    content_type: object = "",
    author: object = "",
) -> FrontierAssessment:
    """Score one candidate for the AI-frontier channel.

    ``body`` and ``description`` are interchangeable: callers pass whichever
    text the source provides (long-form posts use ``body``; video/repo rows use
    ``description``). Tags are included because GitHub repository topics and
    video tags often carry the only explicit "llm"/"agent" signal.
    """
    title_text = _normalize(title)
    body_text = _normalize(f"{description}\n{body}")
    topic_text = _normalize(topic)
    tag_text = _normalize(" ".join(_as_tags(tags)))
    combined = " ".join((title_text, body_text, topic_text, tag_text))
    if not combined.strip():
        return FrontierAssessment()

    score = 0.0
    tags_out: list[str] = []
    matched: list[str] = []
    source = _normalize(source_platform).lower()
    ctype = _normalize(content_type).lower()
    author_text = _normalize(author).lower()
    # The curated wire stores arXiv/Hugging Face rows as `article` so they
    # always use the text-card renderer; they are still primary papers for
    # scoring and tag purposes.
    paper_like = ctype == "paper" or (ctype == "article" and source in {"arxiv", "huggingface"})

    # ── Model anchor ─────────────────────────────────────────────────────
    version_match = _MODEL_WITH_VERSION.search(combined)
    family_match = _MODEL_FAMILY.search(combined)
    cn_model_match = _CN_MODEL.search(combined)
    model_anchor = False
    if version_match:
        model_anchor = True
        score += 4.0 if _MODEL_WITH_VERSION.search(title_text) else 2.5
        tags_out.append(TAG_MODEL)
        matched.append(version_match.group(0))
        # "Kimi K3.1 Pro 正式发布" is the canonical frontier headline: the
        # versioned model and the release verb are both in the title. Give it
        # a small explicit bonus so a short post is not lost to the generic
        # text-post penalties.
        if _RELEASE.search(title_text) and _MODEL_WITH_VERSION.search(title_text):
            score += 1.5
    elif family_match:
        # A bare family name is context, not a frontier claim: "supports
        # Claude / GPT / Gemini" is true of half the tooling ecosystem.
        score += 1.0
        tags_out.append(TAG_MODEL)
        matched.append(family_match.group(0))
    elif cn_model_match:
        score += 1.0
        tags_out.append(TAG_MODEL)
        matched.append(cn_model_match.group(0))

    if _SIZE_OR_CONTEXT.search(combined):
        score += 1.0
        matched.append("size/context")

    # ── Signal groups (each group contributes once) ──────────────────────
    release_mult, release_hit = _match_group(
        _RELEASE, title=title_text, body=body_text, topic=topic_text
    )
    if release_hit:
        # "Launch Plan" in a workflow list is not a model release; require the
        # release word to sit near a model mention, or be a weights/model-card
        # announcement that names the artifact explicitly.
        if _near_model(combined, _RELEASE_ANCHOR, window=100) or _RELEASE_ANCHOR.search(title_text):
            score += 2.5 * release_mult
            tags_out.append(TAG_MODEL)
            matched.append(release_hit)
        else:
            release_hit = ""

    eval_mult, eval_hit = _match_group(_EVAL, title=title_text, body=body_text, topic=topic_text)
    if eval_hit:
        if _near_model(combined, _EVAL_ANCHOR, window=120) or _EVAL_ANCHOR.search(title_text):
            score += 2.0 * eval_mult
            tags_out.append(TAG_INFRA)
            matched.append(eval_hit)
        else:
            # "实测" in a tutorial title is a review, not a benchmark result.
            score += 0.4 * eval_mult
            matched.append(eval_hit)

    research_mult, research_hit = _match_group(
        _RESEARCH, title=title_text, body=body_text, topic=topic_text
    )
    if research_hit:
        if (
            paper_like
            or _near_model(combined, _RESEARCH, window=120)
            or _RESEARCH.search(title_text)
        ):
            score += 2.5 * research_mult
            tags_out.append(TAG_RESEARCH)
            matched.append(research_hit)
        else:
            score += 0.5 * research_mult
            matched.append(research_hit)

    engineering_mult, engineering_hit = _match_group(
        _ENGINEERING, title=title_text, body=body_text, topic=topic_text
    )
    if engineering_hit:
        if _near_model(combined, _ENGINEERING_ANCHOR, window=120) or _GENERIC_AI.search(title_text):
            score += 2.0 * engineering_mult
            tags_out.append(TAG_ENGINEERING)
            matched.append(engineering_hit)
        else:
            score += 0.4 * engineering_mult
            matched.append(engineering_hit)

    agent_mult, agent_hit = _match_group(_AGENT, title=title_text, body=body_text, topic=topic_text)
    if agent_hit:
        score += 1.5 * agent_mult
        tags_out.append(TAG_AGENT)
        matched.append(agent_hit)

    multimodal_mult, multimodal_hit = _match_group(
        _MULTIMODAL, title=title_text, body=body_text, topic=topic_text
    )
    if multimodal_hit:
        score += 2.0 * multimodal_mult
        tags_out.append(TAG_MULTIMODAL)
        matched.append(multimodal_hit)

    safety_mult, safety_hit = _match_group(
        _SAFETY, title=title_text, body=body_text, topic=topic_text
    )
    if safety_hit:
        score += 1.5 * safety_mult
        tags_out.append(TAG_SAFETY)
        matched.append(safety_hit)

    # ── Generic prior ────────────────────────────────────────────────────
    if _GENERIC_AI.search(combined):
        score += 1.0
        matched.append("generic-ai")

    if _GENERIC_AI.search(combined):
        if source == "github":
            score += 0.5
        elif source in {"youtube", "bilibili"}:
            score += 0.2
        elif source in {"linuxdo", "v2ex", "zhihu"}:
            score += 0.1
        if ctype == "repository":
            score += 0.3
        elif paper_like:
            score += 2.0
        elif ctype == "video":
            score += 0.2
    if author_text and any(name in author_text for name in _AUTHOR_PRIOR):
        score += 1.5
    if paper_like:
        # A paper is a frontier artifact even when its title does not contain
        # the word "AI"; the source/type prior is the anchor here.
        score += 2.0

    # ── Applied-vs-academic axis ─────────────────────────────────────────
    # The channel's job is "what can I build with / use today", so a tool,
    # workflow, SDK or product angle earns a real bonus. Research-only
    # language is charged against the candidate; a paper that also ships a
    # usable artifact keeps most of its standing.
    applied_mult, applied_hit = _match_group(
        _APPLIED, title=title_text, body=body_text, topic=topic_text
    )
    if applied_hit:
        score += 2.0 * applied_mult
        tags_out.append(TAG_APPLIED)
        matched.append(f"applied:{applied_hit}")

    academic_mult, academic_hit = _match_group(
        _ACADEMIC, title=title_text, body=body_text, topic=topic_text
    )
    if academic_hit:
        if applied_hit:
            score -= 0.5 * academic_mult
            matched.append(f"academic:{academic_hit}")
        else:
            score -= 6.0 * academic_mult
            matched.append(f"academic-only:{academic_hit}")

    # ── Penalties ────────────────────────────────────────────────────────
    block_negative = _BLOCK_NEGATIVE.search(combined)
    if block_negative:
        score -= 7.0
        matched.append(f"blocked:{block_negative.group(0)}")
    hard_negative = _HARD_NEGATIVE.search(combined)
    if hard_negative:
        score -= 5.0
        matched.append(f"negative:{hard_negative.group(0)}")
    soft_negative = _SOFT_NEGATIVE.search(combined)
    if soft_negative:
        score -= 0.5
        matched.append(f"soft:{soft_negative.group(0)}")

    # ── Anchor gate ──────────────────────────────────────────────────────
    # A candidate must carry at least one frontier-specific anchor. Generic
    # "AI" + "agent" + "API" is a tooling signal, not a frontier signal; a
    # repository with no release/paper/benchmark is capped below the channel
    # threshold even if it mentions every popular model in its README.
    has_release_anchor = bool(_RELEASE_ANCHOR.search(combined))
    has_eval_anchor = bool(_EVAL_ANCHOR.search(combined))
    has_engineering_anchor = bool(_ENGINEERING_ANCHOR.search(combined))
    has_agent_anchor = bool(_AGENT_ANCHOR.search(combined)) and (
        has_release_anchor or has_eval_anchor or has_engineering_anchor
    )
    has_multimodal_anchor = bool(_MULTIMODAL.search(combined)) and (
        model_anchor or has_release_anchor or has_eval_anchor
    )
    # Applied content (a tool, SDK, workflow or build log) is the channel's
    # primary product, so it counts as an anchor on its own — but only when
    # the headline also names the AI surface it is built on. Otherwise every
    # "site configuration guide" in the pool would qualify.
    has_applied_anchor = bool(applied_hit) and bool(
        model_anchor
        or _MODEL_FAMILY.search(title_text)
        or _CN_MODEL.search(title_text)
        or _GENERIC_AI.search(title_text)
        or _ENGINEERING_ANCHOR.search(title_text)
        or _AGENT_ANCHOR.search(title_text)
    )
    has_anchor = bool(
        model_anchor
        or research_hit
        or has_engineering_anchor
        or has_agent_anchor
        or has_multimodal_anchor
        or has_applied_anchor
        or (has_release_anchor and _GENERIC_AI.search(combined))
    )
    if not has_anchor:
        score = min(score, FRONTIER_SCORE_THRESHOLD - 0.5)
    if ctype == "repository" and not (research_hit or version_match or has_eval_anchor):
        score = min(score, FRONTIER_SCORE_THRESHOLD - 0.5)
    # Long-form personal posts often mention a model in passing. The channel
    # needs an AI signal in the headline/topic/tags, not only in the body.
    headline = " ".join((title_text, topic_text, tag_text))
    headline_ai_signal = bool(
        _GENERIC_AI.search(headline)
        or _MODEL_WITH_VERSION.search(headline)
        or _MODEL_FAMILY.search(headline)
        or _CN_MODEL.search(headline)
        or _ENGINEERING_ANCHOR.search(headline)
        or _RESEARCH.search(headline)
        or _AGENT_ANCHOR.search(headline)
        or _MULTIMODAL.search(headline)
    )
    if not headline_ai_signal:
        score = min(score, FRONTIER_SCORE_THRESHOLD - 1.0)

    # ── Academic gate ────────────────────────────────────────────────────
    # Pure research artifacts stay out of this channel regardless of how many
    # research/eval signals they accumulate: a paper abstract with no tool,
    # repo or workflow angle is written for a lab, not for someone building
    # with models. Applied content is untouched (it already earned its bonus).
    if academic_hit and not applied_hit:
        score = min(score, FRONTIER_SCORE_THRESHOLD - 0.5)
    if paper_like and not applied_hit:
        score = min(score, FRONTIER_SCORE_THRESHOLD - 0.5)

    # Text-first sources use the post/question title as the card headline. A
    # long personal post can mention DeepSeek/Gemini in the body without being
    # about the frontier; requiring the headline itself to carry an AI signal
    # keeps "聊聊这一年" and "TO WHOM IT MAY CONCERN" out of the channel.
    text_first = source in {
        "twitter",
        "weibo",
        "zhihu",
        "linuxdo",
        "v2ex",
        "reddit",
    } or ctype in {"tweet", "thread", "answer", "question", "post", "comment"}
    if text_first:
        title_ai_signal = bool(
            _GENERIC_AI.search(title_text)
            or _MODEL_WITH_VERSION.search(title_text)
            or _MODEL_FAMILY.search(title_text)
            or _CN_MODEL.search(title_text)
            or _ENGINEERING_ANCHOR.search(title_text)
            or _RESEARCH.search(title_text)
            or _AGENT_ANCHOR.search(title_text)
            or _MULTIMODAL.search(title_text)
        )
        if not title_ai_signal:
            score = min(score, FRONTIER_SCORE_THRESHOLD - 1.0)
        elif model_anchor and not (
            release_hit
            or eval_hit
            or engineering_hit
            or _RELEASE_ANCHOR.search(title_text)
            or _EVAL_ANCHOR.search(title_text)
            or _ENGINEERING_ANCHOR.search(title_text)
            or _RESEARCH.search(title_text)
        ):
            # A model name plus personal commentary ("Jev + Claude Opus 5.5 is
            # a goldmine") is not a frontier release. Text posts need a
            # technical anchor in the headline or a nearby body sentence.
            score = min(score, FRONTIER_SCORE_THRESHOLD - 0.5)

    return FrontierAssessment(
        score=round(max(0.0, score), 3),
        tags=tuple(_dedupe(tags_out)),
        matched=tuple(_dedupe(matched)[:12]),
    )


def assess_ai_frontier_row(row: Mapping[str, Any]) -> FrontierAssessment:
    """Score a recommendation/candidate row from storage."""
    return assess_ai_frontier(
        title=row.get("title", ""),
        body=row.get("body_text", ""),
        description=row.get("description", ""),
        topic=row.get("topic", "") or row.get("topic_label", "") or row.get("pool_topic_label", ""),
        tags=row.get("tags", ()),
        source_platform=row.get("source_platform", ""),
        content_type=row.get("content_type", ""),
        author=row.get("up_name", "") or row.get("author_name", ""),
    )


def assess_ai_frontier_content(content: Any) -> FrontierAssessment:
    """Score a ``DiscoveredContent``-like object without importing it."""
    return assess_ai_frontier(
        title=getattr(content, "title", ""),
        body=getattr(content, "body_text", ""),
        description=getattr(content, "description", ""),
        topic=getattr(content, "topic_group", "")
        or getattr(content, "topic_key", "")
        or getattr(content, "pool_topic_label", ""),
        tags=getattr(content, "tags", ()),
        source_platform=getattr(content, "source_platform", ""),
        content_type=getattr(content, "content_type", ""),
        author=getattr(content, "up_name", "") or getattr(content, "author_name", ""),
    )


def frontier_tags_for_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convenience for tests/audits: assess a batch and return compact rows."""
    output: list[dict[str, Any]] = []
    for row in rows:
        assessment = assess_ai_frontier_row(row)
        output.append(
            {
                "title": str(row.get("title", "")),
                "source_platform": str(row.get("source_platform", "")),
                "score": assessment.score,
                "is_frontier": assessment.is_frontier,
                "tags": list(assessment.tags),
                "matched": list(assessment.matched),
            }
        )
    return output
