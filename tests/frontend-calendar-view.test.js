import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost" });
for (const k of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData", "Option"]) {
  globalThis[k] = dom.window[k];
}

const { CALENDAR_COPY, renderCalendar } = await import(
  "../custom_components/family_assistant/frontend/calendar-view.js"
);
const { makeRecurrenceDraft } = await import("../custom_components/family_assistant/frontend/recurrence-form.js");

function createMockCard({
  role = "parent",
  actor = "p1",
  timezone = "UTC",
  lang = "en",
  members = [
    { id: "p1", name: "Parent One", role: "parent", active: true },
    { id: "c1", name: "Child One", role: "child", active: true },
    { id: "g1", name: "Guest One", role: "guest", active: true },
  ],
  calendar = {
    config: { publish_to_ha: false, revision: 1 },
    events: [],
    occurrences: [],
  },
  modules = ["calendar"],
} = {}) {
  const commands = [];
  const card = {
    _generation: 1,
    _data: {
      role,
      actor,
      settings: { timezone, modules },
      members,
      calendar,
    },
    _config: { language: lang },
    _hass: { language: lang, config: { time_zone: timezone } },
    parent: ["owner", "parent"].includes(role),
    _writing: false,
    _calendarDraft: null,
    _actionError: null,
    commands,
    button(text, action, primary = false) {
      const btn = document.createElement("button");
      btn.textContent = text;
      if (primary) btn.className = "primary";
      btn.type = "button";
      btn.disabled = Boolean(card._writing);
      btn.addEventListener("click", action);
      return btn;
    },
    input(form, name, label, type = "text", value = "", required = true) {
      const wrap = document.createElement("label");
      wrap.textContent = label;
      const input = document.createElement("input");
      Object.assign(input, { name, type, value, required });
      wrap.append(input);
      form.append(wrap);
      return input;
    },
    async command(action, payload) {
      commands.push({ action, payload });
      return { success: true };
    },
    render() {},
  };
  return card;
}

test("Recurring edit keeps normalized rule and task links with fresh participant validation", () => {
  const rule = {frequency:"weekly",interval:3,start_date:"2026-09-07",time:"00:00",timezone:"UTC",weekdays:[0,3],month_day:22,until:"2027-01-01",exceptions:["2026-09-28"],catchup_hours:48};
  const event = {id:"E000099",revision:5,title:"Synthetic event",all_day:true,start:"2026-09-07",end:"2026-09-08",timezone:"UTC",rule,participants:["c1"],task_ids:["T000099"],creator:"p1",status:"confirmed",visibility:"family"};
  const card = createMockCard({calendar:{events:[event],occurrences:[],config:{revision:0}}});
  card._data.tasks = [{id:"T000099",title:"Synthetic task",assignee:"c1"}];
  card._calendarDraft = {...structuredClone(event),type:"edit",start_date:event.start,end_date:event.end};
  const body = document.createElement("div");document.body.append(body);
  renderCalendar(card,body);
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.equal(card.commands.length,1);
  assert.deepEqual(card.commands[0].payload.rule,rule);
  assert.deepEqual(card.commands[0].payload.task_ids,["T000099"]);
  const frozen = structuredClone(card.commands[0].payload);
  card._calendarDraft.recurrence.interval = "4";
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.deepEqual(card.commands[1].payload,frozen);

  card._calendarDraft = {...structuredClone(event),type:"edit",start_date:event.start,end_date:event.end};
  body.replaceChildren();renderCalendar(card,body);
  card._data.tasks[0].assignee = "p1";
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.equal(card.commands.length,2,"Cannot link task reassigned outside event participants");
});

test("Calendar recurrence follows edited clock, rejects fold seconds and never converts one-off silently",()=>{
  const card=createMockCard({timezone:"Europe/Helsinki"});
  const body=document.createElement("div");document.body.append(body);
  const base={type:"create",title:"Synthetic repeating event",all_day:false,start_local:"2026-09-07T09:35",end_local:"2026-09-07T10:35",timezone:"Europe/Helsinki",participants:["p1"]};
  card._calendarDraft={...base,recurrence:makeRecurrenceDraft({frequency:"weekly",interval:1,start_date:"2026-09-01",time:"01:00",timezone:"UTC",weekdays:[0],month_day:1,exceptions:[],catchup_hours:24,until:null})};
  renderCalendar(card,body);
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.equal(card.commands.length,1);
  assert.equal(card.commands[0].payload.rule.start_date,"2026-09-07");
  assert.equal(card.commands[0].payload.rule.time,"09:35");
  assert.equal(card.commands[0].payload.rule.timezone,"Europe/Helsinki");
  card._calendarDraft={...base,start_local:"2026-10-25T03:30",end_local:"2026-10-25T04:30",start_fold:"1",end_fold:"0",recurrence:makeRecurrenceDraft(card.commands[0].payload.rule)};
  body.replaceChildren();renderCalendar(card,body);
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.equal(card.commands.length,1,"Second folded start is not valid for a repeated series");
  card._calendarDraft.recurrence.enabled=false;
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.equal(card.commands.length,2);
  assert.equal(card.commands[1].payload.rule,null);
});

