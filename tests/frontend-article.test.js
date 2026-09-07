import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {
  url: "https://example.invalid",
});
for (const key of [
  "window",
  "document",
  "HTMLElement",
  "customElements",
  "Event",
  "FormData",
])
  globalThis[key] = dom.window[key];

const { renderArticle, reconcileArticleRefresh, disposeArticle, _test } = await import(
  "../custom_components/family_assistant/frontend/article-view.js"
);
const { ARTICLE_COPY } = await import(
  "../custom_components/family_assistant/frontend/article-copy.js"
);

const clone = (value) => structuredClone(value);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

const members = [
  { id: "owner", role: "owner", active: true, revision: 2, name: "Owner" },
  { id: "parent", role: "parent", active: true, revision: 3, name: "Parent" },
  { id: "adult", role: "adult", active: true, revision: 4, name: "Adult" },
  { id: "child", role: "child", active: true, revision: 5, name: "Child" },
  { id: "guest", role: "guest", active: true, revision: 6, name: "Guest" },
];

function data(role = "parent") {
  return {
    revision: 1,
    actor: role,
    role,
    settings: { modules: ["conversation"] },
    members: clone(members),
    article_source: {
      enabled: true,
      configured: true,
      allowed: role !== "guest",
      revision: role === "guest" ? null : "a".repeat(32),
    },
  };
}

function validResponse(url = "https://example.org/article") {
  return {
    answer: "A factual summary.",
    sources: [
      {
        title: "Verified title",
        url: "https://example.org/final",
        requested_url: url,
        retrieved_at: "2026-09-07T12:00:00+00:00",
      },
    ],
  };
}

class Card extends HTMLElement {
  constructor(value = data(), language = "en") {
    super();
    this.attachShadow({ mode: "open" });
    this._data = value;
    this._config = { language };
    this._entry = "entry-one";
    this._generation = 1;
    this._writing = false;
    this._actionError = null;
    this._articleDraft = null;
    this.calls = [];
    this.handler = async (message) => validResponse(message.url);
    this._hass = {
      language,
      user: { id: "ha-user" },
      callWS: async (message) => {
        this.calls.push(clone(message));
        return await this.handler(message);
      },
    };
  }

  button(label, action, primary = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    if (primary) button.className = "primary";
    button.addEventListener("click", action);
    return button;
  }

  render() {
    const body = document.createElement("div");
    body.className = "body";
    this.shadowRoot.replaceChildren(body);
    renderArticle(this, body);
  }
}

customElements.define("test-article-card", Card);

function setup(t, options = {}) {
  const card = new Card(data(options.role), options.language);
  document.body.append(card);
  card.render();
  t.after(() => card.remove());
  return card;
}

function button(card, label) {
  return [...card.shadowRoot.querySelectorAll("button")].find(
    (item) => item.textContent === label,
  );
}

function openReview(card, url = "https://example.org/article") {
  const copy = ARTICLE_COPY[card._config.language];
  button(card, copy.open).click();
  const input = card.shadowRoot.querySelector('input[name="url"]');
  input.value = url;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  card.shadowRoot
    .querySelector('[data-article-form="edit"]')
    .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  return card.shadowRoot.querySelector('[data-article-form="review"]');
}

function confirmAndSubmit(card) {
  const form = card.shadowRoot.querySelector('[data-article-form="review"]');
  const checkbox = form.querySelector('input[name="confirmed"]');
  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}

test("EN RU UK copy has exact key parity", () => {
  const expected = Object.keys(ARTICLE_COPY.en).sort();
  assert.deepEqual(Object.keys(ARTICLE_COPY.ru).sort(), expected);
  assert.deepEqual(Object.keys(ARTICLE_COPY.uk).sort(), expected);
});

test("explicit editor and named review freeze canonical request with disclosure", async (t) => {
  const card = setup(t, { language: "ru" });
  const review = openReview(card, "https://example.org/article");
  assert.ok(review.textContent.includes(ARTICLE_COPY.ru.review_title));
  assert.ok(review.textContent.includes("IP-адрес"));
  assert.ok(review.textContent.includes("https://example.org/article"));
  review.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await tick();
  assert.equal(card.calls.length, 0, "unchecked review cannot fetch");
  confirmAndSubmit(card);
  await tick();
  assert.equal(card.calls.length, 1);
  assert.deepEqual(card.calls[0], {
    type: "family_assistant/article",
    entry_id: "entry-one",
    url: "https://example.org/article",
    operation_id: card.calls[0].operation_id,
    source_revision: "a".repeat(32),
  });
  assert.equal(typeof card.calls[0].operation_id, "string");
  assert.equal(card.shadowRoot.querySelector(".article-answer").textContent, "A factual summary.");
});

test("verified source is inert text plus hardened HTTPS link and result is transient", async (t) => {
  const card = setup(t);
  card.handler = async () => ({
    answer: "<img src=x onerror=alert(1)> factual text",
    sources: [
      {
        title: "<script>not markup</script>",
        url: "https://example.org/final",
        requested_url: "https://example.org/article",
        retrieved_at: "2026-09-07T12:00:00Z",
      },
    ],
  });
  openReview(card);
  confirmAndSubmit(card);
  await tick();
  assert.equal(card.shadowRoot.querySelector("img"), null);
  assert.equal(card.shadowRoot.querySelector("script:not([type])"), null);
  const link = card.shadowRoot.querySelector(".article-source a");
  assert.equal(link.textContent, "<script>not markup</script>");
  assert.equal(link.href, "https://example.org/final");
  assert.equal(link.target, "_blank");
  assert.equal(link.rel, "noopener noreferrer");
  assert.equal(card._data.article_result, undefined);
  button(card, ARTICLE_COPY.en.close).click();
  assert.equal(card._articleDraft, null);
  assert.equal(card.shadowRoot.querySelector(".article-result"), null);
});

