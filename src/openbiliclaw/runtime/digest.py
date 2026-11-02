"""每日日报（daily digest）：构建、存档、推送、调度。

每天到 ``[digest].send_time`` 把三类内容汇总成一份日报：

* **高分推荐** —— 发现池 relevance 排序的头部条目（``get_pool_candidates``，
  与 serve() 同一套 admission / delight-claim / 主题窗口门槛）；
* **惊喜（delight）** —— 尚未投递的高 delight_score 条目；
* **认知更新** —— 画像/口味的近期变化（``cognition_updates.json``）。

日报先落库（``digest_issues``，同日幂等 upsert），再并发推送到已配置渠道
（webhook / Bark）。渠道失败不回滚存档：失败详情写进 ``delivery_json``，
设置页可见。调度幂等性由「同日仅一份」+ 1 小时尝试退避共同保证——空池或
渠道全挂时不会每个 tick 都重试外发。

v0 范围：桌面 Web 设置 + 存档查看 + API；extension popup / 移动端 / CLI
暂不接入（推送型功能，Bark/webhook 直达手机）。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from openbiliclaw.network import httpx_kwargs_for_endpoint
from openbiliclaw.runtime.producer_cadence import (
    producer_ran_within,
    record_producer_run,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

logger = logging.getLogger(__name__)

__all__ = [
    "BarkChannel",
    "ChannelResult",
    "DigestChannel",
    "DigestDraft",
    "DigestScheduler",
    "WebhookChannel",
    "build_daily_digest",
    "build_senders",
    "run_digest_once",
    "seconds_until_send_time",
    "send_time_today",
]

# Cadence ledger keys. The attempt key gives an hourly floor on retries so an
# empty pool / dead webhook never turns the 60s tick into an outbound storm.
_DIGEST_LEDGER_PLATFORM = "daily_digest"
_DIGEST_ATTEMPT_LEDGER_PLATFORM = "daily_digest_attempt"
# Bark 通知正文上限：通知横幅展示不了长文，超出部分截断。
_BARK_BODY_MAX_CHARS = 500


@dataclass
class DigestDraft:
    """One built-but-not-yet-persisted daily digest."""

    digest_date: str
    title: str
    body_text: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def item_count(self) -> int:
        return int(self.payload.get("item_count", 0) or 0)


@dataclass
class ChannelResult:
    """Outcome of one push channel attempt."""

    channel: str
    ok: bool
    detail: str = ""


class DigestChannel(Protocol):
    """A push channel that can deliver one digest."""

    name: str

    async def send(self, draft: DigestDraft) -> ChannelResult: ...


def _text(row: Mapping[str, Any], *keys: str, default: str = "") -> str:
    """First non-empty string among ``keys``, defensive for schema drift."""
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _section_items(
    rows: list[Mapping[str, Any]],
    *,
    kind: str,
    title_keys: tuple[str, ...],
    reason_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        title = _text(row, *title_keys)
        if not title:
            continue
        items.append(
            {
                "kind": kind,
                "title": title,
                "url": _text(row, "content_url", "url"),
                "platform": _text(row, "source_platform", "source"),
                "topic": _text(row, "pool_topic_label", "topic"),
                "reason": _text(row, *reason_keys),
            }
        )
    return items


def build_daily_digest(
    database: Any,
    memory_manager: Any,
    *,
    top_n: int = 10,
    include_delight: bool = True,
    include_cognition: bool = True,
    now: datetime | None = None,
) -> DigestDraft:
    """Build today's digest from the discovery pool, delight queue, cognition.

    Every source is best-effort: a broken reader logs and degrades to an
    empty section instead of failing the whole digest — the digest should
    still go out with whatever it has.
    """
    now = now or datetime.now()
    digest_date = now.strftime("%Y-%m-%d")

    top_rows: list[Mapping[str, Any]] = []
    try:
        top_rows = list(database.get_pool_candidates(limit=max(1, int(top_n))))
    except Exception:
        logger.exception("digest: 读取发现池高分条目失败")
    top_picks = _section_items(
        top_rows[: max(1, int(top_n))],
        kind="top_pick",
        title_keys=("title",),
        reason_keys=("pool_expression", "relevance_reason"),
    )

    delight_items: list[dict[str, Any]] = []
    if include_delight:
        delight_rows: list[Mapping[str, Any]] = []
        try:
            delight_rows = list(database.get_delight_candidates(min_delight_score=0.85, limit=3))
        except Exception:
            logger.exception("digest: 读取惊喜候选失败")
        delight_items = _section_items(
            delight_rows,
            kind="delight",
            title_keys=("title",),
            reason_keys=("delight_hook", "pool_expression"),
        )

    cognition_items: list[dict[str, Any]] = []
    if include_cognition:
        try:
            updates = list(memory_manager.load_cognition_updates())
        except Exception:
            logger.exception("digest: 读取认知更新失败")
            updates = []
        for item in updates[-3:]:
            summary = _text(item, "summary")
            if not summary:
                continue
            cognition_items.append(
                {
                    "kind": "cognition",
                    "title": summary,
                    "created_at": _text(item, "created_at", "timestamp"),
                }
            )

    payload: dict[str, Any] = {
        "digest_date": digest_date,
        "top_picks": top_picks,
        "delight": delight_items,
        "cognition": cognition_items,
        "item_count": len(top_picks) + len(delight_items) + len(cognition_items),
    }
    return DigestDraft(
        digest_date=digest_date,
        title=f"OpenBiliClaw 日报 · {digest_date}",
        body_text=render_digest_text(payload),
        payload=payload,
    )


def render_digest_text(payload: Mapping[str, Any]) -> str:
    """Render the plain-text digest body shared by all push channels."""
    lines: list[str] = []
    top_picks = payload.get("top_picks") or []
    if top_picks:
        lines.append("【高分推荐】")
        for index, item in enumerate(top_picks, start=1):
            line = f"{index}. {item.get('title', '')}"
            reason = str(item.get("reason", "")).strip()
            if reason:
                line += f" —— {reason}"
            lines.append(line)
    delight = payload.get("delight") or []
    if delight:
        lines.append("")
        lines.append("【惊喜】")
        for item in delight:
            lines.append(f"· {item.get('title', '')}")
    cognition = payload.get("cognition") or []
    if cognition:
        lines.append("")
        lines.append("【认知更新】")
        for item in cognition:
            lines.append(f"· {item.get('title', '')}")
    if not lines:
        lines.append("今天没有可汇总的新内容。")
    return "\n".join(lines)


class WebhookChannel:
    """POST the full digest JSON to a user-supplied webhook endpoint."""

    name = "webhook"

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._timeout = timeout
        # Test seam: a supplied transport wins so unit tests never touch the
        # network; production follows the shared proxy-routing policy.
        self._transport = transport

    async def send(self, draft: DigestDraft) -> ChannelResult:
        payload = {
            "title": draft.title,
            "digest_date": draft.digest_date,
            "text": draft.body_text,
            "item_count": draft.item_count,
            "payload": draft.payload,
        }
        try:
            kwargs: dict[str, Any] = {"timeout": self._timeout}
            if self._transport is not None:
                kwargs["transport"] = self._transport
            else:
                kwargs.update(httpx_kwargs_for_endpoint(self._url))
            async with httpx.AsyncClient(**kwargs) as client:
                response = await client.post(self._url, json=payload)
        except Exception as exc:  # noqa: BLE001 — channel errors are results, not crashes
            return ChannelResult(self.name, False, f"{type(exc).__name__}: {exc}")
        if response.status_code >= 400:
            return ChannelResult(self.name, False, f"HTTP {response.status_code}")
        return ChannelResult(self.name, True, f"HTTP {response.status_code}")


class BarkChannel:
    """Push via a Bark server (iOS). ``base_url`` includes the device key."""

    name = "bark"

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def send(self, draft: DigestDraft) -> ChannelResult:
        body = draft.body_text
        if len(body) > _BARK_BODY_MAX_CHARS:
            body = body[: _BARK_BODY_MAX_CHARS - 1] + "…"
        payload = {"title": draft.title, "body": body, "group": "openbiliclaw-digest"}
        try:
            kwargs: dict[str, Any] = {"timeout": self._timeout}
            if self._transport is not None:
                kwargs["transport"] = self._transport
            else:
                kwargs.update(httpx_kwargs_for_endpoint(self._base_url))
            async with httpx.AsyncClient(**kwargs) as client:
                response = await client.post(self._base_url, json=payload)
        except Exception as exc:  # noqa: BLE001 — channel errors are results, not crashes
            return ChannelResult(self.name, False, f"{type(exc).__name__}: {exc}")
        if response.status_code >= 400:
            return ChannelResult(self.name, False, f"HTTP {response.status_code}")
        return ChannelResult(self.name, True, f"HTTP {response.status_code}")


def build_senders(digest_config: Any) -> list[DigestChannel]:
    """Instantiate one channel per configured URL, in config order."""
    senders: list[DigestChannel] = []
    if digest_config.webhook_url:
        senders.append(WebhookChannel(digest_config.webhook_url))
    if digest_config.bark_url:
        senders.append(BarkChannel(digest_config.bark_url))
    return senders


async def run_digest_once(
    database: Any,
    memory_manager: Any,
    *,
    digest_config: Any,
    senders: list[DigestChannel] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build, archive and push one digest. Shared by scheduler and run-now.

    Returns ``{"created", "issue", "delivery", "message"}``. Archiving is
    idempotent per local day (upsert), so a retry replaces today's issue
    instead of duplicating it. Channel failures never discard the archive.
    """
    now = now or datetime.now()
    draft = build_daily_digest(
        database,
        memory_manager,
        top_n=digest_config.top_n,
        include_delight=digest_config.include_delight,
        include_cognition=digest_config.include_cognition,
        now=now,
    )
    if draft.item_count == 0:
        return {
            "created": False,
            "issue": None,
            "delivery": [],
            "message": "没有可汇总的内容（发现池、惊喜、认知更新均为空）",
        }

    active_senders = build_senders(digest_config) if senders is None else senders
    results: list[ChannelResult] = []
    if active_senders:
        results = list(await asyncio.gather(*(sender.send(draft) for sender in active_senders)))
        for result in results:
            if not result.ok:
                logger.warning("digest: 渠道 %s 推送失败：%s", result.channel, result.detail)

    delivery = [asdict(result) for result in results]
    try:
        digest_id = database.upsert_digest_issue(
            digest_date=draft.digest_date,
            title=draft.title,
            body_text=draft.body_text,
            payload=draft.payload,
            delivery=delivery,
        )
        issue = database.get_digest_issue(digest_id)
    except Exception:
        logger.exception("digest: 日报存档失败")
        return {"created": False, "issue": None, "delivery": delivery, "message": "日报存档失败"}
    return {"created": True, "issue": issue, "delivery": delivery, "message": ""}


