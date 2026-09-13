import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";
import {renderOnlineSchool, onlineSchoolSafeLink} from "../custom_components/family_assistant/frontend/online-school-view.js";
import {ONLINE_SCHOOL_COPY} from "../custom_components/family_assistant/frontend/online-school-copy.js";
import {renderSchool} from "../custom_components/family_assistant/frontend/school-view.js";

const NOW = new Date("2026-09-14T21:30:00Z"); // already 15 September in Kyiv
const dom = new JSDOM("<!doctype html><body></body>", {url: "https://ha.example.invalid"});
globalThis.document = dom.window.document;
globalThis.Event = dom.window.Event;
const ipLink = octets => `https://${octets.join(".")}/a`;

function source(id = "OS1", member = "child1") {
  return {
    id, revision: 1, member, member_revision: 1, provider: "respublika", student_id: "101",
    label: id === "OS1" ? "Synthetic school" : "Sibling private school", timezone: "Europe/Kyiv",
    enabled: true, status: "ready", stale: false, last_success: "2026-09-14T21:00:00Z",
    changes: [{kind: "homework", at: "2026-09-14T21:00:00Z"}], acknowledgements: {},
    snapshot: {
      student_id: "101", student_name: "Synthetic learner", timezone: "Europe/Kyiv",
      source_url: "https://school.example.invalid/daybook/101", coverage_start: "2026-09-14", coverage_end: "2026-09-20",
      lessons: [
        {id: "L1", date: "2026-09-15", start: "09:00", end: "09:45", subject: "Science today", teacher: "Synthetic teacher", room: "A",
          topic: "States of matter", homework: "Read the worksheet", estimated_minutes: 20, cancelled: false, replacement: true,
          links: ["https://resource.example.invalid/chapter"], attachments: [{id: "F1", name: "Worksheet.pdf", ext: "pdf", size: 900}], homework_hash: "a".repeat(64)},
        {id: "L2", date: "2026-09-16", start: "10:00", end: "10:45", subject: "Science tomorrow", teacher: "Synthetic teacher", room: "B",
          topic: "Temperature", homework: "Prepare a question", estimated_minutes: null, cancelled: true, replacement: false, links: [], attachments: []},
      ],
      grades: [{id: "G1", date: "2026-09-14", period: "14", subject: "Science", value: "Н/А", kind: "Practice", comment: "Not assessed"},
        {id: "G2", date: null, period: "Semester", subject: "Art", value: "pass", kind: "Term", comment: ""}],
      absences: [{id: "A1", date: "2026-09-14", period: "14", subject: "Science", comment: "Excused"}],
    },
  };
}

function setup(t, role = "parent") {
  const body = document.createElement("div"); document.body.append(body); t.after(() => body.remove());
  const actor = role === "child" ? "child1" : "parent";
  const card = {
    _entry: "synthetic-entry", _generation: 1, _config: {language: "en"}, _hass: {language: "en"},
    _data: {
      actor, role, settings: {modules: ["school"], timezone: "UTC"},
      members: [{id: "parent", role: role === "child" ? "parent" : role, name: "Synthetic parent", active: true, revision: 1},
        {id: "child1", role: "child", name: "Synthetic child", active: true, revision: 1},
        {id: "child2", role: "child", name: "Synthetic sibling", active: true, revision: 1}],
      school: {timetables: [], online: {sources: [source(), source("OS2", "child2")]}}
    },
    render() {body.replaceChildren(); renderOnlineSchool(this, body, NOW);},
  };
  card.render();
  return {card, body};
}

test("source timezone drives today/tomorrow and loaded lesson facts remain literal", t => {
  const {card, body} = setup(t);
  assert.match(body.textContent, /2026-09-16/);
  assert.match(body.textContent, /Science tomorrow/);
  assert.match(body.textContent, /Cancelled lesson/);
  assert.doesNotMatch(body.textContent, /Science today/);
  body.querySelector('[data-online-day="today"]').click();
  assert.equal(card._onlineSchoolDay, "today");
  assert.match(body.textContent, /2026-09-15/);
  assert.match(body.textContent, /Science today/);
  assert.match(body.textContent, /Teacher estimate: 20 min/);
  assert.match(body.textContent, /Replacement reported/);
  assert.match(body.textContent, /not a separate submission deadline/);
});

