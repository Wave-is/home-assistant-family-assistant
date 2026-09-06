import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost" });
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const { COURT_COPY, renderCourt } = await import(
  "../custom_components/family_assistant/frontend/court-view.js"
);
await import(
  "../custom_components/family_assistant/frontend/family-assistant.js"
);

function createMockCard({
  role = "parent",
  actor = "p1",
  timezone = "UTC",
  lang = "en",
  members = [
    { id: "owner1", name: "Owner One", role: "owner", active: true },
    { id: "p1", name: "Parent One", role: "parent", active: true },
    { id: "p2", name: "Parent Two", role: "parent", active: true },
    { id: "c1", name: "Child One", role: "child", active: true },
    { id: "g1", name: "Guest One", role: "guest", active: true },
  ],
  court = [],
  court_summary = null,
  court_config = {
    weekly_enabled: false,
    weekday: 0,
    time: "00:00",
    second_adult_review: false,
    revision: 1,
  },
  court_reports = [],
  commandFn = null,
} = {}) {
  const commands = [];
  const card = {
    _view: "court",
    _generation: 1,
    _data: {
      role,
      actor,
      settings: { timezone, modules: ["court"] },
      members,
      court,
      court_summary,
      court_config,
      court_reports,
    },
    _config: { language: lang },
    _hass: { language: lang, config: { time_zone: timezone } },
    parent: ["owner", "parent"].includes(role),
    _writing: false,
    _courtAction: null,
    _courtDraft: null,
    _courtConfigOpen: false,
    _actionError: null,
    commands,
    commandFn,
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
    memberSelect(form) {
      const wrap = document.createElement("label");
      wrap.textContent = "Assignee";
      const select = document.createElement("select");
      select.name = "member";
      for (const m of card._data.members.filter(m => m.active && m.role !== "guest")) {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.name;
        select.append(opt);
      }
      wrap.append(select);
      form.append(wrap);
      return select;
    },
    async command(action, payload) {
      commands.push({ action, payload });
      if (card.commandFn) await card.commandFn(action, payload);
      return { success: true };
    },
    render() {},
  };
  return card;
}

test("COURT_COPY exact key parity across en, ru, and uk", () => {
  const enKeys = Object.keys(COURT_COPY.en).sort();
  const ruKeys = Object.keys(COURT_COPY.ru).sort();
  const ukKeys = Object.keys(COURT_COPY.uk).sort();

  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys exactly");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys exactly");

  for (const k of enKeys) {
    assert.equal(typeof COURT_COPY.en[k], "string");
    assert.equal(typeof COURT_COPY.ru[k], "string");
    assert.equal(typeof COURT_COPY.uk[k], "string");
    assert.ok(COURT_COPY.en[k].length > 0);
    assert.ok(COURT_COPY.ru[k].length > 0);
    assert.ok(COURT_COPY.uk[k].length > 0);
  }
});

test("automatic penalty includes the visible task reference and original title safely", () => {
  const card = createMockCard({court:[{id:"task:T1",member:"c1",points:-1,status:"active",reason_key:"task_missed",reason_data:{task_id:"T1"}}]});
  card._data.tasks=[{id:"T1",title:"<img src=x> Synthetic task"}];
  const body=document.createElement("div");renderCourt(card,body);
  assert.ok(body.textContent.includes("Task was not completed by its deadline · T1 · <img src=x> Synthetic task"));
  assert.equal(body.querySelector("img"),null);
});

test("resolved and previous appeals keep the original request and decision visible", () => {
  const prior={actor:"c1",at:"2026-09-01T08:00:00Z",reason:"First request",status:"resolved",decision:"uphold",resolution:{actor:"p2",at:"2026-09-01T09:00:00Z",reason:"First decision"}};
  const card=createMockCard({court:[{id:"C1",member:"c1",points:-1,reason:"Original score",status:"reversed",actor:"p1",previous_appeals:[prior],appeal:{...prior,reason:"Second request",decision:"reverse",resolution:{...prior.resolution,reason:"Second decision"}}}]});
  const body=document.createElement("div");renderCourt(card,body);
  for(const reason of ["Original score","First request","First decision","Second request","Second decision"])assert.ok(body.textContent.includes(reason));
  assert.ok(body.querySelector("details").textContent.includes("Previous appeals (1)"));
});

