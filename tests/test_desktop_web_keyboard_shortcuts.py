from pathlib import Path

from tests._design_css import read_desktop_css

APP_JS = Path("src/openbiliclaw/web/desktop/assets/js/app.js")
APP_CSS = read_desktop_css()
INDEX_HTML = Path("src/openbiliclaw/web/desktop/index.html")


def test_shortcuts_dialog_structure_in_index_html() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="shortcutsDialog"' in html
    assert 'class="drawer"' in html
    assert 'class="drawer-panel shortcuts-panel"' in html
    assert 'data-close="shortcutsDialog"' in html
    assert 'class="shortcuts-grid"' in html
    assert "<kbd>J</kbd>" in html
    assert "<kbd>K</kbd>" in html
    assert "<kbd>Enter</kbd>" in html
    assert "<kbd>S</kbd>" in html
    assert "<kbd>L</kbd>" in html
    assert "<kbd>X</kbd>" in html
    assert "<kbd>C</kbd>" in html
    assert "<kbd>?</kbd>" in html


def test_keyboard_navigation_helpers_in_app_js() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert "function getRecommendationCards()" in js
    assert "function clearCardFocus()" in js
    assert "function focusCardByIndex(" in js
    assert "function getFocusedCard()" in js
    assert "function openShortcutsModal()" in js
    assert "function handleGlobalKeydown(event)" in js
    assert "function initKeyboardNavigation()" in js
    assert 'document.addEventListener("keydown", handleGlobalKeydown);' in js


def test_keyboard_navigation_handles_essential_keys() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    # Typing guards against hijacking input/textarea
    assert "isTyping" in js
    assert 'target.tagName === "INPUT"' in js
    assert 'target.tagName === "TEXTAREA"' in js

    # Key mappings
    assert 'key === "j"' in js or "key === 'j'" in js
    assert 'key === "k"' in js or "key === 'k'" in js
    assert 'key === "Enter" || key === "o"' in js
    assert 'key === "s"' in js or "key === 's'" in js
    assert 'key === "l"' in js or "key === 'l'" in js
    assert 'key === "x"' in js or "key === 'x'" in js
    assert 'key === "c"' in js or "key === 'c'" in js
    assert 'key === "/"' in js or "key === '/'" in js
    assert 'key === "?"' in js or "key === '?'" in js
    assert 'key === "Escape"' in js or "key === 'Escape'" in js


def test_card_focus_css_is_present() -> None:
    assert ".video-card.is-focused" in APP_CSS
    assert "var(--stamp)" in APP_CSS
    assert "kbd" in APP_CSS