def send_time_today(send_time: str, now: datetime) -> datetime:
    """Today's local ``HH:MM`` send moment (no day rollover)."""
    hour_text, minute_text = send_time.split(":", 1)
    return now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)


def seconds_until_send_time(send_time: str, now: datetime) -> int:
    """Seconds until the next send moment (rolls to tomorrow when passed)."""
    target = send_time_today(send_time, now)
    if target <= now:
        target += timedelta(days=1)
    return max(0, int((target - now).total_seconds()))


class DigestScheduler:
    """Daily-time digest trigger riding the refresh loop family.

    Idempotence layering (outermost first):

    1. ``[digest].enabled`` gate — a disabled digest never sends;
    2. ``digest_issues`` same-day unique key — at most one issue per day;
    3. hourly attempt ledger — an empty pool or dead webhook retries at
       most once per hour instead of every tick.
    """

    def __init__(
        self,
        database: Any,
        memory_manager: Any,
        *,
        check_interval_seconds: int = 60,
        now_fn: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._database = database
        self._memory_manager = memory_manager
        self._check_interval_seconds = max(30, int(check_interval_seconds))
        self._now_fn = now_fn

    async def run_forever(self) -> None:
        """Tick on the shared interval; a broken tick never kills the loop."""
        while True:
            with suppress(Exception):
                await self.tick()
            await asyncio.sleep(self._check_interval_seconds)

    async def tick(self) -> dict[str, Any]:
        """Run the due-check + build + send cycle once."""
        from openbiliclaw.config import load_config

        digest_config = load_config().digest
        if not digest_config.enabled:
            return {"skipped": "disabled"}
        now = self._now_fn()
        try:
            latest = self._database.get_latest_digest_issue()
        except Exception:
            logger.exception("digest: 读取最新日报失败")
            latest = None
        if latest and latest.get("digest_date") == now.strftime("%Y-%m-%d"):
            return {"skipped": "already_sent_today"}
        if now < send_time_today(digest_config.send_time, now):
            return {"skipped": "before_send_time"}
        if producer_ran_within(self._database, _DIGEST_ATTEMPT_LEDGER_PLATFORM, 60):
            return {"skipped": "attempt_backoff"}
        record_producer_run(self._database, _DIGEST_ATTEMPT_LEDGER_PLATFORM, 1)
        result = await run_digest_once(
            self._database,
            self._memory_manager,
            digest_config=digest_config,
            now=now,
        )
        if result.get("created"):
            record_producer_run(self._database, _DIGEST_LEDGER_PLATFORM, 1)
        return result

    async def run_now(self) -> dict[str, Any]:
        """Manual trigger: build+send immediately, ignoring time gates."""
        from openbiliclaw.config import load_config

        digest_config = load_config().digest
        return await run_digest_once(
            self._database,
            self._memory_manager,
            digest_config=digest_config,
            now=self._now_fn(),
        )