test("renders weekly summary rows with friendly names and household timezone", () => {
  const card = createMockCard({
    court_summary: {
      start: "2026-09-01T00:00:00Z",
      end: "2026-09-08T00:00:00Z",
      timezone: "UTC",
      rows: [
        {
          member: "c1",
          active_positives: 15,
          active_negatives: -5,
          total: 10,
          active_count: 2,
          reversed_count: 1,
        },
      ],
      events: ["C1"],
    },
  });

  const body = document.createElement("div");
  renderCourt(card, body);

  const text = body.textContent;
  assert.ok(text.includes(COURT_COPY.en.weekly_summary));
  assert.ok(text.includes("Child One"));
  assert.ok(text.includes("+15"));
  assert.ok(text.includes("-5"));
  assert.ok(text.includes("+10"));
  assert.ok(text.includes(`${COURT_COPY.en.reversed_count}: 1`));
});

test("renders prior court_reports using each report's timezone", () => {
  const card = createMockCard({
    court_reports: [
      {
        id: "2026-08-25T00:00:00Z/2026-09-01T00:00:00Z",
        start: "2026-08-25T00:00:00Z",
        end: "2026-09-01T00:00:00Z",
        timezone: "America/New_York",
        rows: [
          {
            member: "c1",
            active_positives: 20,
            active_negatives: 0,
            total: 20,
            active_count: 1,
            reversed_count: 0,
          },
        ],
      },
    ],
  });

  const body = document.createElement("div");
  renderCourt(card, body);

  const text = body.textContent;
  assert.ok(text.includes(COURT_COPY.en.reports_title));
  assert.ok(text.includes("America/New_York"));
  assert.ok(text.includes("Child One"));
});

test("automatic penalty record localization: reason_key and source localized without raw keys", () => {
  const penaltyRecord = {
    id: "task:T123",
    member: "c1",
    points: -2,
    reason_key: "task_missed",
    reason_data: { task_id: "T123" },
    actor: "system",
    source: "task",
    status: "active",
    created_at: "2026-09-05T10:00:00Z",
    revision: 1,
  };

  const card = createMockCard({
    court: [penaltyRecord],
  });

  const body = document.createElement("div");
  renderCourt(card, body);

  const text = body.textContent;
  assert.ok(text.includes(COURT_COPY.en.reason_task_missed));
  assert.ok(text.includes(COURT_COPY.en.source_task));
  assert.ok(text.includes(COURT_COPY.en.source_system));
  assert.ok(!text.includes("undefined"));
  assert.ok(!text.includes("task_missed"));
});

test("XSS prevention: user input, reasons, and names inserted via textContent only", () => {
  const hostileRecord = {
    id: "C_XSS",
    revision: 1,
    member: "c1",
    points: 10,
    reason: '<script>alert("xss")</script><img src=x onerror=alert(1)>',
    actor: "p1",
    status: "active",
    source: "<b>manual</b>",
    created_at: "2026-09-01T12:00:00Z",
  };

  const card = createMockCard({
    court: [hostileRecord],
  });

  const body = document.createElement("div");
  renderCourt(card, body);

  assert.equal(body.querySelectorAll("script").length, 0);
  assert.equal(body.querySelectorAll("img").length, 0);
  assert.equal(body.querySelectorAll("b").length, 0);
  assert.ok(body.textContent.includes('<script>alert("xss")</script>'));
});

test("permissions: guests cannot make any changes or see award/appeal/reverse buttons", () => {
  const record = {
    id: "C1",
    revision: 1,
    member: "g1",
    points: 5,
    reason: "Good helper",
    actor: "p1",
    status: "active",
  };

  const guestCard = createMockCard({
    role: "guest",
    actor: "g1",
    court: [record],
  });

  const body = document.createElement("div");
  renderCourt(guestCard, body);

  const buttons = body.querySelectorAll("button");
  assert.equal(buttons.length, 0);
});

