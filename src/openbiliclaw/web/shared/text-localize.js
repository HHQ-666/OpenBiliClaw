/**
 * Display-time Chinese for the text a card quotes.
 *
 * The tray prints a source's own words — an X tweet body, an English title —
 * and for the non-Chinese sources that is exactly the text a Chinese reader
 * cannot read. This module asks `/api/translate-texts` once per distinct
 * string and swaps the Chinese into the DOM when it arrives; the backend keeps
 * the rendering in a persistent cache, so a card seen twice costs one call.
 *
 * Two rules shape the whole design:
 *
 *   1. **It never blocks the first paint.** Elements render the original text,
 *      the request goes out in the background, and only the two text nodes are
 *      rewritten. Nothing here can delay, replace, or unmount a card.
 *   2. **It never fails loudly.** A missing backend, an expired session, or an
 *      empty answer leaves the English on screen, which is exactly what the
 *      user saw before this module existed.
 *
 * The host surface supplies `request(path, options)` — the desktop page and the
 * mobile page each have their own cookie/bearer plumbing, and this module must
 * not carry a second copy of either.
 *
 * Loaded as a classic script by both surfaces; exposes
 * `globalThis.OpenBiliClawTextLocalize`.
 */
(function (global) {
  "use strict";

  const ENDPOINT = "/translate-texts";
  const BATCH_SIZE = 40;
  const DEBOUNCE_MS = 150;
  // How many times one element may be asked for. The backend spends a bounded
  // number of LLM calls per request and answers the rest as `pending`; one
  // retry picks those up, and a third would only spin against a backend that
  // is already behind. A re-rendered card is a fresh element and starts over.
  const MAX_ATTEMPTS = 2;
  // Mirrors MIN_TRANSLATABLE_CHARS / MAX_TRANSLATABLE_CHARS in
  // src/openbiliclaw/llm/translation.py. A rendering made from a longer source
  // is a partial one, and saying so is cheaper than letting a reader believe
  // the excerpt is the whole post.
  const MIN_TRANSLATABLE_CHARS = 8;
  const EXCERPT_LIMIT = 600;
  const PARTIAL_SUFFIX = "…（原文较长，此处为节译）";

  const CJK_RE = /[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
  const LATIN_RE = /[A-Za-z]/;
  // Links come back unchanged, so a text that is only a URL is not worth a call.
  const URL_RE = /(?:https?:\/\/|www\.)\S+/gi;

  // Every place a surface prints source-verbatim text: the tray card and its
  // cover excerpt, the delight card, the library and history cards, on both
  // the desktop and the phone.
  const TEXT_TARGETS = [
    ".video-title",
    ".cover-text",
    ".card-title",
    ".card-cover-text",
    ".delight-title",
    ".delight-thumb-text",
    "#delightTitle",
    "#delightExcerptText",
  ].join(", ");

  /** source text -> rendered Chinese, for this page's lifetime. */
  const memo = new Map();
  /** element -> attempts spent; dies with the DOM node it describes. */
  const attempts = new WeakMap();
  /** elements waiting for this flush cycle. */
  let queue = [];
  let timer = null;
  let inFlight = false;
  let requestFn = null;

  function collapse(text) {
    return String(text || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  /**
   * Whether a string is worth rendering. Mirrors the backend's rule so the
   * client does not open a batch for text the server would refuse to touch.
   */
  function needsTranslation(text) {
    const collapsed = collapse(text).replace(URL_RE, " ").trim();
    if (collapsed.length < MIN_TRANSLATABLE_CHARS) return false;
    if (CJK_RE.test(collapsed)) return false;
    return LATIN_RE.test(collapsed);
  }

  function paint(element, source, rendered) {
    const shown = collapse(source).length > EXCERPT_LIMIT ? rendered + PARTIAL_SUFFIX : rendered;
    element.textContent = shown;
    element.dataset.localizeApplied = "1";
    element.dataset.localizeSource = source;
    // The rendering is a reading aid: hovering keeps the source word one
    // gesture away, and an element with its own tooltip keeps it.
    if (!element.title) element.title = source;
  }

  function enqueue(element, source) {
    const spent = attempts.get(element) || 0;
    if (spent >= MAX_ATTEMPTS) return;
    attempts.set(element, spent + 1);
    queue.push({ element, source });
  }

  function schedule() {
    if (timer !== null) return;
    timer = global.setTimeout(() => {
      timer = null;
      void flush();
    }, DEBOUNCE_MS);
  }

  async function flush() {
    if (inFlight || !queue.length || typeof requestFn !== "function") return;
    const batch = queue.splice(0, BATCH_SIZE);
    const items = batch.map((entry, index) => ({
      id: String(index),
      text: collapse(entry.source),
    }));
    inFlight = true;
    let answered = {};
    let pendingIds = [];
    try {
      const response = await requestFn(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
        // The backend may spend two LLM batches on a cold cache; the page is
        // already readable while it waits.
        timeoutMs: 120000,
      });
      answered = response?.translations || {};
      pendingIds = Array.isArray(response?.pending) ? response.pending : [];
    } catch (error) {
      // Cosmetic path: the English stays, and the console keeps the reason.
      if (global.console?.debug) global.console.debug("card text translation failed", error);
    } finally {
      inFlight = false;
    }

    const retry = [];
    batch.forEach((entry, index) => {
      const rendered = collapse(answered[String(index)]);
      if (rendered) {
        memo.set(collapse(entry.source), rendered);
        paint(entry.element, entry.source, rendered);
        return;
      }
      // Not answered: `pending` means the server ran out of its per-request
      // budget (worth one more ask), anything else means the request failed as
      // a whole and the element keeps its original text.
      if (pendingIds.includes(String(index))) retry.push(entry);
    });

    retry.forEach((entry) => enqueue(entry.element, entry.source));
    if (queue.length) schedule();
  }

  /**
   * Localize every card text under *root* that is not already Chinese.
   *
   * Idempotent: an element that was localized (or decided not to be) is
   * marked and skipped, so calling this after every incremental re-render —
   * including the two-per-second pool refresh — does no repeated work.
   */
  function localizeWithin(root, options) {
    const request = options && options.request;
    if (typeof request === "function") requestFn = request;
    if (typeof requestFn !== "function") return;
    const scope = root || global.document;
    if (!scope || typeof scope.querySelectorAll !== "function") return;

    scope.querySelectorAll(TEXT_TARGETS).forEach((element) => {
      if (element.dataset.localizeApplied === "1") return;
      const source = element.textContent || "";
      if (!needsTranslation(source)) {
        element.dataset.localizeApplied = "1";
        return;
      }
      const cached = memo.get(collapse(source));
      if (cached) {
        paint(element, source, cached);
        return;
      }
      if (queue.some((entry) => entry.element === element)) return;
      enqueue(element, source);
    });
    if (queue.length) schedule();
  }

  /** Test seam: forget everything (memory only, never the backend cache). */
  function reset() {
    memo.clear();
    queue = [];
    if (timer !== null) {
      global.clearTimeout(timer);
      timer = null;
    }
    inFlight = false;
    requestFn = null;
  }

  const api = { needsTranslation, localizeWithin, reset };

  global.OpenBiliClawTextLocalize = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);