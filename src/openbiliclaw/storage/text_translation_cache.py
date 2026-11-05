"""Persistent cache of display-time Chinese renderings for card text.

Cards quote the source's own words: a tweet body, a Reddit title, a GitHub
repo description. For the non-Chinese sources that excerpt is unreadable to
the user the tray exists for, so the UI asks the LLM once per distinct string
and renders the Chinese from here on.

The cache is keyed by a hash of the *source text*, not by content id: the same
tweet reaches the recommendation tray, the library and the delight strip, and
all three should share one translation. It is a pure presentation cache — a
miss costs an LLM round-trip, never correctness — so it is created lazily and
read best-effort. Storage style mirrors ``storage.x_health``: a self-contained
table with short-lived connections instead of touching the main schema.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from openbiliclaw.storage.database import Database

logger = logging.getLogger(__name__)

_CACHE_TABLE_READY_ATTR = "_openbiliclaw_text_translation_cache_ready"
_CACHE_TABLE_INIT_LOCK = threading.Lock()

# Stored for inspection only (re-checking a rendering, spotting a bad batch);
# the hash below is what identity rests on.
_MAX_STORED_SOURCE_CHARS = 2000


def translation_cache_key(text: str) -> str:
    """Return the stable cache key for one source string.

    Whitespace is normalized first so the same tweet re-serialized with a
    trailing newline does not buy a second LLM call.
    """

    normalized = " ".join(str(text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class TextTranslationCache:
    """``text_translations``: source-text hash → Chinese rendering."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── plumbing ─────────────────────────────────────────────────────

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        """Yield a short-lived connection when the Database supports it.

        The cache is read from FastAPI's threadpool while runtime writers hold
        the process-wide connection; a separate connection lets SQLite
        serialize at the database boundary instead of nesting transactions.
        """

        open_connection = getattr(self._db, "open_connection", None)
        if callable(open_connection):
            conn = open_connection()
            try:
                yield conn
            finally:
                conn.close()
            return
        yield self._db.conn

    def _ensure_table_once(self) -> None:
        if bool(getattr(self._db, _CACHE_TABLE_READY_ATTR, False)):
            return
        with _CACHE_TABLE_INIT_LOCK:
            if bool(getattr(self._db, _CACHE_TABLE_READY_ATTR, False)):
                return
            self._ensure_table()
            setattr(self._db, _CACHE_TABLE_READY_ATTR, True)

    def _ensure_table(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS text_translations (
                    text_hash   TEXT PRIMARY KEY,
                    source_text TEXT NOT NULL DEFAULT '',
                    text_zh     TEXT NOT NULL DEFAULT '',
                    model       TEXT NOT NULL DEFAULT '',
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    # ── reads / writes ───────────────────────────────────────────────

    def get_many(self, keys: Sequence[str]) -> dict[str, str]:
        """Return the cached renderings for *keys*; misses are simply absent."""

        wanted = [str(key) for key in keys if str(key or "").strip()]
        if not wanted:
            return {}
        hits: dict[str, str] = {}
        try:
            self._ensure_table_once()
            with self._connection() as conn:
                # Chunked so a 40-card tray does not blow past SQLite's
                # variable limit on some builds.
                for start in range(0, len(wanted), 200):
                    chunk = wanted[start : start + 200]
                    placeholders = ",".join("?" * len(chunk))
                    rows = conn.execute(
                        "SELECT text_hash, text_zh FROM text_translations "
                        f"WHERE text_hash IN ({placeholders})",
                        chunk,
                    ).fetchall()
                    for row in rows:
                        rendered = str(row["text_zh"] or "").strip()
                        if rendered:
                            hits[str(row["text_hash"])] = rendered
        except Exception:
            # A presentation cache must never take the page down with it.
            logger.debug("text translation cache read failed", exc_info=True)
            return {}
        return hits

    def put_many(
        self,
        rows: Mapping[str, tuple[str, str]],
        *,
        model: str = "",
    ) -> int:
        """Store ``key -> (source_text, text_zh)``; returns how many landed."""

        entries = [
            (
                str(key),
                str(source)[:_MAX_STORED_SOURCE_CHARS],
                str(rendered).strip(),
                str(model or ""),
            )
            for key, (source, rendered) in rows.items()
            if str(key or "").strip() and str(rendered or "").strip()
        ]
        if not entries:
            return 0
        written = 0
        try:
            self._ensure_table_once()
            with self._connection() as conn:
                conn.executemany(
                    "INSERT INTO text_translations (text_hash, source_text, text_zh, model) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(text_hash) DO UPDATE SET "
                    "text_zh = excluded.text_zh, model = excluded.model",
                    entries,
                )
                conn.commit()
                written = len(entries)
        except Exception:
            logger.debug("text translation cache write failed", exc_info=True)
            return 0
        return written
