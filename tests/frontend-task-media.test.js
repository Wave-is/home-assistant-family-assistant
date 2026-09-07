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
  "Event",
  "File",
  "Blob",
])
  globalThis[key] = dom.window[key];

const createdUrls = [];
const revokedUrls = [];
URL.createObjectURL = () => {
  const value = `blob:private-${createdUrls.length + 1}`;
  createdUrls.push(value);
  return value;
};
URL.revokeObjectURL = (value) => revokedUrls.push(value);

const {
  disposeTaskMedia,
  reconcileTaskMediaRefresh,
  renderTaskMedia,
} = await import(
  "../custom_components/family_assistant/frontend/task-media-view.js"
);
const { TASK_MEDIA_COPY } = await import(
  "../custom_components/family_assistant/frontend/task-media-copy.js"
);

const clone = (value) => structuredClone(value);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function eventually(predicate, message = "condition was not reached") {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail(message);
}

function baseState(role = "child") {
  const actor = role === "parent" ? "parent_1" : role === "guest" ? "guest_1" : "child_1";
  return {
    revision: 1,
    actor,
    role,
    settings: { modules: ["tasks"], timezone: "Europe/Kyiv" },
    members: [
      { id: "parent_1", role: "parent", active: true, revision: 3 },
      { id: "child_1", role: "child", active: true, revision: 7 },
      { id: "child_2", role: "child", active: true, revision: 9 },
      { id: "guest_1", role: "guest", active: true, revision: 2 },
    ],
    tasks: [
      {
        id: "TPHOTO_1",
        revision: 5,
        status: "in_progress",
        title: "Synthetic photo task",
        assignee: "child_1",
        assignee_revision: 7,
        report_type: "photo",
        report_attachments: [],
      },
    ],
  };
}

function jsonResponse(value) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function imageResponse() {
  return new Response(new Uint8Array([0x89, 0x50, 0x4e, 0x47]), {
    status: 200,
    headers: { "content-type": "image/png", "content-length": "4" },
  });
}

function makeCard(t, { role = "child", language = "en" } = {}) {
  const state = baseState(role);
  const host = document.createElement("div");
  document.body.append(host);
  const wsCalls = [];
  const httpCalls = [];
  const receipts = new Map();
  let loseReserve = false;
  let loseUpload = false;
  let loseSubmit = false;
  let mediaAvailable = null;
  let uploadGate = null;
  let submitGate = null;

  Object.assign(host, {
    _entry: "entry_1",
    _generation: 1,
    _writing: false,
    _actionError: null,
    _taskMediaDraft: null,
    _config: { language },
    _data: state,
    button(label, callback, primary = false) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      if (primary) button.className = "primary";
      button.disabled = Boolean(this._writing);
      button.addEventListener("click", callback);
      return button;
    },
    render() {
      const item = this._data.tasks.find((value) => value.id === "TPHOTO_1");
      const section = renderTaskMedia(this, item);
      this.replaceChildren(...(section ? [section] : []));
    },
    async refresh() {
      reconcileTaskMediaRefresh(this);
    },
  });

  host._hass = {
    language,
    user: { id: role === "parent" ? "ha_parent" : "ha_child" },
    async callWS(message) {
      wsCalls.push(clone(message));
      if (receipts.has(message.operation_id)) return clone(receipts.get(message.operation_id));
      if (message.action === "media.reserve") {
        const receipt = { id: "M0123456789abcdef0123456789abcdef", revision: 1, status: "reserved" };
        receipts.set(message.operation_id, receipt);
        if (loseReserve) {
          loseReserve = false;
          throw Object.assign(new Error("response lost"), { code: "response_lost" });
        }
        return clone(receipt);
      }
      assert.equal(message.action, "tasks.submit");
      const task = state.tasks[0];
      const receipt = { id: task.id, revision: message.payload.revision + 1, status: "submitted" };
      receipts.set(message.operation_id, receipt);
      task.revision = receipt.revision;
      task.status = "submitted";
      task.report_attachments = [
        {
          id: message.payload.media.id,
          revision: message.payload.media.revision + 1,
          purpose: "task_report",
          mime_type: "image/png",
          size_bytes: 4,
          status: "attached",
        },
      ];
      if (submitGate) await submitGate;
      if (loseSubmit) {
        loseSubmit = false;
        throw Object.assign(new Error("response lost"), { code: "response_lost" });
      }
      return clone(receipt);
    },
    async fetchWithAuth(path, init) {
      httpCalls.push({ path, init });
      if (init.method === "GET") return imageResponse();
      assert.equal(init.method, "PUT");
      if (uploadGate) await uploadGate;
      mediaAvailable ||= {
        id: "M0123456789abcdef0123456789abcdef",
        revision: 2,
        status: "available",
      };
      if (loseUpload) {
        loseUpload = false;
        throw new Error("response lost");
      }
      return jsonResponse(mediaAvailable);
    },
  };
  host.render();
  t.after(() => {
    disposeTaskMedia(host);
    host.remove();
  });
  return {
    host,
    state,
    wsCalls,
    httpCalls,
    loseReserve: () => (loseReserve = true),
    loseUpload: () => (loseUpload = true),
    loseSubmit: () => (loseSubmit = true),
    deferUpload() {
      let release;
      uploadGate = new Promise((resolve) => (release = resolve));
      return () => {
        uploadGate = null;
        release();
      };
    },
    deferSubmit() {
      let release;
      submitGate = new Promise((resolve) => (release = resolve));
      return () => {
        submitGate = null;
        release();
      };
    },
  };
}

