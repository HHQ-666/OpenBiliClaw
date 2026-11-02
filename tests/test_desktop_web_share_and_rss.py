from pathlib import Path

from tests._design_css import read_desktop_css

APP_JS = Path("src/openbiliclaw/web/desktop/assets/js/app.js")
APP_CSS = read_desktop_css()
INDEX_HTML = Path("src/openbiliclaw/web/desktop/index.html")


def test_rss_box_in_index_html() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="rssFeedUrlInput"' in html
    assert 'id="copyRssFeedBtn"' in html
    assert 'id="searchResultsBanner"' in html
    assert 'id="clearSearchResultsBtn"' in html


def test_share_and_search_logic_in_app_js() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert "function generateShareCard(item)" in js
    assert 'data-detail-action="share-card"' in js
    assert "async function executeGlobalSearch(query)" in js
    assert "function clearGlobalSearch()" in js
    assert 'safeBind("#copyRssFeedBtn"' in js
    assert 'safeBind("#clearSearchResultsBtn"' in js


def test_search_and_rss_styles_in_css() -> None:
    assert ".search-results-banner" in APP_CSS
    assert ".rss-feed-box" in APP_CSS
