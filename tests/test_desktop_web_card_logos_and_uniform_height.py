import re
from pathlib import Path

APP_JS = Path("src/openbiliclaw/web/desktop/assets/js/app.js").read_text(encoding="utf-8")
APP_CSS = Path("src/openbiliclaw/web/desktop/assets/css/app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    pattern = rf"(?:^|\n)\s*{re.escape(selector)}\s*\{{(?P<body>.*?)\}}"
    match = re.search(pattern, APP_CSS, flags=re.S)
    assert match is not None, f"CSS rule not found: {selector}"
    return match.group("body")


def test_platform_brand_icons_map_contains_all_supported_platforms() -> None:
    """Verify that PLATFORM_BRAND_ICONS covers all desktop platforms with inline SVGs."""
    for platform in (
        "bilibili",
        "github",
        "linuxdo",
        "zhihu",
        "douyin",
        "xiaohongshu",
        "weibo",
        "youtube",
        "twitter",
        "reddit",
        "bangumi",
        "fallback",
    ):
        assert f"{platform}:" in APP_JS
        assert "<svg" in APP_JS


def test_recommendation_and_saved_cards_render_platform_svg_and_title() -> None:
    """Cards must render the platform brand SVG inside .platform with accessible tooltip."""
    assert "platformLogoSvg(item.platform)" in APP_JS
    assert "platformLogoSvg(savedPlatformRaw)" in APP_JS
    assert 'class="platform"' in APP_JS
    assert 'title="${escapeHtml(platformTitle)}"' in APP_JS
    assert 'aria-label="${escapeHtml(platformTitle)}"' in APP_JS
    assert 'title="${escapeHtml(savedPlatformTitle)}"' in APP_JS
    assert 'aria-label="${escapeHtml(savedPlatformTitle)}"' in APP_JS


def test_desktop_covers_enforce_uniform_16_to_9_ratio_for_all_cards() -> None:
    """All covers, including text cards and coverless cards, must enforce aspect-ratio: 16 / 9."""
    base_cover = _rule(".cover")
    assert "aspect-ratio: 16 / 9;" in base_cover

    text_cover = _rule(".cover.is-text-card")
    assert "aspect-ratio: 16 / 9;" in text_cover

    coverless = _rule(".cover.is-text-card.is-coverless")
    assert "aspect-ratio: 16 / 9;" in coverless
    # No min-height: 96px or max-height: 124px that causes vertical jaggedness
    assert "min-height: 96px" not in coverless
    assert "max-height: 124px" not in coverless


def test_desktop_platform_badge_css_styling_and_colors() -> None:
    """Platform badge is styled as a brand pill with SVG logo and label."""
    platform_base = _rule(".platform")
    assert "height: 24px;" in platform_base
    assert "padding: 0 8px 0 6px;" in platform_base
    assert "display: inline-flex;" in platform_base
    assert "align-items: center;" in platform_base
    assert "gap: 5px;" in platform_base

    platform_svg = _rule(".platform svg")
    assert "width: 14px;" in platform_svg
    assert "height: 14px;" in platform_svg

    assert ".platform .platform-name" in APP_CSS

    # Platform colors must cover video and text platforms
    assert '.platform[data-platform="github"]' in APP_CSS
    assert '.platform[data-platform="linuxdo"]' in APP_CSS
    assert '.platform[data-platform="bilibili"]' in APP_CSS
    assert '.platform[data-platform="zhihu"]' in APP_CSS
    assert '.platform[data-platform="weibo"]' in APP_CSS
    assert '.platform[data-platform="youtube"]' in APP_CSS
    assert '.platform[data-platform="douyin"]' in APP_CSS


def test_video_card_layout_ensures_uniform_height_and_aligned_actions() -> None:
    """Video cards use flex-column with height: 100% and flex reason to align across a row."""
    card_rule = _rule(".video-card")
    assert "display: flex;" in card_rule
    assert "flex-direction: column;" in card_rule
    assert "height: 100%;" in card_rule

    reason_rule = _rule(".reason")
    assert "flex: 1 1 auto;" in reason_rule
