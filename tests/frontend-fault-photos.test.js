import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><body></body>", { url: "https://example.invalid" });
for (const name of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "Event", "File", "Blob", "FormData"])
  globalThis[name] = dom.window[name];
const created = [], revoked = [];
URL.createObjectURL = () => { const url = `blob:private-${created.length}`; created.push(url); return url; };
URL.revokeObjectURL = (url) => revoked.push(url);
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { setupFaultCard } = await import("./fixtures/fault-photo-harness.js");
const { FAULT_PHOTO_COPY } = await import("../custom_components/family_assistant/frontend/fault-photo-copy.js");
const { reconcileFaultPhotos } = await import("../custom_components/family_assistant/frontend/fault-photo-view.js");
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function until(check) { for (let i = 0; i < 100; i++) { if (check()) return; await tick(); } assert.fail("Timed out"); }
async function setup(t, lang = "en", role = "child") { const f = await setupFaultCard(lang, role); t.after(() => f.card.remove()); return f; }
const button = (card, text) => [...card.shadowRoot.querySelectorAll("button")].find((node) => node.textContent === text);
function choose(card, lang = "en") {
  button(card, FAULT_PHOTO_COPY[lang].add).click();
  const input = card.shadowRoot.querySelector('input[type="file"]');
  Object.defineProperty(input, "files", { value: [new File([new Uint8Array([1, 2, 3, 4])], "local-private.png", { type: "image/png" })] });
  input.dispatchEvent(new Event("change"));
}
async function ready(card, lang = "en") {
  button(card, FAULT_PHOTO_COPY[lang].upload).click();
  await until(() => card._faultPhotoDraft?.available && !card._writing && !card._loading);
}
function confirm(card) {
  const form = card.shadowRoot.querySelector("[data-fault-photo-form]");
  const check = form.querySelector('[name="reviewed"]'); check.checked = true; check.dispatchEvent(new Event("change"));
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}
test("copy parity explains EXIF and separate private evidence", () => {
  for (const value of Object.values(FAULT_PHOTO_COPY)) {
    assert.deepEqual(Object.keys(value).sort(), Object.keys(FAULT_PHOTO_COPY.en).sort());
    assert.match(value.privacy, /EXIF/); assert.match(value.privacy, /Telegram/);
  }
});
for (const lang of ["en", "ru", "uk"]) test(`${lang} real card upload, explicit attach, private view and detach cleanup`, async (t) => {
  const f = await setup(t, lang); const { card, calls, http, state } = f;
  choose(card, lang); assert.equal(calls.length, 0); assert.equal(http.length, 0);
  assert.match(card.shadowRoot.textContent, /Synthetic leaking filter/);
  await ready(card, lang); assert.equal(calls.length, 1); assert.equal(state.maintenance.faults[0].revision, 1);
  const fileUrl = card._faultPhotoDraft.preview;
  // Submission without a fresh review checkbox is inert.
  card.shadowRoot.querySelector("[data-fault-photo-form]").dispatchEvent(new Event("submit", { cancelable: true }));
  assert.equal(calls.length, 1);
  confirm(card); await until(() => !card._faultPhotoDraft && !card._writing && !card._loading);
  assert.equal(state.maintenance.faults[0].task_status, "assigned");
  assert.deepEqual(calls.map((call) => call.action), ["media.reserve", "maintenance.fault_photo_attach"]);
  assert.ok(revoked.includes(fileUrl)); assert.equal(http.length, 1);
  button(card, FAULT_PHOTO_COPY[lang].view).click();
  await until(() => card._faultPhotoDownloads?.get("MF000001")?.url);
  const download = card._faultPhotoDownloads.get("MF000001").url;
  assert.equal(http[1].method, "GET"); assert.equal(http[1].cache, "no-store");
  card.remove(); assert.ok(revoked.includes(download));
});
for (const phase of ["media.reserve", "PUT", "maintenance.fault_photo_attach"]) test(`lost ${phase} response retries the frozen request`, async (t) => {
  const { card, calls, http, lose } = await setup(t); choose(card); lose.add(phase);
  button(card, FAULT_PHOTO_COPY.en.upload).click();
  await until(() => !card._writing && !card._loading);
  if (phase !== "maintenance.fault_photo_attach") {
    assert.ok(card._faultPhotoDraft); button(card, FAULT_PHOTO_COPY.en.retry).click();
    await until(() => card._faultPhotoDraft?.available && !card._writing && !card._loading);
  }
  confirm(card); await until(() => !card._writing && !card._loading);
  if (phase === "maintenance.fault_photo_attach") { assert.ok(card._faultPhotoDraft?.pending); confirm(card); await until(() => !card._writing && !card._loading); }
  assert.equal(card._faultPhotoDraft, null);
  if (phase === "PUT") assert.deepEqual(http[1], http[0]);
  else { const retries = calls.filter((call) => call.action === phase); assert.equal(retries.length, 2); assert.deepEqual(retries[0], retries[1]); }
});
for (const drift of ["actor", "module", "task", "user", "fault", "assignment", "entry"]) test(`${drift} drift removes draft and disables captured controls`, async (t) => {
  const { card, calls, state, api } = await setup(t); choose(card); const old = button(card, FAULT_PHOTO_COPY.en.upload), preview = card._faultPhotoDraft.preview;
  if (drift === "actor") state.members.find((item) => item.id === "child").revision++;
  if (drift === "module") state.settings.modules = ["maintenance"];
  if (drift === "task") state.maintenance.faults[0].task_revision++;
  if (drift === "user") api.user.id = "another_user";
  if (drift === "fault") state.maintenance.faults[0].revision++;
  if (drift === "assignment") state.maintenance.faults[0].assignee = "adult";
  if (drift === "entry") card._generation++;
  await card.refresh(); reconcileFaultPhotos(card);
  old.click(); await tick(); assert.equal(calls.length, 0); assert.equal(card._faultPhotoDraft, null); assert.ok(revoked.includes(preview));
});
test("owner purge is explicit, exact-retried and never completes a task", async (t) => {
  const { card, state, lose, calls } = await setup(t, "en", "owner"); choose(card); await ready(card); confirm(card);
  await until(() => !card._faultPhotoDraft && !card._writing && !card._loading);
  button(card, FAULT_PHOTO_COPY.en.purge).click();
  const field = card.shadowRoot.querySelector('[name="reason"]'); field.value = "Synthetic private reason"; field.dispatchEvent(new Event("input"));
  lose.add("maintenance.fault_photo_purge"); confirm(card); await until(() => !card._writing && !card._loading);
  assert.ok(card._faultPhotoDraft?.pending); assert.equal(card.shadowRoot.querySelector('[name="reason"]').disabled, true);
  confirm(card); await until(() => !card._writing && !card._loading);
  assert.equal(card._faultPhotoDraft, null); assert.deepEqual(calls.at(-1), calls.at(-2));
  assert.equal(state.maintenance.faults[0].task_status, "assigned"); assert.equal(state.maintenance.faults[0].photo_attachment, undefined);
});
test("revocation during HTTP upload cancels follow-up attach and drops bytes", async (t) => {
  const { card, calls, state, deferHttp } = await setup(t); choose(card);
  const release = deferHttp(); button(card, FAULT_PHOTO_COPY.en.upload).click(); await until(() => card._faultPhotoDraft?.reservation);
  card._data.settings.modules = []; reconcileFaultPhotos(card); state.settings.modules = [];
  release(); await until(() => !card._writing); assert.equal(card._faultPhotoDraft, null); assert.equal(calls.length, 1);
});
test("malformed metadata, no server upload grant, and guests have no image controls", async (t) => {
  const { card, state } = await setup(t);
  const fault = state.maintenance.faults[0]; fault.can_upload_photo = false; fault.photo_attachment = { id: "Mfake", purpose: "task_report", status: "attached", revision: 3 };
  await card.refresh(); assert.equal(card.shadowRoot.querySelector(".fault-photo"), null);
  const guest = await setup(t, "en", "guest"); assert.equal(guest.card.shadowRoot.querySelector(".fault-photo"), null);
});
