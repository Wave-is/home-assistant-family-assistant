import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "https://example.test" });
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  FormData: dom.window.FormData,
});

const { ALARM_EDITOR_COPY, openAlarmEditor, reconcileAlarmEditorRefresh, renderAlarmEditor } =
  await import("../custom_components/family_assistant/frontend/alarm-editor.js");

function alarm(overrides = {}) {
  return {
    id: "A000001",
    revision: 3,
    member: "child",
    name: "School <wake>",
    time: "07:15",
    timezone: "Europe/Kyiv",
    days: [0, 2, 4],
    enabled: true,
    exceptions: ["2026-09-14"],
    second_min: 10,
    second_max: 16,
    profile: "strict",
    recheck_grace: 45,
    penalty: -2,
    ...overrides,
  };
}

function setup(options = {}) {
  document.body.replaceChildren();
  const host = document.createElement("div");
  const body = document.createElement("main");
  host.append(body);
  document.body.append(host);
  const calls = [];
  const card = {
    _entry: "entry-1",
    _generation: 1,
    _writing: false,
    _actionError: null,
    _config: { language: options.language || "en" },
    _hass: { language: options.language || "en", config: { time_zone: "Europe/Kyiv" } },
    _data: {
      actor: "parent",
      role: options.role || "parent",
      settings: { modules: options.modules || ["alarms"], timezone: "Europe/Kyiv" },
      members: [
        { id: "parent", name: "Morgan", role: options.role || "parent", active: true, revision: 4 },
        { id: "child", name: "Sam <script>", role: "child", active: true, revision: 7 },
      ],
      alarms: options.alarms || [alarm()],
    },
    button(label, callback, primary = false) {
      const value = document.createElement("button");
      value.textContent = label;
      if (primary) value.className = "primary";
      value.addEventListener("click", callback);
      return value;
    },
    render() {
      body.replaceChildren();
      renderAlarmEditor(card, body);
    },
    async command(action, payload, operationId) {
      calls.push({ action, payload, operationId });
      if (options.command) await options.command(card, { action, payload, operationId });
    },
  };
  return { card, body, calls };
}

function submit(body) {
  body.querySelector("form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
}

function confirmAndSave(body) {
  body.querySelector('[name="confirmed"]').checked = true;
  body.querySelector(".alarm-editor-review button.primary").click();
}

test("EN/RU/UK copy has exact parity and factual strict-mode language", () => {
  const keys = Object.keys(ALARM_EDITOR_COPY.en).sort();
  assert.deepEqual(Object.keys(ALARM_EDITOR_COPY.ru).sort(), keys);
  assert.deepEqual(Object.keys(ALARM_EDITOR_COPY.uk).sort(), keys);
  for (const language of ["en", "ru", "uk"]) {
    assert.equal(ALARM_EDITOR_COPY[language].day_names.length, 7);
    assert.match(ALARM_EDITOR_COPY[language].strict, /siren|сирен/iu);
  }
});

test("edit review preserves every supported value and freezes exact payload", async () => {
  const { card, body, calls } = setup();
  assert.equal(openAlarmEditor(card, card._data.alarms[0]), true);
  submit(body);
  assert.match(body.textContent, /Sam <script>/);
  assert.match(body.textContent, /2026-09-14/);
  confirmAndSave(body);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].payload, {
    id: "A000001",
    revision: 3,
    member: "child",
    name: "School <wake>",
    time: "07:15",
    days: [0, 2, 4],
    timezone: "Europe/Kyiv",
    enabled: true,
    exceptions: ["2026-09-14"],
    second_min: 10,
    second_max: 16,
    profile: "strict",
    recheck_grace: 45,
    penalty: -2,
  });
  assert.equal(card._alarmEditorDraft, null);
  assert.equal(card._data.alarms[0].revision, 3);
});

test("create parses all days, exceptions, and strict integer bounds", () => {
  const { card, body } = setup({ alarms: [] });
  openAlarmEditor(card);
  for (const box of body.querySelectorAll('[name="days"]')) box.checked = false;
  submit(body);
  assert.equal(body.querySelector(".alarm-editor-validation").hidden, false);
  assert.equal(body.querySelector(".alarm-editor-validation").getAttribute("role"), "alert");
  body.querySelector('[name="days"][value="1"]').checked = true;
  body.querySelector('[name="days"][value="6"]').checked = true;
  body.querySelector('[name="exceptions"]').value = "2026-09-20\n2026-09-21,2026-09-20";
  body.querySelector('[name="second_min"]').value = "12.5";
  submit(body);
  assert.equal(card._alarmEditorDraft.step, "edit");
  body.querySelector('[name="second_min"]').value = "12";
  submit(body);
  assert.equal(card._alarmEditorDraft.step, "review");
  assert.deepEqual(card._alarmEditorDraft.values.days, [1, 6]);
  assert.deepEqual(card._alarmEditorDraft.values.exceptions, ["2026-09-20", "2026-09-21"]);
});

