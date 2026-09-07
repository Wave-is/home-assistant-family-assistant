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

const {
  renderConversation,
  reconcileConversationRefresh,
  disposeConversation,
  _test,
} = await import(
  "../custom_components/family_assistant/frontend/conversation-view.js"
);
const { CONVERSATION_COPY } = await import(
  "../custom_components/family_assistant/frontend/conversation-copy.js"
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

function data(role = "parent", configured = true) {
  return {
    revision: 1,
    actor: role,
    role,
    settings: { modules: ["conversation"] },
    members: clone(members),
    conversation_source: {
      enabled: true,
      configured,
      allowed: role !== "guest",
      revision: role === "guest" ? null : "a".repeat(32),
    },
    learned_phrases: [
      {
        id: "L000001",
        source: "<img src=x onerror=alert(1)>",
        canonical: "/stats",
        active: true,
        revision: 1,
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
    this._conversationDraft = null;
    this.calls = [];
    this.commands = [];
    this.refreshes = 0;
    this.handler = async () => ({ reply: "A private reply." });
    this._hass = {
      language,
      user: { id: "ha-user" },
      callWS: async (message) => {
        this.calls.push(clone(message));
        return await this.handler(message);
      },
    };
  }

  async refresh() {
    this.refreshes += 1;
  }

  command(action, payload) {
    this.commands.push({ action, payload: clone(payload) });
  }

  render() {
    const body = document.createElement("div");
    body.className = "body";
    this.shadowRoot.replaceChildren(body);
    renderConversation(this, body);
  }
}

customElements.define("test-conversation-card", Card);

function setup(t, options = {}) {
  const card = new Card(data(options.role, options.configured), options.language);
  document.body.append(card);
  card.render();
  t.after(() => card.remove());
  return card;
}

function chatForm(card) {
  return card.shadowRoot.querySelector('[data-conversation-form="chat"]');
}

function button(card, label) {
  return [...card.shadowRoot.querySelectorAll("button")].find(
    (item) => item.textContent === label,
  );
}

function submit(card, text) {
  const form = chatForm(card);
  const input = form.querySelector('input[name="message"]');
  if (!input.disabled) {
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}

test("EN RU UK copy has exact key parity", () => {
  const keys = Object.keys(CONVERSATION_COPY.en).sort();
  assert.deepEqual(Object.keys(CONVERSATION_COPY.ru).sort(), keys);
  assert.deepEqual(Object.keys(CONVERSATION_COPY.uk).sort(), keys);
});

test("source projection is exact and model configuration is optional", (t) => {
  const card = setup(t, { configured: false });
  assert.ok(_test.accessOf(card));
  assert.match(card.shadowRoot.textContent, /Built-in commands remain available/);
  for (const invalid of [
    { ...card._data.conversation_source, extra: true },
    { ...card._data.conversation_source, revision: "short" },
    { ...card._data.conversation_source, allowed: false },
  ]) {
    card._data.conversation_source = invalid;
    assert.equal(_test.accessOf(card), null);
  }
});

test("chat sends the exact frozen current-scope request and renders text inertly", async (t) => {
  const card = setup(t, { language: "ru" });
  card.handler = async () => ({ reply: "<img src=x onerror=alert(1)> ответ" });
  submit(card, "  /ping  ");
  await tick();
  assert.equal(card.calls.length, 1);
  assert.deepEqual(card.calls[0], {
    type: "family_assistant/chat",
    entry_id: "entry-one",
    text: "/ping",
    operation_id: card.calls[0].operation_id,
    session_id: card.calls[0].session_id,
    actor_revision: 3,
    source_revision: "a".repeat(32),
  });
  assert.equal(typeof card.calls[0].operation_id, "string");
  assert.equal(typeof card.calls[0].session_id, "string");
  assert.match(card.shadowRoot.querySelector(".conversation-reply").textContent, /<img/);
  assert.equal(card.shadowRoot.querySelector("img"), null);
  assert.equal(card._conversationDraft.text, "");
  assert.equal(card._conversationDraft.pending, null);
});

test("response loss keeps exact operation, content, session, and source for retry", async (t) => {
  const card = setup(t);
  let attempts = 0;
  card.handler = async () => {
    attempts += 1;
    if (attempts === 1)
      throw Object.assign(new Error("lost"), { code: "provider_timeout" });
    return { reply: "Recovered reply" };
  };
  submit(card, "first request");
  await tick();
  const frozen = clone(card._conversationDraft.pending);
  assert.equal(chatForm(card).querySelector("button").textContent, CONVERSATION_COPY.en.retry);
  submit(card, "ignored replacement");
  await tick();
  assert.deepEqual(card.calls, [frozen, frozen]);
  assert.equal(card.shadowRoot.querySelector(".conversation-reply").textContent, "Recovered reply");
});

test("an explicit warned start-over abandons provider failure or uncertain retry without sending", async (t) => {
  for (const code of ["provider_not_configured", "provider_timeout"]) {
    const card = setup(t);
    card.handler = async () => {
      throw Object.assign(new Error(code), { code });
    };
    submit(card, `request for ${code}`);
    await tick();
    const pending = clone(card._conversationDraft.pending);
    const session = card._conversationDraft.sessionId;
    assert.match(card.shadowRoot.textContent, /may have succeeded/);
    button(card, CONVERSATION_COPY.en.start_new).click();
    assert.equal(card.calls.length, 1, "starting over never calls the backend");
    assert.equal(card._conversationDraft.pending, null);
    assert.equal(card._conversationDraft.reply, null);
    assert.equal(card._conversationDraft.text, "");
    assert.equal(card._conversationDraft.sessionId, session);
    assert.equal(chatForm(card).querySelector('input[name="message"]').disabled, false);
    card.handler = async () => ({ reply: "new request reply" });
    submit(card, "new request");
    await tick();
    assert.notEqual(card.calls[1].operation_id, pending.operation_id);
    assert.equal(card.calls[1].session_id, session);
    card.remove();
  }
});

test("a new confirmed submit clears the prior reply before awaiting", async (t) => {
  const card = setup(t);
  submit(card, "first");
  await tick();
  assert.ok(card.shadowRoot.querySelector(".conversation-reply"));
  let release;
  card.handler = () => new Promise((resolve) => (release = resolve));
  submit(card, "second");
  await tick();
  assert.equal(card.shadowRoot.querySelector(".conversation-reply"), null);
  release({ reply: "second reply" });
  await tick();
});

test("pending completion settles across harmless rerender", async (t) => {
  const card = setup(t);
  let release;
  card.handler = () => new Promise((resolve) => (release = resolve));
  submit(card, "wait for me");
  await tick();
  const draft = card._conversationDraft;
  card.render();
  assert.equal(card._conversationDraft, draft);
  release({ reply: "settled after refresh" });
  await tick();
  assert.equal(card.shadowRoot.querySelector(".conversation-reply").textContent, "settled after refresh");
  assert.equal(card._conversationDraft.loading, false);
});

test("revocation discards delayed content and old finally cannot unlock a newer request", async (t) => {
  const card = setup(t);
  const releases = [];
  card.handler = () => new Promise((resolve) => releases.push(resolve));
  submit(card, "old request");
  await tick();
  const previous = clone(card._data);
  card._data.conversation_source.revision = "b".repeat(32);
  assert.equal(reconcileConversationRefresh(card, previous), true);
  card.render();
  submit(card, "new request");
  await tick();
  const newer = card._conversationDraft;
  releases[0]({ reply: "stale private reply" });
  await tick();
  assert.equal(card._conversationDraft, newer);
  assert.equal(newer.loading, true);
  assert.equal(card.shadowRoot.textContent.includes("stale private reply"), false);
  releases[1]({ reply: "current reply" });
  await tick();
  assert.equal(card.shadowRoot.querySelector(".conversation-reply").textContent, "current reply");
});

test("all identity and module changes clear draft and make detached controls inert", (t) => {
  const changes = [
    [
      (card) =>
        (card._data.members.find((item) => item.id === "parent").revision += 1),
      true,
    ],
    [(card) => (card._data.role = "adult"), false],
    [(card) => (card._data.settings.modules = []), false],
    [(card) => (card._entry = "other"), true],
    [(card) => (card._generation += 1), true],
    [(card) => (card._hass.user.id = "other-user"), true],
  ];
  for (const [change, remainsAuthorized] of changes) {
    const card = setup(t);
    card._conversationDraft.text = "private stale draft";
    const oldDraft = card._conversationDraft;
    const oldForm = chatForm(card);
    const previous = clone(card._data);
    change(card);
    reconcileConversationRefresh(card, previous);
    oldForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    assert.equal(card.calls.length, 0);
    assert.notEqual(card._conversationDraft, oldDraft);
    assert.equal(Boolean(card._conversationDraft), remainsAuthorized);
    assert.equal(card.shadowRoot.textContent.includes("private stale draft"), false);
    card.remove();
  }
});

test("dispose clears owned request state and a detached completion stays discarded", async (t) => {
  const card = setup(t);
  let release;
  card.handler = () => new Promise((resolve) => (release = resolve));
  submit(card, "private pending reply");
  await tick();
  disposeConversation(card);
  card.remove();
  release({ reply: "must not survive reconnect" });
  await tick();
  assert.equal(card._conversationDraft, null);
});

test("learn and forget preserve existing command payloads with safe text rendering", (t) => {
  const card = setup(t, { language: "uk" });
  assert.equal(card.shadowRoot.querySelector("img"), null);
  const details = card.shadowRoot.querySelector(".conversation-learning");
  details.open = true;
  const learn = details.querySelector('[data-conversation-form="learn"]');
  learn.querySelector('[name="source"]').value = "покажи баланс";
  learn.querySelector('[name="canonical"]').value = "/stats";
  learn.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  assert.deepEqual(card.commands[0], {
    action: "conversation.learn",
    payload: { source: "покажи баланс", canonical: "/stats" },
  });
  [...details.querySelectorAll("button")]
    .find((item) => item.textContent === CONVERSATION_COPY.uk.forget)
    .click();
  assert.deepEqual(card.commands[1], {
    action: "conversation.forget",
    payload: { id: "L000001" },
  });
});

test("malformed replies retain the exact retry and never render content", async (t) => {
  for (const response of [
    { reply: "ok", extra: true },
    { reply: "" },
    { reply: 12 },
  ]) {
    const card = setup(t);
    card.handler = async () => response;
    submit(card, "hello");
    await tick();
    assert.equal(card.shadowRoot.querySelector(".conversation-reply"), null);
    assert.equal(card._actionError, "provider_bad_response");
    assert.ok(card._conversationDraft.pending);
    card.remove();
  }
});
