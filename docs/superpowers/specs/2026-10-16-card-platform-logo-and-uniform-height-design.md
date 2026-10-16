# Design: Card Platform Brand Logos & Uniform Card Height

## Context & Objectives
In OpenBiliClaw desktop recommendation view, content cards from multiple platforms (Bilibili, GitHub, Linux.do, Zhihu, Douyin, Weibo, YouTube, Reddit, X/Twitter, Xiaohongshu, Bangumi) are presented together in a responsive grid.

Currently:
1. **Platform Badge is Text-Only**: The badge on top of card covers displays text labels like `B 站`, `GitHub`, `Linux.do`. Showing brand SVG logos instead of plain text significantly improves visual polish and immediate platform recognition.
2. **Card/Cover Heights are Inconsistent**:
   - Video cards (Bilibili, YouTube, Douyin) render covers with standard `aspect-ratio: 16 / 9`.
   - Text/coverless cards (GitHub repositories, Linux.do threads, text posts) had an override rule `.cover.is-text-card.is-coverless { aspect-ratio: auto; min-height: 96px; max-height: 124px; }`.
   - This caused a ~50px height discrepancy in the top cover area between video cards and text cards within the same grid row, causing titles and action bars to be visually misaligned.

## Detailed Design

### 1. Platform Brand Logos (Issue 1)
- **Component**: `.platform` badge positioned at `top: var(--space-2); right: var(--space-2);` on card covers.
- **Rendering**:
  - Replace text label with an SVG icon representing each platform:
    - `bilibili`: B站小电视 (Bilibili TV mascot)
    - `github`: GitHub Octocat mark
    - `linuxdo` / `linux.do`: Linux.do 官方/企鹅论坛徽标
    - `zhihu`: 知乎「知」标志
    - `douyin`: 抖音音乐符号
    - `xiaohongshu` / `xhs`: 小红书标志
    - `weibo`: 微博大眼睛标志
    - `youtube`: YouTube 播放按钮矩形
    - `twitter` / `x`: X 矢量标
    - `reddit`: Reddit 外星人 Snoo 标
    - `bangumi`: Bangumi 标志
    - Fallback: 通用网页/链接图标
  - The badge maintains platform brand theme colors:
    - Bilibili: `#fb7299`
    - GitHub: `#24292e`
    - Linux.do: `#f2a900` or `#1e1e1e`
    - Zhihu: `#0084ff`
    - Douyin: `#161823`
    - Xiaohongshu: `#ff2442`
    - Weibo: `#e6162d`
    - YouTube: `#ff0000`
    - Reddit: `#ff4500`
    - X (Twitter): `#000000`
    - Bangumi: `#f09199`
  - Badges have a circular or smooth squircle shape (`width: 26px; height: 26px; border-radius: var(--radius-pill); display: inline-flex; align-items: center; justify-content: center;`), drop shadow for contrast against covers, and tooltip `title="来自 <平台名>"`.

### 2. Uniform Card & Cover Height (Issue 2)
- **Unified 16:9 Cover Frame**:
  - Remove `.cover.is-text-card.is-coverless { aspect-ratio: auto; min-height: 96px; max-height: 124px; }`.
  - All `.cover` elements (whether video thumbnail, image backdrop, or pure text card) strictly maintain `aspect-ratio: 16 / 9; width: 100%;`.
  - Text cards (`.cover.is-text-card`) center their excerpt text with appropriate padding and line clamp (4 lines), providing a clean, consistent card header.
- **Card Flex Alignment**:
  - Update `.video-card` to use `display: flex; flex-direction: column;` (or grid template rows) so that:
    1. `.cover`: fixed 16:9 ratio, identical height across all cards in the row.
    2. `.video-card > div` (title, meta, stats): consistent structure.
    3. `.reason`: flexible growth (`flex: 1 1 auto;`) so differences in title lines don't push the bottom bar out of alignment.
    4. `.card-actions`: pinned to the bottom (`margin-top: auto;`).
  - Result: In any grid row, cover bottoms, title baselines, and bottom action bars align evenly.

### 3. Verification & Testing
- Automated checks:
  - Verify desktop CSS rules for `.cover.is-text-card` and `.platform`.
  - Verify `platformSvgIcon` mapping in `app.js` and desktop HTML output.
  - Run existing test suites (`pytest tests/test_desktop_web_*.py`, `ruff check`, `mypy`).
- Visual check:
  - Inspect rendered HTML structure and verify layout across multiple card types.
