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

# What a paper owns: ground, stock, ink, rules, hardware, its stamp default.
MATERIAL_TOKENS = (
    "--desk:",
    "--desk-deep:",
    "--desk-line:",
    "--card:",
    "--card-hi:",
    "--card-sunk:",
    "--ink:",
    "--ink-2:",
    "--ink-3:",
    "--rule:",
    "--rule-soft:",
    "--rule-strong:",
    "--brass:",
    "--hue-primary:",
)


def _root_block() -> str:
    match = re.search(r":root \{(?P<body>.*?)\n\}", TOKENS_CSS, flags=re.S)
    assert match is not None, ":root block not found"
    return match.group("body")


def _palette_block(name: str) -> str:
    match = re.search(
        rf':root\[data-palette="{name}"\]\s*\{{(?P<body>.*?)\n\}}',
        TOKENS_CSS,
        flags=re.S,
    )
    assert match is not None, f"paper block not found: {name}"
    return match.group("body")


def _hue_of(block: str) -> int:
    match = re.search(r"--hue-primary:\s*(\d+);", block)
    assert match is not None, "--hue-primary missing"
    return int(match.group(1))


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


def test_the_stamp_hue_is_the_only_accent_rotation() -> None:
    """The only per-user colour knob is the stamp's hue.

    Paper (``data-palette``) picks the *material* — desk, stock, metal; the
    stamp's colour still comes from one hue number, and every palette carries a
    default for it so a fresh install is never left without an accent.
    """

    assert "--hue: var(--hue-primary);" in TOKENS_CSS
    assert "--stamp: hsl(var(--hue)" in TOKENS_CSS
    assert "--stamp-soft: hsl(var(--hue)" in TOKENS_CSS
    for name in ("paper", "moss"):
        assert re.search(r"--hue-primary:\s*\d+;", _palette_block(name)) is not None
    assert re.search(r"--hue-primary:\s*\d+;", _root_block()) is not None


def test_every_paper_repaints_the_whole_material() -> None:
    """A paper may not be half-applied: each owns every material token.

    素白 has no ``[data-palette]`` block because it IS the ``:root`` default.
    """

    for name in ("paper", "moss"):
        block = _palette_block(name)
        for token in MATERIAL_TOKENS:
            assert token in block, (name, token)
    root = _root_block()
    for token in MATERIAL_TOKENS:
        assert token in root, token


def test_paper_default_hues_match_the_frontend_map() -> None:
    """tokens.css and app.js must agree on what each paper stamps with."""

    js = APP_JS.read_text(encoding="utf-8")
    match = re.search(r"const PALETTE_DEFAULT_HUE = \{([^}]*)\};", js)
    assert match is not None, "PALETTE_DEFAULT_HUE map missing"
    frontend = {key: int(value) for key, value in re.findall(r"(\w+):\s*(\d+)", match.group(1))}
    stylesheet = {
        "plain": _hue_of(_root_block()),
        "paper": _hue_of(_palette_block("paper")),
        "moss": _hue_of(_palette_block("moss")),
    }
    assert frontend == stylesheet
    assert set(frontend) == {"plain", "paper", "moss"}


def test_index_bootstraps_theme_before_design_layer_without_flash() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert '<meta name="color-scheme" content="light dark">' in html
    assert "obc.theme" in html
    assert "document.documentElement.dataset.theme" in html
    first_sheet = html.index('href="/shared/design/tokens.css"')
    assert html.index("obc.theme") < first_sheet
    assert "<script src=" not in html[:first_sheet]


def test_paper_choice_is_exposed_in_settings_and_applied_before_paint() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")

    assert 'id="themePaletteSetting" role="radiogroup"' in html
    assert html.count("data-palette-choice=") == 3
    for name in ("素白", "暖纸", "青苔"):
        assert name in html
    # the paper is read in the blocking boot script, not after the sheets load
    first_sheet = html.index('href="/shared/design/tokens.css"')
    assert "obc.palette" in html
    assert html.index("obc.palette") < first_sheet

    assert 'const PALETTE_STORAGE_KEY = "obc.palette";' in js
    assert 'const PALETTE_OPTIONS = ["plain", "paper", "moss"];' in js
    assert "document.documentElement.dataset.palette = state.palette;" in js
    # An unset hue must not pin a colour: the paper's own default has to win.
    assert 'root.style.removeProperty("--hue-primary")' in js
    assert 'safeBind("#themeHueReset", "click"' in js
    assert (
        'storageSet(THEME_HUE_STORAGE_KEY, state.themeHueExplicit ? String(state.themeHue) : "");'
        in js
    )


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
    assert "data-accent-choice" not in html
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
