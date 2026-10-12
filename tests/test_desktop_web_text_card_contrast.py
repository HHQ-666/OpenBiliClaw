"""Text media prints on opaque card stock in the theme's own ink.

A coverless post (知乎 / B 站 / Reddit 长文, X 推文) must never fall back to a
translucent wash or a low-contrast gradient: the clipping is opaque stock and
its copy uses the surface's foreground ink.
"""

import re

from tests._design_css import read_desktop_css

APP_CSS = read_desktop_css()


def _rule(selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}", APP_CSS, flags=re.S)
    assert match is not None, f"CSS rule not found: {selector}"
    return match.group("body")


def test_delight_text_media_uses_theme_foreground_over_surface_tints() -> None:
    base = _rule(".delight .thumb.is-text-media")
    copy = _rule(".delight-text-media-copy")

    assert "background-color: var(--card-sunk);" in base
    assert "border: 1px solid var(--rule-soft);" in base
    assert "color: var(--ink);" in base
    assert "color: var(--ink);" in copy
    assert "color: var(--ink-2);" not in copy

    for platform in ("zhihu", "bilibili", "reddit"):
        platform_rule = _rule(f'.delight .thumb.is-text-media[data-platform="{platform}"]')
        assert "background-color: color-mix(in srgb, var(--card-sunk)," in platform_rule


def test_desktop_coverless_text_cards_keep_opaque_theme_surface() -> None:
    cover = _rule(".cover.is-text-card:not(.has-backdrop)")
    cover_text = _rule(".cover.is-text-card:not(.has-backdrop) .cover-text")

    assert "background-color: var(--card)" in cover or "var(--card-sunk)" in cover
    assert "border: 1px solid var(--rule-soft);" in cover
    assert "color: var(--ink);" in cover_text
    assert "text-shadow: none;" in cover_text


def test_every_appearance_keeps_text_media_opaque() -> None:
    """No theme — explicit or automatic — may restore a translucent text ground."""
    delight = _rule(".delight .thumb.is-text-media")
    cover = _rule(".cover.is-text-card:not(.has-backdrop)")

    for rule in (delight, cover):
        assert "background-color:" in rule
    assert "background: (transparent" not in delight
    assert "transparent 8%" not in cover
    # the retired accent engine is gone: nothing scopes print to it any more.
    assert 'data-accent="classic"' not in APP_CSS
