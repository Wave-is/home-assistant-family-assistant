import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost" });
for (const k of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[k] = dom.window[k];
}

const { REWARD_COPY, renderRewards } = await import(
  "../custom_components/family_assistant/frontend/rewards-view.js"
);

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
  rewards = { catalog: [], requests: [], balances: [] },
  modules = ["court"],
} = {}) {
  const commands = [];
  const card = {
    _generation: 1,
    _data: {
      role,
      actor,
      settings: { timezone, modules },
      members,
      rewards,
    },
    _config: { language: lang },
    _hass: { language: lang, config: { time_zone: timezone } },
    parent: ["owner", "parent"].includes(role),
    _writing: false,
    _rewardDraft: null,
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
      return { success: true };
    },
    render() {},
  };
  return card;
}

test("1. REWARD_COPY exact RU UK EN key parity and valid non-empty strings", () => {
  const enKeys = Object.keys(REWARD_COPY.en).sort();
  const ruKeys = Object.keys(REWARD_COPY.ru).sort();
  const ukKeys = Object.keys(REWARD_COPY.uk).sort();
  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys");
  for (const k of enKeys) {
    assert.ok(typeof REWARD_COPY.en[k] === "string" && REWARD_COPY.en[k].length > 0);
    assert.ok(typeof REWARD_COPY.ru[k] === "string" && REWARD_COPY.ru[k].length > 0);
    assert.ok(typeof REWARD_COPY.uk[k] === "string" && REWARD_COPY.uk[k].length > 0);
  }
});

test("2. XSS prevention and anonymous/guest/disabled-court safety", () => {
  const hostile = { id: "cat1", revision: 1, name: "<script>alert(1)</script>", description: "<img src=x onerror=alert(1)>", cost: 10, enabled: true };
  const card = createMockCard({ role: "parent", rewards: { catalog: [hostile], requests: [], balances: [] } });
  const body = document.createElement("div");
  renderRewards(card, body);
  assert.equal(body.querySelector("script"), null);
  assert.equal(body.querySelector("img"), null);
  assert.ok(body.textContent.includes("<script>alert(1)</script>"));

  // Guest or missing court module produces no controls
  const guestBody = document.createElement("div");
  renderRewards(createMockCard({ role: "guest" }), guestBody);
  assert.equal(guestBody.children.length, 0);

  const noCourtBody = document.createElement("div");
  renderRewards(createMockCard({ modules: [] }), noCourtBody);
  assert.equal(noCourtBody.children.length, 0);
});

test("3. Role projection: child sees only own projection, parent sees all", () => {
  const b1 = { member: "p1", earned: 50, reserved: 0, spent: 10, net: 40, available: 40 };
  const b2 = { member: "c1", earned: -5, reserved: 10, spent: 5, net: -20, available: 0 };
  const r1 = { id: "r1", revision: 1, name: "Ice cream", cost: 5, member: "p1", creator: "p1", status: "requested" };
  const r2 = { id: "r2", revision: 1, name: "Park visit", cost: 10, member: "c1", creator: "c1", status: "requested" };
  const rewards = { catalog: [], requests: [r1, r2], balances: [b1, b2] };

  const childCard = createMockCard({ role: "child", actor: "c1", rewards });
  const childBody = document.createElement("div");
  renderRewards(childCard, childBody);
  assert.ok(childBody.textContent.includes("Child One"));
  assert.ok(!childBody.textContent.includes("Parent One"));
  assert.ok(childBody.textContent.includes("Park visit"));
  assert.ok(!childBody.textContent.includes("Ice cream"));

  const parentCard = createMockCard({ role: "parent", actor: "p1", rewards });
  const parentBody = document.createElement("div");
  renderRewards(parentCard, parentBody);
  assert.ok(parentBody.textContent.includes("Child One"));
  assert.ok(parentBody.textContent.includes("Parent One"));
  assert.ok(parentBody.textContent.includes("Park visit"));
  assert.ok(parentBody.textContent.includes("Ice cream"));
});