test("1. CALENDAR_COPY RU UK EN key parity and non-empty values", () => {
  const enKeys = Object.keys(CALENDAR_COPY.en).sort();
  const ruKeys = Object.keys(CALENDAR_COPY.ru).sort();
  const ukKeys = Object.keys(CALENDAR_COPY.uk).sort();
  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys");
  for (const k of enKeys) {
    assert.ok(typeof CALENDAR_COPY.en[k] === "string" && CALENDAR_COPY.en[k].length > 0);
    assert.ok(typeof CALENDAR_COPY.ru[k] === "string" && CALENDAR_COPY.ru[k].length > 0);
    assert.ok(typeof CALENDAR_COPY.uk[k] === "string" && CALENDAR_COPY.uk[k].length > 0);
  }
});

test("2. Unsafe user text rendered as text and guest/disabled calendar safety", () => {
  const hostileEvent = {
    id: "e1",
    revision: 1,
    title: "<script>alert(1)</script>",
    description: "<img src=x onerror=alert(1)>",
    location: "<b>Room</b>",
    all_day: true,
    start: "2026-09-07",
    end: "2026-09-08",
    timezone: "UTC",
    status: "confirmed",
    creator: "p1",
    participants: ["p1"],
    visibility: "family",
  };
  const card = createMockCard({
    role: "parent",
    calendar: { config: { publish_to_ha: false, revision: 1 }, events: [hostileEvent], occurrences: [] },
  });
  const body = document.createElement("div");
  renderCalendar(card, body);
  assert.equal(body.querySelector("script"), null);
  assert.equal(body.querySelector("img"), null);
  assert.equal(body.querySelector("b"), null);
  assert.ok(body.textContent.includes("<script>alert(1)</script>"));

  // Guest role produces no controls
  const guestBody = document.createElement("div");
  renderCalendar(createMockCard({ role: "guest" }), guestBody);
  assert.equal(guestBody.children.length, 0);

  // Missing calendar module produces no controls
  const noModuleBody = document.createElement("div");
  renderCalendar(createMockCard({ modules: [] }), noModuleBody);
  assert.equal(noModuleBody.children.length, 0);
});

test("3. Agenda display and draft survival across render", () => {
  const occ = {
    id: "occ1",
    event_id: "e1",
    title: "Dentist Visit",
    start: "2026-09-10T10:00:00Z",
    end: "2026-09-10T11:00:00Z",
    all_day: false,
    timezone: "UTC",
    location: "Clinic",
    status: "confirmed",
  };
  const card = createMockCard({
    calendar: { config: { publish_to_ha: false, revision: 1 }, events: [], occurrences: [occ] },
  });
  const body = document.createElement("div");
  renderCalendar(card, body);
  assert.ok(body.textContent.includes("Dentist Visit"));
  assert.ok(body.textContent.includes("Clinic"));

  // Open edit draft
  card._calendarDraft = {
    type: "create",
    title: "Draft Event Title",
    all_day: true,
    start_date: "2026-09-15",
    end_date: "2026-09-16",
    timezone: "UTC",
  };
  body.replaceChildren();
  renderCalendar(card, body);
  const titleInput = body.querySelector('input[name="title"]');
  assert.ok(titleInput);
  assert.equal(titleInput.value, "Draft Event Title");
});

test("4. Stale actor, role, or revision rejection", () => {
  const ev = { id: "e1", revision: 2, title: "Meeting", start: "2026-09-10", end: "2026-09-11", all_day: true, timezone: "UTC", status: "confirmed", creator: "p1" };
  const card = createMockCard({
    role: "parent",
    calendar: { config: { publish_to_ha: false, revision: 1 }, events: [ev], occurrences: [] },
  });
  card._calendarDraft = {
    type: "edit",
    id: "e1",
    revision: 1, // Stale revision (card has revision 2)
    title: "Updated Meeting",
    all_day: true,
    start_date: "2026-09-10",
    end_date: "2026-09-11",
    timezone: "UTC",
  };
  const body = document.createElement("div");
  renderCalendar(card, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0);
  assert.equal(card._actionError, "conflict");
  assert.equal(card._calendarDraft, null);
});

