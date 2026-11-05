from pathlib import Path

from tests._design_css import read_desktop_css

APP_JS = Path("src/openbiliclaw/web/desktop/assets/js/app.js")
APP_CSS = read_desktop_css()
INDEX_HTML = Path("src/openbiliclaw/web/desktop/index.html")


def test_blocked_authors_section_in_index_html() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="blockedAuthorsList"' in html
    assert "黑名单管理（已屏蔽作者）" in html


def test_blocked_authors_styles_in_css() -> None:
    assert ".blocked-authors-list" in APP_CSS
    assert ".blocked-author-row" in APP_CSS
    assert ".blocked-author-info" in APP_CSS


def test_blocked_authors_logic_in_app_js() -> None:
    js = APP_JS.read_text(encoding="utf-8")

    assert "async function loadBlockedAuthors()" in js
    assert 'async function blockAuthor(authorName, sourcePlatform = "")' in js
    assert 'async function unblockAuthor(id, authorName = "")' in js
    assert "async function renderBlockedAuthorsList()" in js
    assert 'data-detail-action="block-author"' in js