test("review Back preserves values and Cancel is available only before uncertainty", async () => {
  const { card, body } = setup({
    command: async (current) => {
      current._actionError = "transport_error";
      current.render();
    },
  });
  openAlarmEditor(card, card._data.alarms[0]);
  body.querySelector('[name="name"]').value = "Preserved draft";
  submit(body);
  const buttons = () => [...body.querySelectorAll("button")];
  buttons().find((item) => item.textContent === ALARM_EDITOR_COPY.en.back).click();
  assert.equal(body.querySelector('[name="name"]').value, "Preserved draft");
  submit(body);
  assert.ok(buttons().some((item) => item.textContent === ALARM_EDITOR_COPY.en.cancel));
  confirmAndSave(body);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(body.textContent, /Retry exact request/);
  assert.ok(!buttons().some((item) => item.textContent === ALARM_EDITOR_COPY.en.cancel));
  assert.ok(!buttons().some((item) => item.textContent === ALARM_EDITOR_COPY.en.back));
});

test("invalid dates, zones, ranges, and bool-like numbers never reach command", () => {
  const invalid = [
    ["exceptions", "2026-02-30"],
    ["timezone", "Not/AZone"],
    ["second_min", "0"],
    ["second_max", "26"],
    ["recheck_grace", "true"],
    ["penalty", "1"],
  ];
  for (const [name, value] of invalid) {
    const { card, body, calls } = setup();
    openAlarmEditor(card, card._data.alarms[0]);
    body.querySelector(`[name="${name}"]`).value = value;
    submit(body);
    assert.equal(card._alarmEditorDraft.step, "edit", name);
    assert.equal(calls.length, 0);
  }
});

test("failed transport and committed response loss retry identical operation", async () => {
  let attempt = 0;
  const { card, body, calls } = setup({
    command: async (current, call) => {
      attempt += 1;
      if (attempt === 1) {
        current._data.alarms[0] = alarm({ revision: 4, name: call.payload.name });
        current._actionError = "response_lost";
      } else current._actionError = null;
      current.render();
    },
  });
  openAlarmEditor(card, card._data.alarms[0]);
  submit(body);
  confirmAndSave(body);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(body.textContent, /Retry exact request/);
  body.querySelector(".alarm-editor-review button.primary").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(card._alarmEditorDraft, null);
});

test("source, member, role, module, entry, and generation changes revoke drafts", () => {
  const mutations = [
    (card) => (card._data.alarms[0].revision += 1),
    (card) => (card._data.members[1].revision += 1),
    (card) => { card._data.role = "adult"; card._data.members[0].role = "adult"; },
    (card) => (card._data.settings.modules = []),
    (card) => (card._entry = "other"),
    (card) => (card._generation += 1),
  ];
  for (const mutate of mutations) {
    const { card, body } = setup();
    openAlarmEditor(card, card._data.alarms[0]);
    const previous = structuredClone(card._data);
    mutate(card);
    assert.equal(reconcileAlarmEditorRefresh(card, previous), true);
    assert.equal(card._alarmEditorDraft, null);
    assert.equal(card._actionError, "conflict");
    assert.equal(renderAlarmEditor(card, body), false);
  }
});

test("detached controls and unsupported source records are inert", () => {
  const { card, body, calls } = setup();
  assert.equal(openAlarmEditor(card, alarm({ profile: "loud" })), false);
  openAlarmEditor(card, card._data.alarms[0]);
  const form = body.querySelector("form");
  body.remove();
  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  assert.equal(calls.length, 0);
});

test("names render as text and cannot inject markup", () => {
  const { card, body } = setup();
  openAlarmEditor(card, card._data.alarms[0]);
  submit(body);
  assert.equal(body.querySelectorAll("script").length, 0);
  assert.match(body.textContent, /School <wake>/);
  assert.match(body.textContent, /Sam <script>/);
});