function button(host, label) {
  return [...host.querySelectorAll("button")].find((item) => item.textContent === label);
}

function choose(host, name = "private.png") {
  const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, {
    type: "image/png",
    lastModified: 123,
  });
  const input = host.querySelector('input[type="file"]');
  Object.defineProperty(input, "files", { configurable: true, value: [file] });
  button(host, TASK_MEDIA_COPY.en.review).click();
  return file;
}

function confirmAndClick(host, confirmationName, label) {
  const confirmation = host.querySelector(`input[name="${confirmationName}"]`);
  confirmation.checked = true;
  confirmation.dispatchEvent(new Event("change", { bubbles: true }));
  const action = button(host, label);
  assert.equal(action.disabled, false);
  action.click();
}

async function uploadReady(host) {
  confirmAndClick(host, "confirm_upload", TASK_MEDIA_COPY.en.upload);
  await eventually(() => host._taskMediaDraft?.stage === "ready" && !host._writing);
}

test("localized copy has parity and states the explicit retained-EXIF private boundary", () => {
  const keys = Object.keys(TASK_MEDIA_COPY.en).sort();
  assert.deepEqual(Object.keys(TASK_MEDIA_COPY.ru).sort(), keys);
  assert.deepEqual(Object.keys(TASK_MEDIA_COPY.uk).sort(), keys);
  for (const locale of Object.values(TASK_MEDIA_COPY)) {
    assert.match(locale.privacy, /EXIF/i);
    assert.match(locale.privacy, /Telegram/i);
  }
});

test("only a current eligible assignee or parent can begin a photo review", (t) => {
  const child = makeCard(t);
  assert.ok(child.host.querySelector('input[type="file"]'));
  child.state.tasks[0].assignee = "child_2";
  child.state.tasks[0].assignee_revision = 9;
  child.host.render();
  assert.equal(child.host.querySelector('input[type="file"]'), null);

  const parent = makeCard(t, { role: "parent" });
  assert.ok(parent.host.querySelector('input[type="file"]'));
  parent.state.tasks[0].status = "submitted";
  parent.host.render();
  assert.equal(parent.host.querySelector('input[type="file"]'), null);

  const guest = makeCard(t, { role: "guest" });
  assert.equal(guest.host.querySelector('input[type="file"]'), null);
  assert.equal(renderTaskMedia(guest.host, guest.state.tasks[0]), null);
  assert.equal(renderTaskMedia(guest.host, { ...guest.state.tasks[0], report_type: "text" }), null);
});