test("draft input persistence across renders and mixed form regression check", () => {
  const record = {
    id: "C1",
    revision: 1,
    member: "c1",
    points: 5,
    reason: "Test",
    actor: "p1",
    status: "active",
  };

  const card = createMockCard({
    role: "owner",
    actor: "owner1",
    court: [record],
  });

  const body = document.createElement("div");
  renderCourt(card, body);

  // Open award form and type inputs
  const awardBtn = Array.from(body.querySelectorAll("button")).find(
    b => b.textContent === COURT_COPY.en.award_title
  );
  awardBtn.click();

  body.replaceChildren();
  renderCourt(card, body);

  const rInput = body.querySelector('input[name="reason"]');
  rInput.value = "Great job with homework";
  rInput.dispatchEvent(new dom.window.Event("input"));

  // Check draft was preserved on card
  assert.equal(card._courtDraft.reason, "Great job with homework");

  // Re-render: input value survives rerender without being wiped
  body.replaceChildren();
  renderCourt(card, body);

  const rInputAfter = body.querySelector('input[name="reason"]');
  assert.equal(rInputAfter.value, "Great job with homework");

  // Open ledger appeal form: must close award form (only one active edit form)
  const appealBtn = Array.from(body.querySelectorAll("button")).find(
    b => b.textContent === COURT_COPY.en.appeal
  );
  appealBtn.click();

  body.replaceChildren();
  renderCourt(card, body);

  assert.equal(card._courtDraft, null);
  assert.ok(card._courtAction);
  assert.equal(card._courtAction.type, "appeal");
});

test("child can appeal own active record; cannot reverse or resolve", () => {
  const record = {
    id: "C2",
    revision: 2,
    member: "c1",
    points: -10,
    reason: "Forgot chores",
    actor: "p1",
    status: "active",
  };

  const childCard = createMockCard({
    role: "child",
    actor: "c1",
    court: [record],
  });

  const body = document.createElement("div");
  renderCourt(childCard, body);

  const buttons = Array.from(body.querySelectorAll("button")).map(b => b.textContent);
  assert.ok(buttons.includes(COURT_COPY.en.appeal));
  assert.ok(!buttons.includes(COURT_COPY.en.reverse));
  assert.ok(!buttons.includes(COURT_COPY.en.resolve_appeal));

  const appealBtn = Array.from(body.querySelectorAll("button")).find(
    b => b.textContent === COURT_COPY.en.appeal
  );
  appealBtn.click();

  body.replaceChildren();
  renderCourt(childCard, body);

  const form = body.querySelector("form");
  assert.ok(form);
  const reasonInput = form.querySelector('input[name="reason"]');
  reasonInput.value = "I had soccer practice";

  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));

  assert.equal(childCard.commands.length, 1);
  assert.deepEqual(childCard.commands[0], {
    action: "court.appeal",
    payload: {
      id: "C2",
      revision: 2,
      reason: "I had soccer practice",
    },
  });
});

test("policy second_adult_review: original record author or appellant parent sees explanation instead of actionable button", () => {
  const recordWithAppeal = {
    id: "C3",
    revision: 3,
    member: "c1",
    points: -20,
    reason: "Broken glass",
    actor: "p1",
    status: "active",
    appeal: {
      status: "pending",
      actor: "c1",
      reason: "It was an accident",
      at: "2026-09-02T10:00:00Z",
    },
  };

  const authorCard = createMockCard({
    role: "parent",
    actor: "p1",
    court: [recordWithAppeal],
    court_config: {
      weekly_enabled: true,
      weekday: 0,
      time: "00:00",
      second_adult_review: true,
      revision: 1,
    },
  });

  const bodyAuthor = document.createElement("div");
  renderCourt(authorCard, bodyAuthor);

  assert.ok(bodyAuthor.textContent.includes(COURT_COPY.en.second_adult_review_notice));
  const authorButtons = Array.from(bodyAuthor.querySelectorAll("button")).map(b => b.textContent);
  assert.ok(!authorButtons.includes(COURT_COPY.en.resolve_appeal));
  assert.ok(!authorButtons.includes(COURT_COPY.en.reverse));

  const reviewerCard = createMockCard({
    role: "parent",
    actor: "p2",
    court: [recordWithAppeal],
    court_config: {
      weekly_enabled: true,
      weekday: 0,
      time: "00:00",
      second_adult_review: true,
      revision: 1,
    },
  });

  const bodyReviewer = document.createElement("div");
  renderCourt(reviewerCard, bodyReviewer);

  const reviewerButtons = Array.from(bodyReviewer.querySelectorAll("button")).map(b => b.textContent);
  assert.ok(reviewerButtons.includes(COURT_COPY.en.resolve_appeal));
});