test("child and selected member contexts never render sibling imports", t => {
  const {card, body} = setup(t, "child");
  assert.equal(body.querySelectorAll(".online-source").length, 1);
  assert.doesNotMatch(body.textContent, /Sibling private school|Synthetic sibling/);
  card._config.member_id = "child2"; card.render();
  assert.equal(body.querySelectorAll(".online-source").length, 0);
  card._data.role = "parent"; card._data.actor = "parent"; card.render();
  assert.equal(body.querySelectorAll(".online-source").length, 1);
  assert.match(body.textContent, /Sibling private school/);
  assert.doesNotMatch(body.textContent, /Synthetic school/);
});

for (const role of ["adult", "guest"]) test(`${role} has no online school UI`, t => {
  const {body} = setup(t, role); assert.equal(body.textContent, "");
});

test("changed member epoch, revoked actor and disabled School fail closed", t => {
  const {card, body} = setup(t);
  card._data.members.find(row => row.id === "child1").revision = 2; card.render();
  assert.equal(body.querySelector('[data-source-id="OS1"]'), null);
  card._data.members[0].active = false; card.render(); assert.equal(body.textContent, "");
  card._data.members[0].active = true; card._data.settings.modules = []; card.render();
  assert.equal(body.textContent, "");
});

test("stale, unknown and outside-coverage states never claim there is no homework", t => {
  const {card, body} = setup(t); const row = card._data.school.online.sources[0];
  card._config.member_id = "child1";
  row.stale = true; row.status = "online_school_timeout"; row.snapshot.coverage_end = "2026-09-15";
  card.render();
  assert.match(body.textContent, /Last-known data/); assert.match(body.textContent, /outside the loaded dates/);
  assert.doesNotMatch(body.textContent, /No homework text|No lessons are listed/);
  row.snapshot = null; row.last_success = null; row.status = "pending"; card.render();
  assert.match(body.textContent, /Waiting for the first sync/); assert.match(body.textContent, /No verified diary/);
});

test("disabled connection shows status, never retained snapshot or links", t => {
  const {card, body} = setup(t); card._config.member_id = "child1";
  card._data.school.online.sources[0].enabled = false; card.render();
  assert.match(body.textContent, /Connection disabled/);
  assert.doesNotMatch(body.textContent, /Science tomorrow|Prepare a question/);
  assert.equal(body.querySelectorAll("a").length, 0);
});

test("external content is text and click-only HTTPS, never image/script fetches or downloads", t => {
  const {card, body} = setup(t); card._config.member_id = "child1"; card._onlineSchoolDay = "today";
  const row = card._data.school.online.sources[0].snapshot.lessons[0];
  row.homework = '<img src="https://evil.example.invalid/track" onerror="alert(1)">';
  row.links.push("javascript:alert(1)", "https://user:pass@example.invalid/a", "http://example.invalid/");
  card.render();
  assert.match(body.textContent, /<img src=/);
  assert.equal(body.querySelectorAll("img,script,iframe,object,input").length, 0);
  const links = [...body.querySelectorAll("a")];
  assert.equal(links.length, 2);
  assert(links.every(a => a.target === "_blank" && a.rel === "noopener noreferrer" && a.referrerPolicy === "no-referrer"));
  assert.match(body.textContent, /Worksheet.pdf · pdf · 900 B/);
  assert.equal(body.querySelectorAll("a[download]").length, 0);
});

