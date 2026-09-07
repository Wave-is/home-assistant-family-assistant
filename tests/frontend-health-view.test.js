import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "https://example.invalid" });
for (const key of [
  "window",
  "document",
  "Element",
  "HTMLElement",
  "customElements",
  "CustomEvent",
  "Event",
  "FormData",
]) {
  globalThis[key] = dom.window[key];
}

await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { HEALTH_COPY, countHealthAttention, reconcileHealthRefresh, renderHealth } =
  await import("../custom_components/family_assistant/frontend/health-view.js");

const CANARY = "PRIVATE_HEALTH_CANARY";

function data(role = "owner") {
  return {
    revision: 1,
    actor: role === "parent" ? "parent" : role,
    role,
    settings: { name: "Family", modules: [], timezone: "Europe/Kyiv" },
    members: [
      { id: "owner", name: "Owner", role: "owner", active: true, revision: 3 },
      { id: "parent", name: "Parent", role: "parent", active: true, revision: 4 },
      { id: "child", name: CANARY, role: "child", active: true, revision: 5 },
    ],
    health: {
      digests: "digest_retention_attention",
      scheduler: "scheduler_failed",
      [CANARY]: CANARY,
    },
    delivery_issues: [
      {
        id: "N-private-id",
        recipient: "child-private-id",
        key: "task_reminder",
        state: "uncertain",
        attempts: 1,
        created_at: "2026-09-07T12:30:00+00:00",
      },
      {
        id: "N-waiting",
        recipient: "child-private-id",
        key: CANARY,
        state: "awaiting_channel",
        attempts: 0,
        created_at: "2026-09-07T12:31:00+00:00",
      },
    ],
  };
}

function card(role = "owner", language = "en") {
  const value = document.createElement("family-health-card");
  value.setConfig({ view: "health", language, entry_id: "entry-1" });
  value._data = data(role);
  document.body.append(value);
  const body = value.shadowRoot.querySelector(".body");
  body.replaceChildren();
  return { card: value, body };
}

test("copy has exact EN/RU/UK key and nested label parity", () => {
  assert.deepEqual(Object.keys(HEALTH_COPY).sort(), ["en", "ru", "uk"]);
  const top = Object.keys(HEALTH_COPY.en).sort();
  const modules = Object.keys(HEALTH_COPY.en.modules).sort();
  const events = Object.keys(HEALTH_COPY.en.events).sort();
  for (const language of ["ru", "uk"]) {
    assert.deepEqual(Object.keys(HEALTH_COPY[language]).sort(), top);
    assert.deepEqual(Object.keys(HEALTH_COPY[language].modules).sort(), modules);
    assert.deepEqual(Object.keys(HEALTH_COPY[language].events).sort(), events);
  }
});

test("parent sees localized known labels and generic unknown labels without raw values", () => {
  const { card: value, body } = card("owner", "ru");
  assert.equal(renderHealth(value, body), true);
  const text = body.textContent;
  assert.match(text, /Семейные сводки/);
  assert.match(text, /Нужно проверить хранение семейных сводок/);
  assert.match(text, /Планировщик/);
  assert.match(text, /Планировщик не смог сохранить/);
  assert.match(text, /Другой компонент/);
  assert.match(text, /Состояние требует проверки/);
  assert.match(text, /Задачи/);
  assert.match(text, /Уведомление/);
  assert.equal(text.includes(CANARY), false);
  assert.equal(text.includes("N-private-id"), false);
  assert.equal(text.includes("child-private-id"), false);
  assert.equal(body.querySelectorAll(".health-metric b")[0].textContent, "3");
  assert.equal(body.querySelectorAll(".health-metric b")[1].textContent, "2");
  value.remove();
});

test("attention count excludes connected states while retaining their visible rows", () => {
  const { card: value, body } = card();
  value._data.health = {
    telegram: "connected",
    mikrotik: "network_connected",
    scheduler: "scheduler_failed",
  };
  assert.equal(countHealthAttention(value._data.health), 1);
  renderHealth(value, body);
  assert.equal(body.querySelector(".health-metric b").textContent, "1");
  assert.match(body.textContent, /Telegram/);
  assert.match(body.textContent, /Connected/);
  assert.match(body.textContent, /Family network/);
  value.remove();
});

test("prototype module names and normalized-invalid dates use generic fixed copy", () => {
  const { card: value, body } = card();
  value._data.health = { constructor: "connected", toString: "connected" };
  value._data.delivery_issues[0].created_at = "2026-02-30T12:30:00+00:00";
  renderHealth(value, body);
  assert.equal(body.querySelectorAll(".health-row strong")[0].textContent, "Other component");
  assert.equal(body.querySelectorAll(".health-row strong")[1].textContent, "Other component");
  assert.equal(body.querySelector(".health-delivery time").textContent, "Time unavailable");
  assert.equal(body.textContent.includes("function Object"), false);
  value.remove();
});

test("nonparent projection is not rendered even if it contains private rows", () => {
  const { card: value, body } = card("child", "uk");
  assert.equal(renderHealth(value, body), false);
  assert.match(body.textContent, /лише батькам/);
  assert.equal(body.textContent.includes(CANARY), false);
  assert.equal(body.querySelector("button"), null);
  value.remove();
});