test("5. Strict date/time order and date-only exclusive end date enforcement", () => {
  const card = createMockCard({ role: "parent" });
  card._calendarDraft = {
    type: "create",
    title: "Day Off",
    participants: ["p1"],
    all_day: true,
    start_date: "2026-09-10",
    end_date: "2026-09-10", // Equal end date should be rejected (must be strictly > start_date)
    timezone: "UTC",
  };
  const body = document.createElement("div");
  renderCalendar(card, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0); // Blocked

  // Fix end date to exclusive next day
  const endInput = body.querySelector('input[name="end_date"]');
  endInput.value = "2026-09-11";
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.equal(card.commands[0].action, "calendar.save");
  assert.equal(card.commands[0].payload.start, "2026-09-10");
  assert.equal(card.commands[0].payload.end, "2026-09-11");
});

test("6. DST gap rejected and fold choice for ambiguous time", () => {
  // In Europe/Helsinki, 2026-03-29 03:30:00 does not exist (clocks jump from 03:00 to 04:00)
  const card = createMockCard({ timezone: "Europe/Helsinki" });
  card._calendarDraft = {
    type: "create",
    title: "DST Gap Event",
    participants: ["p1"],
    all_day: false,
    start_local: "2026-03-29T03:30",
    end_local: "2026-03-29T04:30",
    timezone: "Europe/Helsinki",
  };
  const body = document.createElement("div");
  renderCalendar(card, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0); // Non-existent local time rejected

  // Ambiguous time: 2026-10-25 03:30 occurs twice in Europe/Helsinki
  card._calendarDraft = {
    type: "create",
    title: "DST Fold Event",
    participants: ["p1"],
    all_day: false,
    start_local: "2026-10-25T03:30",
    end_local: "2026-10-25T04:30",
    start_fold: "1", // Second occurrence chosen
    end_fold: "0",
    timezone: "Europe/Helsinki",
  };
  body.replaceChildren();
  renderCalendar(card, body);
  const foldForm = body.querySelector("form");
  foldForm.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.equal(card.commands[0].action, "calendar.save");
  assert.ok(card.commands[0].payload.start.includes("2026-10-25"));
});

test("7. Child role cannot approve events and tentative event approval workflow", () => {
  const tentativeEvent = {
    id: "e_tent",
    revision: 1,
    title: "Kid Party",
    start: "2026-09-12",
    end: "2026-09-13",
    all_day: true,
    timezone: "UTC",
    status: "tentative",
    creator: "c1",
    participants: ["c1"],
    visibility: "family",
  };
  // Child viewing
  const childCard = createMockCard({
    role: "child",
    actor: "c1",
    calendar: { config: { publish_to_ha: false, revision: 1 }, events: [tentativeEvent], occurrences: [] },
  });
  const childBody = document.createElement("div");
  renderCalendar(childCard, childBody);
  const childButtons = Array.from(childBody.querySelectorAll("button")).map((b) => b.textContent);
  assert.ok(!childButtons.includes(CALENDAR_COPY.en.approve), "Child must not see Approve button");

  // Parent viewing and approving
  const parentCard = createMockCard({
    role: "parent",
    actor: "p1",
    calendar: { config: { publish_to_ha: false, revision: 1 }, events: [tentativeEvent], occurrences: [] },
  });
  parentCard._calendarDraft = {
    type: "approve",
    id: "e_tent",
    revision: 1,
    reason: "Approved by parent",
  };
  const parentBody = document.createElement("div");
  renderCalendar(parentCard, parentBody);
  const approveForm = parentBody.querySelector("form");
  approveForm.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(parentCard.commands.length, 1);
  assert.deepEqual(parentCard.commands[0], {
    action: "calendar.approve",
    payload: { id: "e_tent", revision: 1, reason: "Approved by parent" },
  });
});