test("refreshed-but-not-rerendered revision/policy reevaluation blocks stale DOM submission", () => {
  const recordWithAppeal = {
    id: "C3",
    revision: 3,
    member: "c1",
    points: -20,
    reason: "Broken glass",
    actor: "p1",
    status: "active",
    appeal: {
      status: "pending",
      actor: "c1",
      reason: "It was an accident",
    },
  };

  // Initially author p1 had no second_adult_review
  const card = createMockCard({
    role: "parent",
    actor: "p1",
    court: [recordWithAppeal],
    court_config: {
      second_adult_review: false,
      revision: 1,
    },
  });

  const body = document.createElement("div");
  renderCourt(card, body);

  const resolveBtn = Array.from(body.querySelectorAll("button")).find(
    b => b.textContent === COURT_COPY.en.resolve_appeal
  );
  assert.ok(resolveBtn);
  resolveBtn.click();

  body.replaceChildren();
  renderCourt(card, body);

  const form = body.querySelector("form");
  const rInput = form.querySelector('input[name="reason"]');
  rInput.value = "Pardoned";

  // Simulate refresh: server state now enabled second_adult_review without rerendering this form yet
  card._data.court_config.second_adult_review = true;

  // Form submit should reevaluate live policy and reject dispatching command
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0);
  assert.equal(card._courtAction, null);
});

test("real customElement async failed retry test with stable operation IDs", async () => {
  const cardEl = document.createElement("family-court-card");
  const executed = [];
  const record = {
    id: "C99",
    revision: 1,
    member: "c1",
    points: 10,
    reason: "Testing",
    actor: "p1",
    status: "active",
  };

  cardEl._hass = {
    language: "en",
    config: { time_zone: "UTC" },
    callWS: async (msg) => {
      if (msg.type === "family_assistant/view") {
        return {
          role: "parent",
          actor: "p1",
          settings: { name: "Test Family", timezone: "UTC", modules: ["court"] },
          members: [
            { id: "p1", name: "Parent One", role: "parent", active: true },
            { id: "c1", name: "Child One", role: "child", active: true },
          ],
          court: [record],
        };
      }
      if (msg.type === "family_assistant/execute") {
        executed.push(msg);
        if (executed.length === 1) {
          const err = new Error("Conflict");
          err.code = "storage_conflict";
          throw err;
        }
        return { accepted: true };
      }
      return {};
    },
  };

  cardEl.setConfig({ view: "court", entry_id: "entry_1" });
  await new Promise(resolve => setTimeout(resolve, 0));

  const shadow = cardEl.shadowRoot;
  assert.ok(shadow);

  // Trigger court.reverse
  const reverseBtn = Array.from(shadow.querySelectorAll("button")).find(
    b => b.textContent === COURT_COPY.en.reverse
  );
  assert.ok(reverseBtn);
  reverseBtn.click();

  const form = shadow.querySelector("form");
  assert.ok(form);
  const rInput = form.querySelector('input[name="reason"]');
  rInput.value = "Cancel test";

  // First submit (will fail with storage_conflict)
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await new Promise(resolve => setTimeout(resolve, 10));

  assert.equal(executed.length, 1);
  const opId1 = executed[0].operation_id;
  assert.ok(opId1);

  // Retry submit: should reuse same pending operation ID and exact payload
  const retryForm = shadow.querySelector("form");
  assert.ok(retryForm);
  retryForm.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await new Promise(resolve => setTimeout(resolve, 10));

  assert.equal(executed.length, 2);
  assert.equal(executed[1].operation_id, opId1);
  assert.deepEqual(executed[1].payload, executed[0].payload);
});
