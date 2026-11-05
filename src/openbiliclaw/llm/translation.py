"""Display-time Chinese renderings of non-Chinese card text.

The tray quotes a source's own words: an X tweet body, a Reddit title, a
GitHub repo description. For every non-Chinese source that excerpt reaches a
reader who cannot read it — including the user this local install exists for.
This module renders those strings into Simplified Chinese, once per distinct
string, and the result is cached by :mod:`openbiliclaw.storage.text_translation_cache`
so a later card with the same words costs nothing.

It is deliberately *not* part of the evaluation or recommendation pipeline:
translation is presentation. Nothing here can change what gets recommended, and
a failed call degrades to showing the original text rather than an error.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from openbiliclaw.llm.json_utils import extract_llm_json_list

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# CJK ideographs plus kana and CJK punctuation: enough to answer "is this
# already readable to a Chinese reader" without a language detector.
_CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
# Links survive translation untouched, so a card whose whole text is a URL has
# nothing to render.
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# Below this, a string is a label or a fragment ("RT", "3.4k", "v2.0") and
# translating it is noise.
MIN_TRANSLATABLE_CHARS = 8
# A card shows two title lines and a six-line excerpt (~120 Chinese
# characters); the tail of a 5000-character thread never reaches the screen.
MAX_TRANSLATABLE_CHARS = 600
# Per LLM call. Small enough that a slow local model cannot blow the request
# budget, large enough that a first-load tray settles in two or three calls.
MAX_TEXTS_PER_CALL = 8
MAX_CHARS_PER_CALL = 3000

_CALLER = "recommendation.translate_card_text"

TRANSLATION_SYSTEM_PROMPT = (
    "<task>\n"
    "卡片上要显示一段外语原文（推文正文、英文标题、仓库简介等），读中文的用户看不懂。"
    "把它翻成简体中文，供卡片直接展示。\n"
    "</task>\n\n"
    "<rules>\n"
    "1. 只输出严格 json 数组，长度与输入条目数一致，顺序一一对应；"
    '每项形如 {"id": "<原样带回输入里的 id>", "zh": "<简体中文译文>"}。\n'
    "2. 忠实翻译。不概括、不评论、不写推荐话术、不补充原文没有的信息，不改变语气。\n"
    "3. 专有名词、产品名、框架与库名、代码标识符、@用户名、URL、#话题标签保持原文；"
    "技术术语用通行中文译名，必要时在括号里保留英文原名（例如「连接池（connection pool）」）。\n"
    "4. 保留原文的段落结构：原文的空行在译文里照旧。\n"
    "5. 输入本身就是中文、或只有数字符号表情的条目，把原文放进 zh 原样返回。\n"
    "6. 不要输出 Markdown 代码块，不要任何多余说明。\n"
    "</rules>"
)


def needs_translation(text: str) -> bool:
    """Whether *text* is worth rendering into Chinese before display.

    True only for strings that carry latin words and no CJK at all: a mixed
    string ("RAG 是什么"), a number, a URL, or an emoji run is already fine.
    """

    collapsed = " ".join(str(text or "").split())
    collapsed = _URL_RE.sub(" ", collapsed).strip()
    if len(collapsed) < MIN_TRANSLATABLE_CHARS:
        return False
    if _CJK_RE.search(collapsed):
        return False
    return bool(_LATIN_RE.search(collapsed))


def translatable_excerpt(text: str) -> str:
    """The part of *text* worth spending tokens on."""

    collapsed = str(text or "").strip()
    if len(collapsed) <= MAX_TRANSLATABLE_CHARS:
        return collapsed
    # Cut on a word boundary so the model is not handed half a word.
    head = collapsed[:MAX_TRANSLATABLE_CHARS]
    space = head.rfind(" ")
    return (head[:space] if space > MAX_TRANSLATABLE_CHARS // 2 else head).strip()


def build_translation_messages(entries: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    """Build the prompt for one batch of ``(id, text)`` pairs.

    The system half is the module-level constant so providers that cache
    prompts keep hitting the same prefix across batches.
    """

    lines = ["<items>"]
    for item_id, text in entries:
        lines.append(f'<item id="{item_id}">')
        lines.append(str(text))
        lines.append("</item>")
    lines.append("</items>")
    return [
        {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


def parse_translation_items(
    content: str,
    expected_ids: Sequence[str],
) -> dict[str, str]:
    """Map ``id -> zh`` from an LLM response; unknown or missing ids dropped."""

    payload = extract_llm_json_list(
        str(content or ""),
        wrapper_keys=("translations", "items", "results", "data"),
        allow_singleton=True,
        item_predicate=lambda item: "zh" in item or "translation" in item or "text" in item,
    )
    if not payload:
        return {}
    wanted = {str(item_id) for item_id in expected_ids}
    rendered: dict[str, str] = {}
    for item in payload:
        item_id = str(item.get("id", "")).strip()
        if item_id not in wanted:
            continue
        translated = str(item.get("zh") or item.get("translation") or item.get("text") or "")
        if translated.strip():
            rendered[item_id] = translated.strip()
    return rendered


def chunk_translation_entries(
    entries: Sequence[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    """Split ``(id, text)`` pairs into per-call batches within the budget."""

    batches: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_chars = 0
    for item_id, text in entries:
        length = len(text)
        if current and (
            len(current) >= MAX_TEXTS_PER_CALL or current_chars + length > MAX_CHARS_PER_CALL
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append((item_id, text))
        current_chars += length
    if current:
        batches.append(current)
    return batches


async def translate_batch(
    llm_service: Any,
    entries: Sequence[tuple[str, str]],
    *,
    caller: str = _CALLER,
    timeout: float = 30.0,
) -> dict[str, str]:
    """Translate one batch through ``LLMService.complete_structured_task``.

    Returns ``{}`` on any failure (timeout, provider error, malformed output):
    a caller that cannot get a rendering shows the original text, and a card is
    never worth surfacing an LLM error for.
    """

    if not entries or llm_service is None:
        return {}
    complete = getattr(llm_service, "complete_structured_task", None)
    if not callable(complete):
        return {}

    messages = build_translation_messages(entries)
    expected_ids = [item_id for item_id, _ in entries]
    try:
        response = await asyncio.wait_for(
            complete(
                system_instruction=messages[0]["content"],
                user_input=messages[1]["content"],
                temperature=0.2,
                max_tokens=4096,
                caller=caller,
                # Translation is mechanical; a reasoning chain only adds
                # latency and tokens.
                reasoning_effort="",
                inject_core_memory=False,
            ),
            timeout=timeout,
        )
    except Exception:
        logger.debug("card text translation call failed", exc_info=True)
        return {}

    rendered = parse_translation_items(str(getattr(response, "content", "") or ""), expected_ids)
    if len(rendered) < len(expected_ids):
        logger.debug(
            "card text translation returned %d/%d items",
            len(rendered),
            len(expected_ids),
        )
    return rendered
