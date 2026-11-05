"""Read the web design layer for the frontend contract tests.

The redesign replaced the two per-surface stylesheets with one shared
design system under ``web/shared/design``. Contract tests assert that a
selector or declaration exists *somewhere* in a surface's print, so they
read the whole layer rather than a single file.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN_DIR = ROOT / "src" / "openbiliclaw" / "web" / "shared" / "design"

_CORE = ("tokens.css", "base.css", "world.css")
_DESKTOP_PAGES = (
    "desktop.css",
    "home.css",
    "library.css",
    "profile.css",
    "chat.css",
    "settings.css",
)
_MOBILE_PAGES = (
    "mobile.css",
    "home.css",
    "library.css",
    "profile.css",
    "chat.css",
    "settings.css",
)


def _read_all(names: tuple[str, ...], *, pages_subdir: bool) -> str:
    chunks: list[str] = []
    for name in names[:3]:
        path = DESIGN_DIR / name
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    for name in names[3:] if pages_subdir else ():
        path = DESIGN_DIR / "pages" / name
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def read_design_core() -> str:
    """tokens + base + world, without any surface page print."""
    return "\n".join(
        (DESIGN_DIR / name).read_text(encoding="utf-8")
        for name in _CORE
        if (DESIGN_DIR / name).is_file()
    )


def read_desktop_css() -> str:
    """Everything the desktop surface loads."""
    return _read_all(("tokens.css", "base.css", "world.css", *_DESKTOP_PAGES), pages_subdir=True)


def read_mobile_css() -> str:
    """Everything the mobile surface loads."""
    return _read_all(("tokens.css", "base.css", "world.css", *_MOBILE_PAGES), pages_subdir=True)


def read_all_design_css() -> str:
    """The whole layer: both surfaces, every page file."""
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(DESIGN_DIR.rglob("*.css")))