test("retry and resolve keep the exact existing payload contracts", () => {
  const { card: value, body } = card("parent");
  const calls = [];
  value.command = (action, payload) => calls.push({ action, payload });
  renderHealth(value, body);
  const issue = body.querySelector(".health-delivery");

  issue.querySelector("button").click();
  let form = issue.querySelector("form");
  form.querySelector("input[name=reason]").value = "  Checked private chat  ";
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  assert.equal(calls.length, 0);
  form.querySelector("input[name=confirmed]").checked = true;
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  assert.deepEqual(calls.shift(), {
    action: "notifications.retry",
    payload: { id: "N-private-id", reason: "Checked private chat", confirmed: true },
  });

  body.replaceChildren();
  renderHealth(value, body);
  const resolve = [...body.querySelectorAll(".health-delivery button")].find(
    (button) => button.textContent === "Resolve without resending",
  );
  const resolveActions = resolve.closest(".actions");
  resolve.click();
  form = resolveActions.querySelector("form");
  form.querySelector("input[name=reason]").value = "Acknowledged";
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  assert.deepEqual(calls.shift(), {
    action: "notifications.resolve",
    payload: { id: "N-private-id", reason: "Acknowledged" },
  });
  value.remove();
});

test("stale role, member epoch, issue state, and detached forms cannot dispatch", () => {
  for (const [label, mutate] of [
    ["role", (value) => {
      value._data.role = "adult";
    }],
    ["member epoch", (value) => {
      value._data.members.find((member) => member.id === "owner").revision += 1;
    }],
    ["issue state", (value) => {
      value._data.delivery_issues[0].state = "failed";
    }],
    ["detached", (_value, form) => form.remove()],
  ]) {
    const { card: value, body } = card();
    const calls = [];
    value.command = (...args) => calls.push(args);
    renderHealth(value, body);
    body.querySelector(".health-delivery button").click();
    const form = body.querySelector("form");
    form.querySelector("input[name=reason]").value = "Reviewed";
    form.querySelector("input[name=confirmed]").checked = true;
    mutate(value, form);
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    assert.equal(calls.length, 0, label);
    value.remove();
  }
});

test("refresh reconciliation forces private focused reviews away on access or issue drift", () => {
  const { card: value, body } = card();
  const previous = structuredClone(value._data);
  renderHealth(value, body);
  body.querySelector(".health-delivery button").click();
  body.querySelector("input[name=reason]").focus();
  assert.equal(reconcileHealthRefresh(value, structuredClone(value._data)), false);
  value._data.role = "adult";
  assert.equal(reconcileHealthRefresh(value, previous), true);
  value._data = structuredClone(previous);
  const beforeIssue = structuredClone(value._data);
  value._data.delivery_issues[0].state = "failed";
  assert.equal(reconcileHealthRefresh(value, beforeIssue), true);
  value.remove();
});

test("actual FamilyCard refresh removes a focused review after role revocation", async () => {
  const { card: value } = card();
  const allowed = structuredClone(value._data);
  const revoked = data("child");
  revoked.health = { [CANARY]: CANARY };
  revoked.delivery_issues = [
    {
      id: CANARY,
      recipient: CANARY,
      key: CANARY,
      state: "uncertain",
      attempts: 1,
      created_at: "2026-09-07T12:30:00+00:00",
    },
  ];
  const responses = [allowed, revoked];
  value._hass = {
    language: "en",
    user: { id: "ha-user" },
    callWS: async () => structuredClone(responses.shift()),
  };
  value._data = null;
  await value.refresh();
  value.shadowRoot.querySelector(".health-delivery button").click();
  value.shadowRoot.querySelector("input[name=reason]").focus();
  assert.notEqual(value.shadowRoot.querySelector(".health-review"), null);
  await value.refresh();
  assert.equal(value.shadowRoot.querySelector(".health-review"), null);
  assert.match(value.shadowRoot.textContent, /parents only/);
  assert.equal(value.shadowRoot.textContent.includes(CANARY), false);
  value.remove();
});

test("actual FamilyCard reuses its operation id for the exact failed retry", async () => {
  const { card: value, body } = card();
  const requests = [];
  value._hass = {
    language: "en",
    user: { id: "ha-owner" },
    callWS: async (request) => {
      if (request.type === "family_assistant/execute") {
        requests.push(structuredClone(request));
        throw Object.assign(new Error("synthetic"), { code: "storage_error" });
      }
      return structuredClone(value._data);
    },
  };
  value.refresh = async () => {};

  const waitForIdle = async () => {
    for (let index = 0; index < 20 && value._writing; index += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1));
    }
    assert.equal(value._writing, false);
  };

  const submit = () => {
    const currentBody = value.shadowRoot.querySelector(".body");
    currentBody.replaceChildren();
    renderHealth(value, currentBody);
    currentBody.querySelector(".health-delivery button").click();
    const form = currentBody.querySelector("form");
    form.querySelector("input[name=reason]").value = "Same reviewed reason";
    form.querySelector("input[name=confirmed]").checked = true;
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  };
  submit();
  await waitForIdle();
  submit();
  await waitForIdle();
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[0].payload, requests[1].payload);
  assert.equal(requests[0].operation_id, requests[1].operation_id);
  value.remove();
});

test("malformed health and delivery containers render bounded empty states", () => {
  const { card: value, body } = card();
  value._data.health = [CANARY];
  value._data.delivery_issues = { [CANARY]: CANARY };
  assert.equal(renderHealth(value, body), true);
  assert.match(body.textContent, /No component health problems/);
  assert.match(body.textContent, /No unresolved delivery problems/);
  assert.equal(body.textContent.includes(CANARY), false);
  value.remove();
});
