"""The catalog's theme contract.

One token system owns both appearances: ``tokens.css`` prints the light
room and the night reading room, the only colour control the user keeps is
the stamp hue, and every surface draws from tokens rather than literals.
"""

import re
from pathlib import Path
from tests._design_css import DESIGN_DIR, read_desktop_css

APP_CSS = read_desktop_css()
TOKENS_CSS = (DESIGN_DIR / "tokens.css").read_text(encoding="utf-8")
APP_JS = Path("src/openbiliclaw/web/desktop/assets/js/app.js")
INDEX_HTML = Path("src/openbiliclaw/web/desktop/index.html")


def test_tokens_declare_explicit_and_auto_dark_blocks() -> None:
    assert ':root[data-theme="dark"] {' in TOKENS_CSS
    assert "@media (prefers-color-scheme: dark)" in TOKENS_CSS
    assert ':root:not([data-theme="light"])' in TOKENS_CSS
    assert "color-scheme: dark;" in TOKENS_CSS
    assert "color-scheme: light;" in TOKENS_CSS


def test_only_tokens_carry_literal_colors() -> None:
    """Every surface prints from tokens; hex literals live in tokens.css alone."""
    offenders: list[str] = []
    for path in sorted(DESIGN_DIR.rglob("*.css")):
        if path.name == "tokens.css":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("/*", 1)[0]
            if re.search(r"#[0-9a-fA-F]{3,8}\b", code):
                offenders.append(f"{path.parent.name}/{path.name}: {line.strip()}")
    assert not offenders, offenders


def test_the_stamp_hue_is_the_only_colour_control() -> None:
    assert "--hue: var(--hue-primary, 8);" in TOKENS_CSS
    assert "--stamp: hsl(var(--hue)" in TOKENS_CSS
    assert "--stamp-soft: hsl(var(--hue)" in TOKENS_CSS


def test_index_bootstraps_theme_before_design_layer_without_flash() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert '<meta name="color-scheme" content="light dark">' in html
    assert "obc.theme" in html
    assert "document.documentElement.dataset.theme" in html
    first_sheet = html.index('href="/shared/design/tokens.css"')
    assert html.index("obc.theme") < first_sheet
    assert "<script src=" not in html[:first_sheet]


def test_app_js_contains_three_state_theme_cycle_and_storage_key() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert 'const THEME_STORAGE_KEY = "obc.theme";' in js
    assert 'const THEME_OPTIONS = ["auto", "light", "dark"];' in js
    assert "storageGet(THEME_STORAGE_KEY)" in js
    assert "storageSet(THEME_STORAGE_KEY, state.themeMode);" in js
    assert "cycleThemeMode" in js
    assert "跟随系统" in js
    assert "浅色" in js
    assert "深色" in js


def test_theme_controls_exist_in_topbar_and_frontend_settings() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")

    assert 'id="themeToggleBtn"' in html
    assert 'id="themeModeSetting"' in html
    assert 'data-theme-choice="auto"' in html
    assert 'data-theme-choice="light"' in html
    assert 'data-theme-choice="dark"' in html
    assert 'safeBind("#themeToggleBtn", "click", cycleThemeMode);' in js
    assert "renderThemeControls();" in js


def test_retired_accent_engine_and_notice_are_gone() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "classic.css" not in html
    assert 'data-accent-choice' not in html
    assert 'id="themeAccentSetting"' not in html
    assert 'id="themeNotice"' not in html
    assert html.index("obc.theme") < html.index('href="/shared/design/tokens.css"')


def test_hue_control_stays_keyboard_accessible() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    css = APP_CSS

    assert 'id="themeModeSetting" role="radiogroup"' in html
    assert 'id="themeHueSetting" role="radiogroup"' in html
    assert html.count('role="radio"') >= 15
    assert "bindRovingChoiceGroup" in js
    for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"):
        assert key in js
    assert "enhanceSelects" not in js
    assert ".custom-select" not in css
    assert "select:focus-visible" in css
    assert "outline: none;" in css and "box-shadow: var(--focus-ring);" in css


def test_coarse_pointer_controls_keep_minimum_touch_targets() -> None:
    assert "@media (pointer: coarse), (max-width: 820px)" in APP_CSS
    assert ".feedback-icon-btn" in APP_CSS
    assert "min-height: 44px;" in APP_CSS


def test_ink_on_card_meets_wcag_aaa_contrast_in_both_themes() -> None:
    def block(selector: str) -> str:
        return TOKENS_CSS.split(selector, 1)[1].split("}", 1)[0]

    def hex_token(source: str, name: str) -> str:
        match = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}});", source)
        assert match is not None, name
        return match.group(1)

    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light = block(":root {")
    dark = block(':root[data-theme="dark"] {')
    for source in (light, dark):
        ink = luminance(hex_token(source, "ink"))
        card = luminance(hex_token(source, "card"))
        ratio = (max(ink, card) + 0.05) / (min(ink, card) + 0.05)
        assert ratio >= 7, ratio