test("8. Owner export configuration requires explicit public visibility confirmation", () => {
  const ownerCard = createMockCard({
    role: "owner",
    actor: "p1",
    calendar: { config: { publish_to_ha: false, revision: 2 }, events: [], occurrences: [] },
  });
  const body = document.createElement("div");
  // Open publish config draft enabling publish without checking confirmation box
  ownerCard._calendarDraft = {
    type: "publish_config",
    publish_to_ha: true,
    confirm_public_visibility: false,
    revision: 2,
  };
  renderCalendar(ownerCard, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(ownerCard.commands.length, 0);
  assert.equal(ownerCard._actionError, "confirmation_required");
  assert.equal(ownerCard._calendarDraft.frozenPayload, undefined);

  // Now test with confirmation checked
  ownerCard.commands.length = 0;
  ownerCard._calendarDraft = {
    type: "publish_config",
    publish_to_ha: true,
    confirm_public_visibility: true,
    revision: 2,
  };
  body.replaceChildren();
  renderCalendar(ownerCard, body);
  const confirmedForm = body.querySelector("form");
  confirmedForm.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(ownerCard.commands.length, 1);
  assert.deepEqual(ownerCard.commands[0], {
    action: "calendar.configure",
    payload: { publish_to_ha: true, revision: 2, confirm_public_visibility: true },
  });
});

test("9. Exact retry payload preserved across failed actions", () => {
  const card = createMockCard({ role: "parent" });
  card._data.calendar.events.push({id:"e1", revision:1, creator:"p1", status:"confirmed", title:"Synthetic event", all_day:true, start:"2026-09-06", end:"2026-09-07"});
  const frozenPayload = {
    id: "e1",
    revision: 1,
    reason: "Severe weather cancellation",
  };
  card._actionError = "network_timeout";
  card._calendarDraft = {
    type: "cancel",
    id: "e1",
    revision: 1,
    reason: "Severe weather cancellation",
    frozenPayload,
  };
  const body = document.createElement("div");
  renderCalendar(card, body);
  const retryBtn = Array.from(body.querySelectorAll("button")).find(
    (b) => b.textContent === CALENDAR_COPY.en.retry
  );
  assert.ok(retryBtn, "Retry button must be present when frozen and action error exists");
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], {
    action: "calendar.cancel",
    payload: frozenPayload,
  });
});

test("10. No implicit fold selection; malformed reminders are not silently dropped", () => {
  const card=createMockCard({timezone:"Europe/Kyiv"});
  card._calendarDraft={type:"create",title:"Synthetic event",participants:["p1"],
    start_local:"2026-10-25T03:30",end_local:"2026-10-25T04:30",timezone:"Europe/Kyiv"};
  const body=document.createElement("div");renderCalendar(card,body);
  const submit=()=>body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  submit();assert.equal(card.commands.length,0);assert.match(body.textContent,/Choose one/);
  body.querySelector('[name="start_fold"]').value="1";
  body.querySelector('[name="reminders"]').value="15, banana, 3.5";
  submit();assert.equal(card.commands.length,0);
  body.querySelector('[name="reminders"]').value="15";
  submit();assert.equal(card.commands.length,1);
  assert.equal(card.commands[0].payload.start,"2026-10-25T01:30:00.000Z");
});

test("11. Actor, role, entry and timezone changes invalidate drafts after re-render",()=>{
  for(const change of [c=>c._data.actor="c1",c=>c._data.role="child",c=>c._entry="other",c=>c._data.settings.timezone="Europe/Kyiv"]){
    const card=createMockCard();card._calendarDraft={type:"create",title:"Old private draft",participants:["p1"]};
    const body=document.createElement("div");renderCalendar(card,body);change(card);
    body.replaceChildren();renderCalendar(card,body);
    assert.equal(card._calendarDraft,null);assert.equal(card.commands.length,0);
    assert.doesNotMatch(body.textContent,/Old private draft/);
  }
});

test("12. Existing offset and seconds survive an unchanged time edit",()=>{
  const ev={id:"e1",creator:"p1",revision:1,title:"Synthetic event",timezone:"Europe/Kyiv",status:"confirmed",participants:["p1"],start:"2026-10-25T03:30:15+02:00",end:"2026-10-25T04:30:45+02:00"};
  const card=createMockCard({calendar:{events:[ev],occurrences:[],config:{revision:0,publish_to_ha:false}}});
  const body=document.createElement("div");renderCalendar(card,body);
  [...body.querySelectorAll("button")].find(b=>b.textContent==="Edit").click();
  body.replaceChildren();renderCalendar(card,body);
  body.querySelector('[name="title"]').value="Renamed";
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.equal(card.commands.length,1);assert.equal(card.commands[0].payload.start,ev.start);
  assert.equal(card.commands[0].payload.end,ev.end);
});