for (const value of ["javascript:alert(1)", "https://localhost/a", ipLink([127, 0, 0, 1]), ipLink([10, 1, 1, 1]), ipLink([172, 16, 1, 1]), ipLink([169, 254, 169, 254]), "https://example.invalid/?token=secret", "https://[::1]/"]) test(`unsafe link rejected: ${value}`, () => {
  assert.equal(onlineSchoolSafeLink(value), null);
});

test("stale source, household generation and detached controls cannot navigate or change day", t => {
  const {card, body} = setup(t); const link = body.querySelector("a");
  const button = body.querySelector('[data-online-day="today"]');
  card._generation += 1;
  const event = new Event("click", {cancelable: true}); link.dispatchEvent(event);
  assert.equal(event.defaultPrevented, true); button.click(); assert.equal(card._onlineSchoolDay, undefined);
  card.render(); const old = body.querySelector('[data-online-day="today"]');
  card.render(); old.click(); assert.equal(card._onlineSchoolDay, undefined);
});

test("grades retain nonnumeric marks and period labels; absences are not zero grades", t => {
  const {body} = setup(t);
  assert.match(body.textContent, /Science · Н\/А/); assert.match(body.textContent, /Semester · Art · pass/);
  assert.match(body.textContent, /Reported absences/); assert.match(body.textContent, /Excused/);
  assert.match(body.textContent, /No average or grading scale is inferred/);
  assert.doesNotMatch(body.textContent, /Science · 0/);
});

test("local preparation acknowledgement is shown only for the exact current homework", t => {
  const {card, body} = setup(t); card._config.member_id = "child1"; card._onlineSchoolDay = "today";
  const row = card._data.school.online.sources[0];
  row.acknowledgements.L1 = {done: true, homework_hash: "a".repeat(64), member_revision: 1}; card.render();
  assert.match(body.textContent, /prepared locally; not submitted/);
  row.snapshot.lessons[0].homework_hash = "b".repeat(64); card.render();
  assert.doesNotMatch(body.textContent, /prepared locally; not submitted/);
});

test("all three locales have exact key parity and owner-only setup guidance", t => {
  for (const language of ["en", "ru", "uk"]) {
    assert.deepEqual(Object.keys(ONLINE_SCHOOL_COPY[language]).sort(), Object.keys(ONLINE_SCHOOL_COPY.en).sort());
    const {card, body} = setup(t, "owner"); card._config.language = language; card.render();
    assert(body.textContent.includes(ONLINE_SCHOOL_COPY[language].title));
    assert(body.textContent.includes(ONLINE_SCHOOL_COPY[language].setup));
    assert.equal(body.querySelectorAll("input[type=password]").length, 0);
  }
});

test("online-school block is integrated after native actor authorization", t => {
  const {card, body} = setup(t, "child"); body.replaceChildren();
  renderSchool(card, body);
  assert.equal(body.firstElementChild.className, "online-school");
  card._data.role = "guest"; body.replaceChildren(); renderSchool(card, body);
  assert.equal(body.querySelector(".online-school"), null);
});

test("rendering imported facts never calls any write or network API", t => {
  const {card, body} = setup(t);
  card._command = () => assert.fail("read-only view invoked a write");
  card._hass.callWS = () => assert.fail("read-only view invoked an API");
  card.render(); body.querySelector('[data-online-day="today"]').click();
  assert(body.querySelector(".online-school"));
});

test("long assignment links use bounded readable labels without changing the full destination", t => {
  const {card, body} = setup(t); card._config.member_id = "child1"; card._onlineSchoolDay = "today";
  const href = "https://resource.example.invalid/" + "chapter-".repeat(30) + "?part=2&mode=read";
  card._data.school.online.sources[0].snapshot.lessons[0].links = [href]; card.render();
  const anchor = body.querySelector(".online-assignment-link");
  assert.equal(anchor.getAttribute("href"), href);
  assert.equal(anchor.title, href);
  assert(anchor.textContent.startsWith("resource.example.invalid/chapter-"));
  assert(anchor.textContent.length <= 80);
  assert(anchor.textContent.endsWith("…"));
});