test("review uses textContent and sends exact reserve, upload, and separate submit requests", async (t) => {
  const fixture = makeCard(t);
  const file = choose(
    fixture.host,
    `<img src=x onerror="alert(1)">.png${"x".repeat(500)}`,
  );
  assert.equal(fixture.host.querySelectorAll("img").length, 1);
  assert.equal(
    fixture.host.querySelector("img").alt,
    TASK_MEDIA_COPY.en.selected_photo_alt,
  );
  assert.match(fixture.host.textContent, /<img src=x/);
  assert.ok(fixture.host.querySelector(".task-media-file").textContent.length <= 160);
  assert.equal(fixture.wsCalls.length, 0);
  assert.equal(fixture.httpCalls.length, 0);
  await uploadReady(fixture.host);

  assert.equal(fixture.wsCalls.length, 1);
  assert.deepEqual(fixture.wsCalls[0], {
    type: "family_assistant/execute",
    entry_id: "entry_1",
    action: "media.reserve",
    payload: {
      purpose: "task_report",
      task_id: "TPHOTO_1",
      task_revision: 5,
      uploader_revision: 7,
    },
    operation_id: fixture.wsCalls[0].operation_id,
  });
  assert.match(fixture.wsCalls[0].operation_id, /^[0-9a-f-]{36}$/);
  assert.equal(fixture.httpCalls.length, 1);
  assert.equal(
    fixture.httpCalls[0].path,
    "/api/family_assistant/media/entry_1/M0123456789abcdef0123456789abcdef",
  );
  assert.equal(fixture.httpCalls[0].init.body, file);
  assert.deepEqual(fixture.httpCalls[0].init.headers, {
    "Content-Type": "image/png",
    "X-Family-Media-Revision": "1",
  });
  assert.equal(fixture.state.tasks[0].status, "in_progress");

  confirmAndClick(fixture.host, "confirm_submit", TASK_MEDIA_COPY.en.submit);
  await eventually(() => fixture.host._taskMediaDraft === null && !fixture.host._writing);
  assert.equal(fixture.wsCalls.length, 2);
  assert.deepEqual(fixture.wsCalls[1], {
    type: "family_assistant/execute",
    entry_id: "entry_1",
    action: "tasks.submit",
    payload: {
      id: "TPHOTO_1",
      revision: 5,
      media: { id: "M0123456789abcdef0123456789abcdef", revision: 2 },
    },
    operation_id: fixture.wsCalls[1].operation_id,
  });
  assert.equal(fixture.state.tasks[0].status, "submitted");
  assert.equal(fixture.httpCalls.filter((call) => call.init.method === "GET").length, 0);
});

test("a lost reserve response retries the exact frozen operation and file", async (t) => {
  const fixture = makeCard(t);
  const file = choose(fixture.host);
  fixture.loseReserve();
  confirmAndClick(fixture.host, "confirm_upload", TASK_MEDIA_COPY.en.upload);
  await eventually(() => !fixture.host._writing && fixture.wsCalls.length === 1);
  assert.ok(fixture.host._taskMediaDraft);
  const first = clone(fixture.wsCalls[0]);
  confirmAndClick(fixture.host, "confirm_upload", TASK_MEDIA_COPY.en.retry_upload);
  await eventually(() => fixture.host._taskMediaDraft?.stage === "ready");
  assert.deepEqual(fixture.wsCalls[1], first);
  assert.equal(fixture.httpCalls[0].init.body, file);
});

test("a lost upload response retries the same reservation revision and reviewed File", async (t) => {
  const fixture = makeCard(t);
  const file = choose(fixture.host);
  fixture.loseUpload();
  confirmAndClick(fixture.host, "confirm_upload", TASK_MEDIA_COPY.en.upload);
  await eventually(() => !fixture.host._writing && fixture.httpCalls.length === 1);
  assert.equal(fixture.host._taskMediaDraft.reservation.revision, 1);
  confirmAndClick(fixture.host, "confirm_upload", TASK_MEDIA_COPY.en.retry_upload);
  await eventually(() => fixture.host._taskMediaDraft?.stage === "ready");
  assert.equal(fixture.wsCalls.length, 1);
  assert.equal(fixture.httpCalls[0].init.body, file);
  assert.equal(fixture.httpCalls[1].init.body, file);
  assert.equal(fixture.httpCalls[0].init.headers["X-Family-Media-Revision"], "1");
  assert.equal(fixture.httpCalls[1].init.headers["X-Family-Media-Revision"], "1");
});

test("post-commit submit loss retains only an exact frozen replay", async (t) => {
  const fixture = makeCard(t);
  choose(fixture.host);
  await uploadReady(fixture.host);
  fixture.loseSubmit();
  confirmAndClick(fixture.host, "confirm_submit", TASK_MEDIA_COPY.en.submit);
  await eventually(
    () => !fixture.host._writing && fixture.state.tasks[0].status === "submitted",
  );
  const frozen = clone(fixture.wsCalls[1]);
  assert.ok(fixture.host._taskMediaDraft);
  assert.ok(button(fixture.host, TASK_MEDIA_COPY.en.retry_submit));
  button(fixture.host, TASK_MEDIA_COPY.en.retry_submit).click();
  await eventually(() => fixture.host._taskMediaDraft === null);
  assert.deepEqual(fixture.wsCalls[2], frozen);
});

