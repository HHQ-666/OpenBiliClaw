# Card Platform Brand Logos & Uniform Card Height Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text-only platform badges on recommendation cards with crisp brand SVG logos and unify all card covers to an identical 16:9 aspect ratio and aligned flex layout.

**Architecture:**
1. In `src/openbiliclaw/web/desktop/assets/js/app.js`, define an inline SVG icon map `PLATFORM_BRAND_ICONS` for all platforms (`bilibili`, `github`, `linuxdo`, `zhihu`, `douyin`, `xiaohongshu`, `weibo`, `youtube`, `twitter`/`x`, `reddit`, `bangumi`, and fallback).
2. Render the logo inside `.platform` with `title` and `aria-label` attributes while preserving `data-platform`.
3. In `src/openbiliclaw/web/desktop/assets/css/app.css`, make `.platform` a compact badge (26x26px, flex center), add colors for `github` and `linuxdo`, remove the reduced height rule on `.cover.is-text-card.is-coverless` so all cards enforce standard `16:9` ratio, and configure `.video-card` flex column alignment so titles, reasons, and actions align across cards in a row.
4. Add automated unit tests in `tests/test_desktop_web_card_logos_and_uniform_height.py`.

**Tech Stack:** Vanilla JavaScript (ES modules), CSS3 (Flexbox/Grid/Aspect-ratio), Python (pytest).

---

### Task 1: Add brand SVG icons and update card markup in app.js

**Files:**
- Modify: `src/openbiliclaw/web/desktop/assets/js/app.js`

- [ ] **Step 1: Define `PLATFORM_BRAND_ICONS` map and helper function `platformLogoSvg(platform)`**
- [ ] **Step 2: Update recommendation card HTML generation in `createRecommendationCard` / `recommendationMediaHtml`**
- [ ] **Step 3: Update saved card HTML generation in `renderSavedCards`**
- [ ] **Step 4: Verify syntax and build checks**

---

### Task 2: Update CSS styling in app.css

**Files:**
- Modify: `src/openbiliclaw/web/desktop/assets/css/app.css`

- [ ] **Step 1: Update `.platform` styling to circular/squircle icon badge**
- [ ] **Step 2: Add platform badge colors for `github`, `linuxdo`, and ensure `weibo`, `bilibili`, etc. are preserved**
- [ ] **Step 3: Unify `.cover` and `.cover.is-text-card` to strict 16:9 aspect ratio with centered text**
- [ ] **Step 4: Configure `.video-card` flex column layout for row-aligned action bars**

---

### Task 3: Add automated tests and verify all test suites

**Files:**
- Create: `tests/test_desktop_web_card_logos_and_uniform_height.py`

- [ ] **Step 1: Write test asserting platform SVG icons and 16:9 uniform height CSS**
- [ ] **Step 2: Run pytest on the new and existing desktop web tests**
- [ ] **Step 3: Run ruff check and formatting**

---

### Task 4: Documentation & commit

**Files:**
- Modify: `docs/changelog.md`

- [ ] **Step 1: Update changelog with the visual enhancements**
- [ ] **Step 2: Commit all changes in the worktree**