test("4. Strict cost validation (1..10000) and request TTL (1..720) in catalog creation", () => {
  const card = createMockCard({ role: "parent" });
  const body = document.createElement("div");
  card._rewardDraft = { type: "catalog_create", name: "Board Game", cost: 0, description: "fun", enabled: true, request_ttl_hours: 1000 };
  renderRewards(card, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.CustomEvent("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0); // blocked by invalid cost/ttl

  // Fix cost and ttl to valid bounds
  card._rewardDraft.cost = 50;
  card._rewardDraft.request_ttl_hours = 24;
  body.replaceChildren();
  renderRewards(card, body);
  const validForm = body.querySelectorAll("form")[0];
  validForm.dispatchEvent(new dom.window.CustomEvent("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.equal(card.commands[0].action, "court.reward_save");
  assert.equal(card.commands[0].payload.cost, 50);
  assert.equal(card.commands[0].payload.request_ttl_hours, 24);
});

test("5. Catalog create and edit payloads: edit includes exact id and revision", () => {
  const card = createMockCard({
    role: "parent",
    rewards: { catalog: [{ id: "c10", revision: 3, name: "Book", cost: 15, description: "Sci-Fi", enabled: true, request_ttl_hours: 48, eligible: ["c1"] }] }
  });
  const body = document.createElement("div");
  card._rewardDraft = { type: "catalog_edit", id: "c10", revision: 3, name: "Book Updated", cost: 20, description: "Sci-Fi", enabled: true, request_ttl_hours: 48, eligible: ["c1"] };
  renderRewards(card, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.CustomEvent("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], {
    action: "court.reward_save",
    payload: { id: "c10", revision: 3, name: "Book Updated", cost: 20, description: "Sci-Fi", enabled: true, eligible: ["c1"], request_ttl_hours: 48 }
  });
});

test("6. Stale revision detection rejects instead of silently updating", () => {
  const card = createMockCard({
    role: "parent",
    rewards: { catalog: [{ id: "c10", revision: 4, name: "Book", cost: 15 }] }
  });
  const body = document.createElement("div");
  // Draft has stale revision 3
  card._rewardDraft = { type: "catalog_edit", id: "c10", revision: 3, name: "Book New", cost: 20, description: "", enabled: true, request_ttl_hours: 24, eligible: [] };
  renderRewards(card, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.CustomEvent("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0);
  assert.equal(card._actionError, "conflict");
  assert.equal(card._rewardDraft, null);
});

test("7. Retry mechanism retains exact frozen payload on failure", () => {
  const card = createMockCard({ role: "parent" });
  const body = document.createElement("div");
  const payload = { name: "Camp", cost: 100, description: "", enabled: true, eligible: [], request_ttl_hours: 168 };
  card._actionError = "network_timeout";
  card._rewardDraft = { type: "catalog_create", frozenPayload: payload, ...payload };
  renderRewards(card, body);
  const retryBtn = Array.from(body.querySelectorAll("button")).find(b => b.textContent === REWARD_COPY.en.retry);
  assert.ok(retryBtn);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.CustomEvent("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], { action: "court.reward_save", payload });
});

test("8. Child can cancel only own requested status request", () => {
  const reqOwn = { id: "req1", revision: 1, reward_id: "cat1", name: "Playtime", cost: 5, member: "c1", creator: "c1", status: "requested" };
  const reqOther = { id: "req2", revision: 1, reward_id: "cat2", name: "Trip", cost: 50, member: "c2", creator: "c2", status: "requested" };
  const childCard = createMockCard({
    role: "child",
    actor: "c1",
    rewards: { catalog: [], requests: [reqOwn, reqOther], balances: [{ member: "c1", available: 10 }] }
  });
  const body = document.createElement("div");
  renderRewards(childCard, body);

  // Child should only see reqOwn and have a Cancel button for it
  const buttons = Array.from(body.querySelectorAll("button"));
  const cancelBtn = buttons.find(b => b.textContent === REWARD_COPY.en.cancel);
  assert.ok(cancelBtn);

  // Open transition draft to cancel
  childCard._rewardDraft = { type: "transition", id: "req1", revision: 1, decision: "cancel", reason: "changed mind" };
  renderRewards(childCard, body);
  const transForm = body.querySelector("form");
  transForm.dispatchEvent(new dom.window.CustomEvent("submit", { cancelable: true }));
  assert.equal(childCard.commands.length, 1);
  assert.deepEqual(childCard.commands[0], {
    action: "court.reward_transition",
    payload: { id: "req1", revision: 1, decision: "cancel", reason: "changed mind" }
  });

  // Attempting to cancel someone else's request or a non-requested status is rejected
  childCard.commands.length = 0;
  childCard._rewardDraft = { type: "transition", id: "req2", revision: 1, decision: "cancel", reason: "not mine" };
  body.replaceChildren();
  renderRewards(childCard, body);
  const invalidForm = body.querySelector("form");
  assert.equal(invalidForm,null);
  assert.equal(childCard.commands.length, 0);
  assert.equal(childCard._rewardDraft, null);
});

test("focused request form rechecks refreshed catalog revision and wallet", () => {
  for(const change of ["revision","balance"]){
    const card=createMockCard({role:"child",actor:"c1",rewards:{catalog:[{id:"R1",revision:1,name:"A privilege",cost:5,enabled:true,eligible:[]}],requests:[],balances:[{member:"c1",available:10}]}});
    card._rewardDraft={type:"request_confirm",id:"R1",revision:1,member:"c1",note:""};
    const body=document.createElement("div");renderRewards(card,body);
    card._data=structuredClone(card._data);
    if(change==="revision")card._data.rewards.catalog[0].revision=2;
    else card._data.rewards.balances[0].available=0;
    body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
    assert.equal(card.commands.length,0);
    if(change==="revision")assert.equal(card._actionError,"conflict");
    else assert.ok(body.textContent.includes(REWARD_COPY.en.insufficient_funds));
  }
});

test("transition draft never adopts a newer revision or role", () => {
  const card=createMockCard({rewards:{catalog:[],requests:[{id:"V1",revision:1,name:"A promise",cost:5,member:"c1",status:"requested"}],balances:[]}});
  card._rewardDraft={type:"transition",id:"V1",revision:1,decision:"approve",reason:"Checked"};
  const body=document.createElement("div");renderRewards(card,body);
  card._data=structuredClone(card._data);card._data.rewards.requests[0].revision=2;
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  assert.equal(card.commands.length,0);assert.equal(card._actionError,"conflict");
});