test("a late submit success cannot erase a new entry's unrelated draft", async (t) => {
  const fixture = makeCard(t);
  choose(fixture.host);
  await uploadReady(fixture.host);
  const release = fixture.deferSubmit();
  confirmAndClick(fixture.host, "confirm_submit", TASK_MEDIA_COPY.en.submit);
  await eventually(
    () => fixture.host._writing && fixture.state.tasks[0].status === "submitted",
  );
  const unrelatedDraft = { unrelated: true };
  const newWriteOwner = {};
  fixture.host._entry = "entry_2";
  fixture.host._generation += 1;
  fixture.host._hass.user.id = "new_ha_user";
  fixture.host._taskMediaDraft = unrelatedDraft;
  fixture.host._taskMediaWriteOwner = newWriteOwner;
  fixture.host._writing = true;
  release();
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(fixture.host._taskMediaDraft, unrelatedDraft);
  assert.equal(fixture.host._taskMediaWriteOwner, newWriteOwner);
  assert.equal(fixture.host._writing, true);
});

test("selected preview is local-only, bounded, revoked, and recreated only in valid scope", (t) => {
  const fixture = makeCard(t);
  const before = createdUrls.length;
  choose(fixture.host);
  const first = fixture.host.querySelector("img").src;
  assert.equal(createdUrls.length, before + 1);
  assert.equal(fixture.httpCalls.length, 0);
  assert.equal(fixture.wsCalls.length, 0);

  fixture.host._error = new Error("view unavailable");
  disposeTaskMedia(fixture.host, { keepDraft: true });
  assert.ok(revokedUrls.includes(first));
  fixture.host.render();
  assert.equal(fixture.host.querySelector("img"), null);
  assert.equal(createdUrls.length, before + 1);

  fixture.host._error = null;
  assert.equal(reconcileTaskMediaRefresh(fixture.host), false);
  fixture.host.render();
  const restored = fixture.host.querySelector("img").src;
  assert.notEqual(restored, first);
  assert.equal(createdUrls.length, before + 2);
  fixture.state.members[1].revision += 1;
  assert.equal(reconcileTaskMediaRefresh(fixture.host), true);
  assert.ok(revokedUrls.includes(restored));
  assert.equal(fixture.host._taskMediaDraft, null);
});

test("selected preview decode failure is honest and never interprets the filename as markup", (t) => {
  const fixture = makeCard(t);
  choose(fixture.host, "<script>private()</script>.png");
  const preview = fixture.host.querySelector("img");
  const url = preview.src;
  preview.dispatchEvent(new Event("error"));
  assert.equal(fixture.host.querySelector("img"), null);
  assert.ok(fixture.host.textContent.includes(TASK_MEDIA_COPY.en.preview_failed));
  assert.equal(button(fixture.host, TASK_MEDIA_COPY.en.upload), undefined);
  assert.ok(fixture.host.textContent.includes("<script>private()</script>.png"));
  assert.equal(fixture.host.querySelector("script"), null);
  assert.ok(revokedUrls.includes(url));
  assert.equal(fixture.httpCalls.length, 0);
  assert.equal(fixture.wsCalls.length, 0);
});

test("error disposal preserves a frozen retry but recovery still reconciles authority", async (t) => {
  const fixture = makeCard(t);
  const file = choose(fixture.host);
  await uploadReady(fixture.host);
  const draft = fixture.host._taskMediaDraft;
  const reserveRequest = draft.reserveRequest;
  const submitRequest = draft.submitRequest;
  const reservation = draft.reservation;
  disposeTaskMedia(fixture.host, { keepDraft: true });
  assert.equal(fixture.host._taskMediaDraft, draft);
  assert.equal(draft.file, file);
  assert.equal(draft.reserveRequest, reserveRequest);
  assert.equal(draft.submitRequest, submitRequest);
  assert.equal(draft.reservation, reservation);
  assert.equal(draft.controller.signal.aborted, true);

  fixture.host._error = new Error("view unavailable");
  assert.equal(reconcileTaskMediaRefresh(fixture.host), false);
  fixture.host._error = null;
  fixture.state.members[1].revision += 1;
  assert.equal(reconcileTaskMediaRefresh(fixture.host), true);
  assert.equal(fixture.host._taskMediaDraft, null);
});