test("lost response retains exact frozen URL operation and source generation", async (t) => {
  const card = setup(t);
  let attempts = 0;
  card.handler = async (message) => {
    attempts += 1;
    if (attempts === 1) throw Object.assign(new Error("lost"), { code: "article_unavailable" });
    return validResponse(message.url);
  };
  openReview(card);
  confirmAndSubmit(card);
  await tick();
  const frozen = clone(card._articleDraft.pending);
  assert.equal(button(card, ARTICLE_COPY.en.retry).textContent, ARTICLE_COPY.en.retry);
  button(card, ARTICLE_COPY.en.retry).click();
  await tick();
  assert.deepEqual(card.calls, [frozen, frozen]);
  assert.equal(card.shadowRoot.querySelector(".article-answer").textContent, "A factual summary.");
});

test("malformed model links or unverified citation fields never render", async (t) => {
  for (const response of [
    { ...validResponse(), answer: "Invented https://bad.invalid" },
    { ...validResponse(), answer: "Invented bad.invalid" },
    { ...validResponse(), sources: [{ ...validResponse().sources[0], extra: "bad" }] },
    { ...validResponse(), sources: [{ ...validResponse().sources[0], requested_url: "https://other.example/path" }] },
  ]) {
    const card = setup(t);
    card.handler = async () => response;
    openReview(card);
    confirmAndSubmit(card);
    await tick();
    assert.equal(card.shadowRoot.querySelector(".article-result"), null);
    assert.equal(card._actionError, "provider_bad_response");
    assert.ok(card._articleDraft.pending, "exact retry remains available");
    card.remove();
  }
});

test("unchanged refresh preserves typed URL but authority changes clear private state", (t) => {
  const changes = [
    (card) => (card._data.members.find((item) => item.id === "parent").revision += 1),
    (card) => (card._data.members.find((item) => item.id === "parent").role = "adult"),
    (card) => (card._data.settings.modules = []),
    (card) => (card._data.article_source.revision = "b".repeat(32)),
    (card) => (card._entry = "other"),
    (card) => (card._generation += 1),
    (card) => (card._hass.user.id = "other-user"),
  ];
  for (const change of changes) {
    const card = setup(t);
    button(card, ARTICLE_COPY.en.open).click();
    const input = card.shadowRoot.querySelector('input[name="url"]');
    input.value = "https://typed.example/path";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    const previous = clone(card._data);
    assert.equal(reconcileArticleRefresh(card, previous), false);
    card.render();
    assert.equal(card.shadowRoot.querySelector('input[name="url"]').value, "https://typed.example/path");
    const oldReview = button(card, ARTICLE_COPY.en.review);
    change(card);
    reconcileArticleRefresh(card, previous);
    oldReview.click();
    assert.equal(card._articleDraft, null);
    assert.equal(card.calls.length, 0);
    card.remove();
  }
});

test("delayed response is discarded after source or actor revocation", async (t) => {
  const card = setup(t);
  let release;
  card.handler = () => new Promise((resolve) => (release = resolve));
  openReview(card);
  confirmAndSubmit(card);
  await tick();
  const previous = clone(card._data);
  card._data.article_source = {
    enabled: true,
    configured: true,
    allowed: false,
    revision: null,
  };
  assert.equal(reconcileArticleRefresh(card, previous), true);
  card.render();
  release(validResponse());
  await tick();
  assert.equal(card._articleDraft, null);
  assert.equal(card.shadowRoot.querySelector(".article-result"), null);
  assert.equal(card.shadowRoot.textContent.includes("A factual summary"), false);
});

test("pending work settles after harmless rerender and disposal clears disconnected state", async (t) => {
  const card = setup(t);
  let release;
  card.handler = () => new Promise((resolve) => (release = resolve));
  openReview(card);
  confirmAndSubmit(card);
  await tick();
  const draft = card._articleDraft;
  card.render();
  assert.equal(card._articleDraft, draft);
  release(validResponse());
  await tick();
  assert.equal(card.shadowRoot.querySelector(".article-answer").textContent, "A factual summary.");

  button(card, ARTICLE_COPY.en.close).click();
  openReview(card);
  disposeArticle(card);
  assert.equal(card._articleDraft, null);
});

test("disabled unconfigured unauthorized guest and malformed projections expose no form", (t) => {
  const values = [
    { enabled: false, configured: true, allowed: false, revision: null },
    { enabled: true, configured: false, allowed: false, revision: null },
    { enabled: true, configured: true, allowed: false, revision: null },
    { enabled: true, configured: true, allowed: false, revision: "leak" },
  ];
  for (const source of values) {
    const card = setup(t, { role: "guest" });
    card._data.article_source = source;
    card.render();
    assert.equal(card.shadowRoot.querySelector("form"), null);
    assert.equal(button(card, ARTICLE_COPY.en.open), undefined);
    card.remove();
  }
});

test("pure validators reject credentials fragments non-HTTPS and preserve inputs", () => {
  for (const value of [
    "http://example.org",
    "https://user:pass@example.org",
    "https://example.org/#fragment",
    "https://example.org:444/path",
    "not a url",
  ])
    assert.throws(() => _test.normalizeUrl(value), /article_invalid_url/);
  const raw = validResponse();
  const before = clone(raw);
  const result = _test.validateResponse(raw, { url: "https://example.org/article" });
  assert.deepEqual(raw, before);
  assert.ok(Object.isFrozen(result) && Object.isFrozen(result.sources[0]));
});
