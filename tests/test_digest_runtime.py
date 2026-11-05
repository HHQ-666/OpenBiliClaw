"""Digest runtime: builder, renderer, channels, run-once, scheduler gates."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from openbiliclaw.runtime.digest import (
    BarkChannel,
    ChannelResult,
    DigestScheduler,
    WebhookChannel,
    build_daily_digest,
    build_senders,
    render_digest_text,
    run_digest_once,
    seconds_until_send_time,
    send_time_today,
)


def _db(tmp_path: Path):
    from openbiliclaw.storage.database import Database

    db = Database(tmp_path / "digest.db")
    db.initialize()
    return db


def _insert_pool_row(db, bvid: str, title: str, score: float = 0.9) -> None:
    db.conn.execute(
        """INSERT INTO content_cache
               (bvid, title, content_url, source_platform, pool_status,
                pool_expression, pool_topic_label, style_key, topic_group,
                relevance_score)
           VALUES (?, ?, ?, 'bilibili', 'fresh', ?, 'AI', 'tech', 'ai', ?)""",
        (bvid, title, f"https://www.bilibili.com/video/{bvid}", f"很对{title}口味", score),
    )
    db.conn.commit()


def test_build_daily_digest_sections(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_pool_row(db, "BV1a", "视频A", 0.92)
    _insert_pool_row(db, "BV1b", "视频B", 0.88)
    memory = SimpleNamespace(
        load_cognition_updates=lambda: [
            {"summary": "开始关注本地 LLM", "created_at": "2026-11-01T08:00:00"}
        ]
    )

    draft = build_daily_digest(db, memory, top_n=5, now=datetime(2026, 11, 1, 9, 0))

    assert draft.digest_date == "2026-11-01"
    assert draft.payload["item_count"] == 3
    assert [item["title"] for item in draft.payload["top_picks"]] == ["视频A", "视频B"]
    assert draft.payload["cognition"][0]["title"] == "开始关注本地 LLM"
    assert "【高分推荐】" in draft.body_text
    assert "【认知更新】" in draft.body_text


def test_build_daily_digest_tolerates_broken_readers(tmp_path: Path) -> None:
    db = _db(tmp_path)

    def boom() -> list[dict[str, object]]:
        raise RuntimeError("broken")

    memory = SimpleNamespace(load_cognition_updates=boom)

    draft = build_daily_digest(db, memory, now=datetime(2026, 11, 1, 9, 0))

    assert draft.item_count == 0


def test_render_digest_text_empty() -> None:
    text = render_digest_text({"top_picks": [], "delight": [], "cognition": []})

    assert "没有可汇总" in text


def test_webhook_channel_posts_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.read()
        return httpx.Response(200)

    channel = WebhookChannel(
        "https://hooks.example.com/abc", transport=httpx.MockTransport(handler)
    )
    draft = build_daily_digest(
        _db(Path(__import__("tempfile").mkdtemp())),
        SimpleNamespace(load_cognition_updates=lambda: []),
        now=datetime(2026, 11, 1, 9, 0),
    )
    draft.payload["item_count"] = 1

    result = asyncio.run(channel.send(draft))

    assert result.ok is True
    assert seen["url"] == "https://hooks.example.com/abc"
    body = __import__("json").loads(seen["json"])
    assert body["title"] == draft.title
    assert body["digest_date"] == "2026-11-01"


def test_webhook_channel_supports_feishu_and_wecom() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.read()
        return httpx.Response(200)

    draft = build_daily_digest(
        _db(Path(__import__("tempfile").mkdtemp())),
        SimpleNamespace(load_cognition_updates=lambda: []),
        now=datetime(2026, 11, 1, 9, 0),
    )

    # Feishu webhook
    feishu = WebhookChannel(
        "https://open.feishu.cn/open-apis/bot/v2/hook/xxx", transport=httpx.MockTransport(handler)
    )
    result_feishu = asyncio.run(feishu.send(draft))
    assert result_feishu.ok is True
    feishu_body = __import__("json").loads(seen["json"])
    assert feishu_body["msg_type"] == "post"
    assert "zh_cn" in feishu_body["content"]["post"]

    # WeCom webhook
    wecom = WebhookChannel(
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
        transport=httpx.MockTransport(handler),
    )
    result_wecom = asyncio.run(wecom.send(draft))
    assert result_wecom.ok is True
    wecom_body = __import__("json").loads(seen["json"])
    assert wecom_body["msg_type"] == "markdown"
    assert "###" in wecom_body["markdown"]["content"]


def test_webhook_channel_reports_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    channel = WebhookChannel(
        "https://hooks.example.com/abc", transport=httpx.MockTransport(handler)
    )
    draft = build_daily_digest(
        _db(Path(__import__("tempfile").mkdtemp())),
        SimpleNamespace(load_cognition_updates=lambda: []),
        now=datetime(2026, 11, 1, 9, 0),
    )

    result = asyncio.run(channel.send(draft))

    assert result.ok is False
    assert "HTTP 500" in result.detail


def test_bark_channel_posts_title_and_body() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.read()
        return httpx.Response(200)

    channel = BarkChannel("https://api.day.app/abc/", transport=httpx.MockTransport(handler))
    draft = build_daily_digest(
        _db(Path(__import__("tempfile").mkdtemp())),
        SimpleNamespace(load_cognition_updates=lambda: []),
        now=datetime(2026, 11, 1, 9, 0),
    )
    draft.payload["item_count"] = 1

    result = asyncio.run(channel.send(draft))

    assert result.ok is True
    assert seen["url"] == "https://api.day.app/abc"
    body = __import__("json").loads(seen["json"])
    assert body["title"] == draft.title
    assert body["group"] == "openbiliclaw-digest"


def test_build_senders_follows_config() -> None:
    empty = build_senders(SimpleNamespace(webhook_url="", bark_url=""))
    both = build_senders(SimpleNamespace(webhook_url="https://h", bark_url="https://b"))

    assert empty == []
    assert [sender.name for sender in both] == ["webhook", "bark"]


def test_run_digest_once_archives_and_delivers(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_pool_row(db, "BV1c", "视频C")
    memory = SimpleNamespace(load_cognition_updates=lambda: [])

    async def fake_send(draft):
        return ChannelResult("bark", True, "ok")

    sender = SimpleNamespace(name="bark", send=fake_send)
    config = SimpleNamespace(top_n=10, include_delight=True, include_cognition=True)

    result = asyncio.run(
        run_digest_once(
            db,
            memory,
            digest_config=config,
            senders=[sender],  # type: ignore[list-item]
            now=datetime(2026, 11, 1, 9, 0),
        )
    )

    assert result["created"] is True
    assert result["issue"]["delivery"][0]["channel"] == "bark"
    # Same-day rerun upserts in place.
    result2 = asyncio.run(
        run_digest_once(
            db, memory, digest_config=config, senders=[], now=datetime(2026, 11, 1, 10, 0)
        )
    )
    assert result2["issue"]["id"] == result["issue"]["id"]
    assert db.conn.execute("SELECT COUNT(*) FROM digest_issues").fetchone()[0] == 1


def test_run_digest_once_skips_empty_pool(tmp_path: Path) -> None:
    db = _db(tmp_path)
    memory = SimpleNamespace(load_cognition_updates=lambda: [])
    config = SimpleNamespace(top_n=10, include_delight=True, include_cognition=True)

    result = asyncio.run(
        run_digest_once(db, memory, digest_config=config, now=datetime(2026, 11, 1, 9, 0))
    )

    assert result["created"] is False
    assert "没有可汇总" in result["message"]


def test_send_time_helpers() -> None:
    now = datetime(2026, 11, 1, 7, 0)

    assert send_time_today("09:00", now) == datetime(2026, 11, 1, 9, 0)
    assert 0 < seconds_until_send_time("09:00", now) <= 2 * 3600
    # Past today's moment → rolls to tomorrow (>= 23h).
    assert seconds_until_send_time("06:00", now) >= 23 * 3600


def test_scheduler_tick_gates(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_pool_row(db, "BV1d", "视频D")
    memory = SimpleNamespace(load_cognition_updates=lambda: [])
    config = SimpleNamespace(
        top_n=10,
        include_delight=True,
        include_cognition=True,
        send_time="09:00",
        webhook_url="",
        bark_url="",
    )
    scheduler = DigestScheduler(db, memory, now_fn=lambda: datetime(2026, 11, 1, 8, 0))

    import openbiliclaw.config as config_module

    original = config_module.load_config
    config_module.load_config = lambda *a, **kw: SimpleNamespace(digest=config)  # type: ignore[assignment]
    try:
        # Disabled → never runs.
        config.enabled = False
        assert asyncio.run(scheduler.tick())["skipped"] == "disabled"
        # Enabled but before send time → waits.
        config.enabled = True
        assert asyncio.run(scheduler.tick())["skipped"] == "before_send_time"
        # After send time → sends, then same-day rerun is skipped.
        scheduler_later = DigestScheduler(db, memory, now_fn=lambda: datetime(2026, 11, 1, 9, 30))
        sent = asyncio.run(scheduler_later.tick())
        assert sent["created"] is True
        assert asyncio.run(scheduler_later.tick())["skipped"] == "already_sent_today"
    finally:
        config_module.load_config = original  # type: ignore[assignment]


def test_scheduler_backs_off_after_empty_attempt(tmp_path: Path) -> None:
    db = _db(tmp_path)
    memory = SimpleNamespace(load_cognition_updates=lambda: [])
    config = SimpleNamespace(
        enabled=True,
        top_n=10,
        include_delight=True,
        include_cognition=True,
        send_time="09:00",
        webhook_url="",
        bark_url="",
    )
    scheduler = DigestScheduler(db, memory, now_fn=lambda: datetime(2026, 11, 1, 9, 0))

    import openbiliclaw.config as config_module

    original = config_module.load_config
    config_module.load_config = lambda *a, **kw: SimpleNamespace(digest=config)  # type: ignore[assignment]
    try:
        first = asyncio.run(scheduler.tick())
        assert first["created"] is False
        second = asyncio.run(scheduler.tick())
        assert second["skipped"] == "attempt_backoff"
    finally:
        config_module.load_config = original  # type: ignore[assignment]
