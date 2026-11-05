from pathlib import Path

from tests._design_css import read_desktop_css

APP_JS = Path("src/openbiliclaw/web/desktop/assets/js/app.js")
APP_CSS = read_desktop_css()
INDEX_HTML = Path("src/openbiliclaw/web/desktop/index.html")


def test_card_detail_drawer_in_index_html() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="cardDetailDrawer"' in html
    assert 'class="drawer"' in html
    assert 'id="cardDetailPanel"' in html
    assert 'id="cardDetailPlatform"' in html
    assert 'id="cardDetailDrawerTitle"' in html
    assert 'id="cardDetailContent"' in html
    assert 'data-close="cardDetailDrawer"' in html


def test_card_detail_drawer_logic_in_app_js() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert "function openCardDetail(item, card = null)" in js
    assert 'openPanel("cardDetailDrawer");' in js
    assert "openCardDetail(item, card)" in js
    assert "card-detail-chat-form" in js
    assert "card-detail-summary" in js
    assert "card-detail-actions-row" in js


def test_card_detail_drawer_styles_in_css() -> None:
    assert "#cardDetailPanel" in APP_CSS
    assert ".card-detail-cover" in APP_CSS
    assert ".card-detail-title" in APP_CSS
    assert ".card-detail-summary" in APP_CSS
    assert ".card-detail-chat-input" in APP_CSS
