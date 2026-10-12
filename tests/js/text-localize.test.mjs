/**
 * tests for shared/text-localize.js — display-time Chinese for card text.
 *
 * The module is a classic script by design (three surfaces load it with a
 * <script> tag), so it is loaded here into a vm context with a hand-rolled
 * stand-in for the few DOM APIs it touches.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync("src/openbiliclaw/web/shared/text-localize.js", "utf8");

function load() {
  const context = vm.createContext({ console, setTimeout, clearTimeout });
  context.window = context;
  vm.runInContext(source, context);
  return context.OpenBiliClawTextLocalize;
}

function element(text) {
  return { textContent: text, dataset: {}, title: "" };
}

function scopeOf(elements) {
  return { querySelectorAll: () => elements };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 250));

test("needsTranslation mirrors the backend rule", () => {
  const api = load();
  assert.equal(api.needsTranslation("PostgreSQL connection pool tuning notes"), true);
  assert.equal(api.needsTranslation("this is pure f*cking insane"), true);
  assert.equal(api.needsTranslation("RAG 是什么"), false);
  assert.equal(api.needsTranslation("这条推文在聊 RAG 检索"), false);
  assert.equal(api.needsTranslation("v2.0"), false);
  assert.equal(api.needsTranslation("https://x.com/foo/status/123"), false);
  assert.equal(api.needsTranslation("🎉🎉"), false);
});

test("an English card text is rendered in place and marked done", async () => {
  const api = load();
  const node = element("PostgreSQL connection pool tuning notes");
  const requested = [];
  const request = async (path, options) => {
    const payload = JSON.parse(options.body);
    requested.push(...payload.items);
    return { translations: { "0": "PostgreSQL 连接池调优笔记" }, pending: [] };
  };
  api.localizeWithin(scopeOf([node]), { request });
  assert.equal(node.textContent, "PostgreSQL connection pool tuning notes");
  await settle();
  assert.equal(node.textContent, "PostgreSQL 连接池调优笔记");
  assert.equal(node.dataset.localizeApplied, "1");
  assert.equal(node.dataset.localizeSource, "PostgreSQL connection pool tuning notes");
  // The original stays one hover away.
  assert.equal(node.title, "PostgreSQL connection pool tuning notes");
  assert.equal(requested.length, 1);
  assert.equal(requested[0].text, "PostgreSQL connection pool tuning notes");
});

test("Chinese and fragment cards never open a request", async () => {
  const api = load();
  const nodes = [element("这条已经是中文了"), element("v2.0"), element("🎉")];
  let calls = 0;
  api.localizeWithin(scopeOf(nodes), { request: async () => { calls += 1; return { translations: {} }; } });
  await settle();
  assert.equal(calls, 0);
  assert.equal(nodes[0].textContent, "这条已经是中文了");
});

test("a second scan of the same tree does no further work", async () => {
  const api = load();
  const node = element("I thought PostgreSQL's connection pool was the bottleneck.");
  let calls = 0;
  const request = async () => ({ translations: { "0": "我以为连接池是瓶颈。" }, pending: [] });
  api.localizeWithin(scopeOf([node]), { request: async (...args) => { calls += 1; return request(...args); } });
  await settle();
  for (let i = 0; i < 3; i += 1) api.localizeWithin(scopeOf([node]), { request });
  await settle();
  assert.equal(calls, 1);
  assert.equal(node.textContent, "我以为连接池是瓶颈。");
});

test("a second element with the same text is painted from the memo, free", async () => {
  const api = load();
  const first = element("shared english sentence for memo");
  const second = element("shared english sentence for memo");
  let calls = 0;
  const request = async () => {
    calls += 1;
    return { translations: { "0": "用于记忆的共用英文句子" }, pending: [] };
  };
  api.localizeWithin(scopeOf([first]), { request });
  await settle();
  const callsAfterFirst = calls;
  api.localizeWithin(scopeOf([second]), { request });
  await settle();
  assert.equal(first.textContent, "用于记忆的共用英文句子");
  assert.equal(second.textContent, "用于记忆的共用英文句子");
  assert.equal(calls, callsAfterFirst);
});

test("pending ids are retried once and then left alone", async () => {
  const api = load();
  const node = element("english card text waiting for budget");
  let calls = 0;
  const request = async (path, options) => {
    calls += 1;
    const ids = JSON.parse(options.body).items.map((item) => item.id);
    return { translations: {}, pending: ids };
  };
  for (let i = 0; i < 5; i += 1) {
    api.localizeWithin(scopeOf([node]), { request });
    await settle();
  }
  assert.equal(calls, 2);
  assert.equal(node.textContent, "english card text waiting for budget");
  assert.equal(node.dataset.localizeApplied, undefined);
});

test("a failing request leaves the original text in place", async () => {
  const api = load();
  const node = element("an english sentence that fails");
  api.localizeWithin(scopeOf([node]), {
    request: async () => {
      throw new Error("network down");
    },
  });
  await settle();
  assert.equal(node.textContent, "an english sentence that fails");
  assert.equal(node.dataset.localizeApplied, undefined);
});

test("a rendering made from a truncated source says so", async () => {
  const api = load();
  const long = "word ".repeat(400).trim();
  const node = element(long);
  api.localizeWithin(scopeOf([node]), {
    request: async () => ({ translations: { "0": "这是一段很长的节选。" }, pending: [] }),
  });
  await settle();
  assert.equal(node.textContent, "这是一段很长的节选。…（原文较长，此处为节译）");
});

test("without a request function nothing is touched", async () => {
  const api = load();
  const node = element("english text with no host request");
  api.localizeWithin(scopeOf([node]));
  await settle();
  assert.equal(node.textContent, "english text with no host request");
});