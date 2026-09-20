import assert from "node:assert/strict";
import {test, afterEach} from "node:test";
import {JSDOM} from "jsdom";
const dom = new JSDOM("<!doctype html><body></body>", {url: "https://example.invalid"});
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "Event", "FormData"]) globalThis[key] = dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const clone = value => structuredClone(value);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const waitFor = async (check, ms = 2000) => {
  const start = Date.now();
  while (!check()) {
    if (Date.now() - start > ms) throw new Error("Timed out waiting for async card update");
    await new Promise(resolve => setTimeout(resolve, 10));
  }
};
const members = [
  {id: "owner", name: "Example Owner", role: "owner", active: true, revision: 1},
  {id: "child-a", name: "Child Alpha", role: "child", active: true, revision: 2},
];
const task = (id, title, status, due_at = null) => ({id, title, status, revision: 1, assignee: "child-a", due_at, checklist: []});
const alarm = (id, time, days, enabled) => ({id, member: "child-a", revision: 1, time, days, enabled, exceptions: [], penalty: 0});
function state() {
  return {
    revision: 1, role: "owner", actor: "owner", members: clone(members),
    settings: {name: "Example Family", timezone: "UTC", modules: ["tasks", "alarms"]},
    tasks: [
      task("T1", "Water plants", "assigned", "2026-09-21T08:00:00+00:00"),
      task("T2", "Read chapter", "completed"),
      task("T3", "Clean desk", "assigned", "2026-09-20T08:00:00+00:00"),
    ],
    alarms: [alarm("A1", "07:00", [0, 1, 2, 3, 4], true), alarm("A2", "09:30", [5, 6], false)],
  };
}
async function cardFor(view, extra = {}) {
  const calls = [];
  const data = state();
  const apply = message => {
    if (message.action === "alarms.enable") {
      const alarm = data.alarms.find(item => item.id === message.payload.id);
      if (alarm && alarm.revision === message.payload.revision) {alarm.enabled = message.payload.enabled; alarm.revision += 1;}
      return;
    }
    const task = data.tasks.find(item => item.id === message.payload.id);
    if (!task || task.revision !== message.payload.revision) throw new Error("revision_conflict");
    if (message.action === "tasks.complete") task.status = "completed";
    if (message.action === "tasks.reopen") task.status = "assigned";
    task.revision += 1;
  };
  const card = document.createElement("family-assistant-card");
  card.setConfig({entry_id: "example", view, ...extra});
  document.body.append(card);
  card.hass = {
    user: {id: "example-owner"}, language: "en",
    callWS: async message => {
      calls.push(clone(message));
      if (message.type === "family_assistant/view") return clone(data);
      if (message.type === "family_assistant/execute") {apply(message); return {};}
      throw new Error("Unexpected endpoint");
    },
  };
  await tick();
  return {card, calls};
}
afterEach(() => document.body.replaceChildren());

test("compact tasks card renders only active tasks, open tasks first by due date", async () => {
  const {card} = await cardFor("tasks");
  const root = card.shadowRoot;
  assert.equal(root.querySelector(".compact-list"), root.querySelector(".body .compact-list"));
  const titles = [...root.querySelectorAll(".compact-title")].map(node => node.textContent);
  assert.deepEqual(titles, ["Clean desk", "Water plants"]);
  assert.equal(root.querySelectorAll("button").length, 0);
  const boxes = [...root.querySelectorAll(".compact-row input[type=checkbox]")];
  assert.deepEqual(boxes.map(box => box.checked), [false, false]);
  assert.equal(root.querySelector(".compact-row.done"), null);
  assert.match(root.querySelector(".compact-row .compact-meta").textContent, /Child Alpha · 2026-09-20/);
  assert.equal(card.getCardSize(), 4);
});

