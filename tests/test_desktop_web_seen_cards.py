from pathlib import Path

from tests._design_css import read_desktop_css

APP_JS = Path("src/openbiliclaw/web/desktop/assets/js/app.js")
APP_CSS = read_desktop_css()


def test_seen_cards_storage_helpers_defined() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert 'SEEN_CARDS_STORAGE_KEY = "openbiliclaw.webui.seenCards"' in js
    assert "function loadSeenCards()" in js
    assert "function saveSeenCards()" in js
    assert "function recommendationSeenKey(item)" in js
    assert "function isRecommendationSeen(item)" in js
    assert "function markRecommendationSeen(item, card = null)" in js


def test_card_instantiation_applies_is_seen() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert "if (isRecommendationSeen(item)) {" in js
    assert 'card.classList.add("is-seen");' in js


def test_open_recommendation_marks_card_as_seen() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert "markRecommendationSeen(item, card);" in js


def test_punched_hole_and_seen_dimming_in_css() -> None:
    assert ".video-card.is-seen::after" in APP_CSS
    assert ".video-card.is-seen .cover img" in APP_CSS
    assert "opacity: 0.88;" in APP_CSS
