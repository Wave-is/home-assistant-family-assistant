import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body><div id='root'></div></body>", {
  url: "http://localhost",
});
for (const key of ["window", "document", "HTMLElement", "Event", "FormData"])
  globalThis[key] = dom.window[key];
const { MEALS_COPY } = await import(
  "../custom_components/family_assistant/frontend/meals-copy.js"
);
const { renderMeals } = await import(
  "../custom_components/family_assistant/frontend/meals-view.js"
);

const plan = {
  id: "plan-1",
  revision: 3,
  status: "draft",
  week_start: "2026-09-07",
  title: "School week",
  note: "Parent note",
  entries: [
    {
      date: "2026-09-07",
      slot: "breakfast",
      title: "Oats",
      servings: 2,
      ingredients: [{ name: "Oats", unit: "g", quantity: 100 }],
    },
  ],
};
function card({
  role = "parent",
  language = "en",
  plans = [plan],
  outcomes = [],
} = {}) {
  let sequence = 0;
  return {
    _generation: 1,
    _entry: "entry-1",
    _config: { language },
    _hass: { language },
    _data: {
      actor: "parent-1",
      role,
      settings: { modules: ["pantry"] },
      pantry: { meal_plans: structuredClone(plans) },
    },
    parent: ["owner", "parent"].includes(role),
    _writing: false,
    _mealsDraft: null,
    _actionError: null,
    calls: [],
    button(label, action, primary = false) {
      const b = document.createElement("button");
      b.textContent = label;
      b.type = "button";
      if (primary) b.className = "primary";
      b.addEventListener("click", action);
      return b;
    },
    render() {},
    async command(action, payload) {
      this._writing = true;
      const fingerprint = JSON.stringify([this._entry, action, payload]);
      if (!this._pending || this._pending.fingerprint !== fingerprint)
        this._pending = { fingerprint, id: `op-${++sequence}` };
      this.calls.push({ action, payload, operationId: this._pending.id });
      const result = outcomes.shift();
      if (result instanceof Promise) await result;
      if (result === "fail") this._actionError = "transport";
      else {
        this._actionError = null;
        this._pending = null;
      }
      this._writing = false;
    },
  };
}
function render(card) {
  const body = document.createElement("div");
  document.getElementById("root").replaceChildren(body);
  renderMeals(card, body);
  return body;
}
function button(body, label) {
  const found = [...body.querySelectorAll("button")].find(
    (b) => b.textContent === label,
  );
  assert.ok(found, `missing ${label}`);
  return found;
}
function submit(body) {
  body
    .querySelector("form")
    .dispatchEvent(
      new dom.window.Event("submit", { bubbles: true, cancelable: true }),
    );
}
async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

test("parent creates a canonical Monday plan with nested entries", async () => {
  const c = card({ plans: [] });
  let body = render(c);
  button(body, MEALS_COPY.en.new_plan).click();
  body = render(c);
  body.querySelector("[name=week_start]").value = "2026-09-07";
  body.querySelector("[name=title]").value = "School week";
  body.querySelector("[name=note]").value = "Prep on Sunday";
  for (const [selector, value] of [
    ["[data-meals-path='0.title']", "Oats"],
    ["[data-meals-path='0.servings']", "2"],
  ]) {
    const input = body.querySelector(selector);
    input.value = value;
    input.dispatchEvent(new dom.window.Event("input"));
  }
  submit(body);
  await settle();
  assert.deepEqual(c.calls[0].payload, {
    week_start: "2026-09-07",
    title: "School week",
    note: "Prep on Sunday",
    entries: [
      {
        date: "2026-09-07",
        slot: "breakfast",
        title: "Oats",
        servings: 2,
        ingredients: [],
      },
    ],
  });
  assert.equal(c.calls[0].action, "pantry.meal_save");
});

test("published plans are readonly for adult and child, while guests see nothing", () => {
  const published = { ...plan, status: "published" };
  for (const role of ["adult", "child"]) {
    const body = render(card({ role, plans: [published] }));
    assert.ok(body.querySelector("[data-meal-plan='plan-1']"));
    assert.equal(body.querySelectorAll("form").length, 0);
    assert.equal(body.textContent.includes(MEALS_COPY.en.note), false);
  }
  assert.equal(
    render(card({ role: "guest", plans: [published] })).textContent,
    "",
  );
});

test("publish requires explicit review and carries id plus revision", async () => {
  const c = card();
  let body = render(c);
  button(body, MEALS_COPY.en.publish).click();
  body = render(c);
  assert.ok(body.textContent.includes(plan.title));
  submit(body);
  await settle();
  assert.equal(c.calls.length, 0);
  body.querySelector("[name=reviewed]").checked = true;
  submit(body);
  await settle();
  assert.deepEqual(c.calls[0].payload, { id: "plan-1", revision: 3 });
  assert.equal(c.calls[0].action, "pantry.meal_publish");
});

test("archive requires review and reason", async () => {
  const c = card();
  let body = render(c);
  button(body, MEALS_COPY.en.archive).click();
  body = render(c);
  body.querySelector("[name=reviewed]").checked = true;
  submit(body);
  await settle();
  assert.equal(c.calls.length, 0);
  body.querySelector("[name=reason]").value = "No longer needed";
  submit(body);
  await settle();
  assert.deepEqual(c.calls[0].payload, {
    id: "plan-1",
    revision: 3,
    reason: "No longer needed",
  });
});

test("stale detached controls cannot send and failed save retries frozen payload", async () => {
  const c = card({ outcomes: ["fail", "ok"] });
  let body = render(c);
  const old = button(body, MEALS_COPY.en.edit);
  c._generation += 1;
  old.click();
  assert.equal(c._mealsDraft, null);
  c._generation = 1;
  body = render(c);
  button(body, MEALS_COPY.en.edit).click();
  body = render(c);
  body.querySelector("[name=title]").value = "Changed";
  body
    .querySelector("[name=title]")
    .dispatchEvent(new dom.window.Event("input"));
  submit(body);
  await settle();
  assert.equal(c.calls.length, 1);
  const payload = c.calls[0].payload;
  assert.ok(c._mealsDraft?.pending);
  body = render(c);
  submit(body);
  await settle();
  assert.equal(c.calls.length, 2);
  assert.equal(c.calls[1].payload, payload);
  assert.equal(c.calls[1].operationId, c.calls[0].operationId);
  assert.equal(c._mealsDraft, null);
});

test("localized mobile labels and constraints remain readable", () => {
  const body = render(card({ language: "uk" }));
  assert.ok(body.textContent.includes(MEALS_COPY.uk.title));
  assert.ok(body.textContent.includes(MEALS_COPY.uk.edit));
  const formCard = card({ language: "ru" });
  let ru = render(formCard);
  button(ru, MEALS_COPY.ru.edit).click();
  ru = render(formCard);
  assert.equal(ru.querySelector("[name=week_start]").type, "date");
  assert.ok(
    ru.querySelector("[name=plan_title]") ||
      ru.textContent.includes(MEALS_COPY.ru.plan_title),
  );
  assert.ok(ru.textContent.includes(MEALS_COPY.ru.entries));
});