test("compact task checkbox sends tasks.complete with the exact payload and the task leaves the list", async () => {
  const {card, calls} = await cardFor("tasks", {compact: true});
  const box = card.shadowRoot.querySelector(".compact-row input[type=checkbox]");
  box.checked = true;
  box.dispatchEvent(new dom.window.Event("change"));
  await waitFor(() => calls.some(item => item.type === "family_assistant/execute" && item.action === "tasks.complete"));
  const complete = calls.find(item => item.action === "tasks.complete");
  assert.deepEqual(complete.payload, {id: "T3", revision: 1});
  assert.equal(complete.entry_id, "example");
  assert.ok(complete.operation_id);
  await waitFor(() => card.shadowRoot.querySelectorAll(".compact-row").length === 1 && calls.filter(item => item.type === "family_assistant/view").length >= 2);
  const titles = [...card.shadowRoot.querySelectorAll(".compact-title")].map(node => node.textContent);
  assert.deepEqual(titles, ["Water plants"]);
});

test("compact alarms card toggles alarms.enable per checkbox without buttons", async () => {
  const {card, calls} = await cardFor("alarms", {compact: true});
  const root = card.shadowRoot;
  assert.equal(root.querySelectorAll("button").length, 0);
  const rows = [...root.querySelectorAll(".compact-row")];
  assert.deepEqual([...root.querySelectorAll(".compact-title")].map(node => node.textContent), ["07:00", "09:30"]);
  assert.match(rows[0].querySelector(".compact-meta").textContent, /Weekdays/);
  assert.match(rows[1].querySelector(".compact-meta").textContent, /Weekends/);
  const first = rows[0].querySelector("input[type=checkbox]");
  assert.equal(first.checked, true);
  first.checked = false;
  first.dispatchEvent(new dom.window.Event("change"));
  await waitFor(() => calls.some(item => item.type === "family_assistant/execute" && item.action === "alarms.enable"));
  const firstWrite = calls.find(item => item.action === "alarms.enable");
  assert.deepEqual(firstWrite.payload, {id: "A1", revision: 1, enabled: false});
  await waitFor(() => card.shadowRoot.querySelectorAll(".compact-row").length === 2 && calls.filter(item => item.type === "family_assistant/view").length >= 2);
  const secondRow = [...card.shadowRoot.querySelectorAll(".compact-row")].find(row => row.querySelector(".compact-title").textContent === "09:30");
  const second = secondRow.querySelector("input[type=checkbox]");
  assert.equal(second.checked, false);
  second.checked = true;
  second.dispatchEvent(new dom.window.Event("change"));
  await waitFor(() => calls.filter(item => item.type === "family_assistant/execute" && item.action === "alarms.enable").length === 2);
  const secondWrite = calls.filter(item => item.action === "alarms.enable")[1];
  assert.deepEqual(secondWrite.payload, {id: "A2", revision: 1, enabled: true});
});

test("non-compact cards keep the full panel and card size", async () => {
  const {card} = await cardFor("tasks", {compact: false});
  assert.equal(card.shadowRoot.querySelector(".compact-list"), null);
  assert.equal(card.getCardSize(), 5);
});

test("Lovelace editor compact checkbox emits exact config changes", async () => {
  const editor = document.createElement("family-assistant-card-editor");
  editor.setConfig({type: "custom:family-tasks-card"});
  let emitted;
  editor.addEventListener("config-changed", event => {emitted = event.detail.config;});
  editor.hass = {language: "en", callWS: async () => [{entry_id: "synthetic", title: "Example household"}]};
  document.body.append(editor);
  await tick();
  const label = [...editor.shadowRoot.querySelectorAll("label.check")].find(item => /Compact checklist view/.test(item.textContent));
  assert.ok(label, "compact editor checkbox is missing");
  const box = label.querySelector("input[type=checkbox]");
  assert.equal(box.checked, true);
  box.checked = false;
  box.dispatchEvent(new dom.window.Event("change"));
  assert.equal(emitted.compact, false);
  assert.equal(emitted.type, "custom:family-tasks-card");
  box.checked = true;
  box.dispatchEvent(new dom.window.Event("change"));
  assert.equal("compact" in emitted, false);
});