test("a late old-generation upload cannot unlock a newer write owner", async (t) => {
  const fixture = makeCard(t);
  choose(fixture.host);
  const release = fixture.deferUpload();
  confirmAndClick(fixture.host, "confirm_upload", TASK_MEDIA_COPY.en.upload);
  await eventually(() => fixture.host._writing && fixture.httpCalls.length === 1);
  const newOwner = {};
  fixture.host._generation += 1;
  fixture.host._taskMediaWriteOwner = newOwner;
  fixture.host._writing = true;
  release();
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(fixture.host._taskMediaWriteOwner, newOwner);
  assert.equal(fixture.host._writing, true);
});

test("stale DOM cannot start a review while the current view is in error", (t) => {
  const fixture = makeCard(t);
  const input = fixture.host.querySelector('input[type="file"]');
  Object.defineProperty(input, "files", {
    configurable: true,
    value: [new File([1], "private.png", { type: "image/png" })],
  });
  fixture.host._error = new Error("view unavailable");
  button(fixture.host, TASK_MEDIA_COPY.en.review).click();
  assert.equal(fixture.host._taskMediaDraft, null);
  assert.equal(fixture.wsCalls.length, 0);
});

test("refresh aborts drafts on revision, member epoch, module, or card generation drift", (t) => {
  const mutations = [
    (fixture) => (fixture.state.tasks[0].revision += 1),
    (fixture) => (fixture.state.members[1].revision += 1),
    (fixture) => (fixture.state.settings.modules = []),
    (fixture) => (fixture.host._generation += 1),
    (fixture) => (fixture.host._hass.user.id = "different_ha_session"),
  ];
  for (const mutate of mutations) {
    const fixture = makeCard(t);
    choose(fixture.host);
    const signal = fixture.host._taskMediaDraft.controller.signal;
    mutate(fixture);
    assert.equal(reconcileTaskMediaRefresh(fixture.host), true);
    assert.equal(fixture.host._taskMediaDraft, null);
    assert.equal(signal.aborted, true);
    assert.equal(fixture.host._actionError, "conflict");
  }
});

test("current and parent historical photos download only on click and revoke on scope change", async (t) => {
  const fixture = makeCard(t, { role: "parent" });
  const current = {
    id: "M11111111111111111111111111111111",
    revision: 3,
    purpose: "task_report",
    mime_type: "image/png",
    size_bytes: 4,
    status: "attached",
  };
  const historical = {
    id: "M22222222222222222222222222222222",
    revision: 8,
    purpose: "task_report",
    mime_type: "image/jpeg",
    size_bytes: 7,
    status: "attached",
  };
  fixture.state.tasks[0].report_attachments = [current];
  fixture.state.tasks[0].previous_reports = [
    { report: "PARENT-ONLY-CANARY", report_attachments: [historical] },
  ];
  // Parent retention authority intentionally survives the child's identity
  // epoch and active-role changes; no new upload is permitted in that state.
  fixture.state.members[1].revision += 1;
  fixture.state.members[1].active = false;
  fixture.host.render();
  assert.equal(fixture.httpCalls.length, 0);
  assert.equal(fixture.host.textContent.includes(current.id), false);
  assert.equal(fixture.host.textContent.includes(historical.id), false);
  assert.equal(fixture.host.textContent.includes("PARENT-ONLY-CANARY"), false);
  const loads = [...fixture.host.querySelectorAll("button")].filter(
    (item) => item.textContent === TASK_MEDIA_COPY.en.download,
  );
  assert.equal(loads.length, 2);
  assert.equal(fixture.host.querySelector('input[type="file"]'), null);
  loads[0].click();
  await eventually(() => fixture.host.querySelector("img"));
  assert.equal(fixture.httpCalls.length, 1);
  assert.equal(fixture.httpCalls[0].init.method, "GET");
  assert.equal(fixture.httpCalls[0].init.headers["X-Family-Media-Revision"], "3");
  const url = fixture.host.querySelector("img").src;
  fixture.state.tasks[0].revision += 1;
  assert.equal(reconcileTaskMediaRefresh(fixture.host), true);
  assert.ok(revokedUrls.includes(url));
});
