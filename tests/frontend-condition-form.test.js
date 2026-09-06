import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body><div id='root'></div></body>", {
  url: "http://localhost",
});
for (const key of ["window", "document", "HTMLElement", "Event"]) {
  globalThis[key] = dom.window[key];
}

const { CONDITION_COPY, renderConditionForm } = await import(
  "../custom_components/family_assistant/frontend/condition-form.js"
);

const clone = (value) => JSON.parse(JSON.stringify(value));

test("changing all to any preserves text edited since the last structural render", () => {
  const mounted = mount({
    value: {
      kind: "all",
      conditions: [
        {
          kind: "entity_state",
          entity_id: "sensor.synthetic",
          state: "old",
        },
      ],
    },
    allowlist: ["sensor.synthetic"],
  });
  const rootKind = mounted.fieldset.querySelector(
    '[data-condition-field="kind"][data-condition-path=""]',
  );
  input(
    mounted.fieldset.querySelector('[data-condition-field="state"]'),
    "new",
  );
  change(rootKind, "any");
  assert.equal(mounted.changes.at(-1).conditions[0].state, "new");
});

function mount(options = {}) {
  const root = document.getElementById("root");
  root.replaceChildren();
  const changes = [];
  const fieldset = renderConditionForm({
    ...options,
    onChange: (value) => changes.push(value),
  });
  root.append(fieldset);
  return { root, fieldset, changes };
}

function change(control, value) {
  if (control.type === "checkbox") control.checked = value;
  else control.value = value;
  control.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
}

function input(control, value) {
  control.value = value;
  control.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
}

function controlForLabel(root, labelText, selector = "input,select") {
  const label = [...root.querySelectorAll("label")].find(
    (candidate) => candidate.firstChild?.textContent === labelText,
  );
  assert.ok(label, `missing label: ${labelText}`);
  const control = label.querySelector(selector);
  assert.ok(control, `missing control for: ${labelText}`);
  return control;
}

test("CONDITION_COPY has exact EN, RU, and UK key parity", () => {
  const enKeys = Object.keys(CONDITION_COPY.en).sort();
  assert.deepEqual(Object.keys(CONDITION_COPY.ru).sort(), enKeys);
  assert.deepEqual(Object.keys(CONDITION_COPY.uk).sort(), enKeys);

  const modeKeys = Object.keys(CONDITION_COPY.en.modes).sort();
  for (const language of ["en", "ru", "uk"]) {
    assert.deepEqual(
      Object.keys(CONDITION_COPY[language].modes).sort(),
      modeKeys,
    );
    for (const key of enKeys.filter((key) => key !== "modes")) {
      assert.ok(
        CONDITION_COPY[language][key],
        `${language}.${key} must be non-empty`,
      );
    }
    for (const key of modeKeys) {
      assert.ok(
        CONDITION_COPY[language].modes[key],
        `${language}.modes.${key} must be non-empty`,
      );
    }
  }
});

test("an absent condition changes to a canonical mode without mutating the input", () => {
  const mounted = mount({ value: null });
  const kind = mounted.fieldset.querySelector("select");
  change(kind, "mode");

  assert.deepEqual(mounted.changes, [
    { kind: "mode", mode: "normal", negate: false },
  ]);
});

test("nested time and entity edits preserve untouched groups, negation, and values", () => {
  const value = {
    kind: "all",
    negate: true,
    conditions: [
      {
        kind: "any",
        negate: true,
        conditions: [
          { kind: "mode", mode: "holidays", negate: false },
          {
            kind: "time_window",
            start: "07:30",
            end: "09:15",
            timezone: "Europe/Kyiv",
            negate: false,
          },
        ],
      },
      {
        kind: "entity_state",
        entity_id: "binary_sensor.front_door",
        state: "off",
        max_age_seconds: 300,
        negate: true,
      },
    ],
  };
  const original = clone(value);
  const mounted = mount({
    value,
    allowlist: ["binary_sensor.front_door", "binary_sensor.window"],
    timezone: "UTC",
  });

  input(controlForLabel(mounted.fieldset, CONDITION_COPY.en.start), "08:05");
  let latest = mounted.changes.at(-1);
  assert.equal(latest.conditions[0].conditions[1].start, "08:05");
  assert.equal(latest.conditions[0].conditions[1].end, "09:15");
  assert.equal(latest.conditions[0].conditions[1].timezone, "Europe/Kyiv");
  assert.equal(latest.conditions[0].negate, true);
  assert.deepEqual(
    latest.conditions[0].conditions[0],
    value.conditions[0].conditions[0],
  );

  input(controlForLabel(mounted.fieldset, CONDITION_COPY.en.state), "closed");
  latest = mounted.changes.at(-1);
  assert.equal(latest.conditions[1].state, "closed");
  assert.equal(latest.conditions[1].entity_id, "binary_sensor.front_door");
  assert.equal(latest.conditions[1].max_age_seconds, 300);
  assert.equal(latest.conditions[1].negate, true);

  change(mounted.fieldset.querySelector("input[type='checkbox']"), false);
  latest = mounted.changes.at(-1);
  assert.equal(latest.negate, false);
  assert.equal(latest.conditions[0].negate, true);
  assert.equal(latest.conditions[0].conditions[1].start, "08:05");
  assert.equal(latest.conditions[1].state, "closed");
  assert.deepEqual(
    value,
    original,
    "the supplied condition must remain immutable",
  );
});

test("nested kind and negate controls edit only their addressed node", () => {
  const value = {
    kind: "all",
    negate: true,
    conditions: [
      { kind: "mode", mode: "holidays", negate: false },
      { kind: "mode", mode: "ill", negate: true },
    ],
  };
  const mounted = mount({
    value,
    allowlist: ["binary_sensor.front_door"],
  });

  const firstKind = mounted.fieldset.querySelector(
    '[data-condition-field="kind"][data-condition-path="0"]',
  );
  assert.ok(firstKind);
  change(firstKind, "entity_state");
  assert.deepEqual(mounted.changes.at(-1), {
    kind: "all",
    negate: true,
    conditions: [
      {
        kind: "entity_state",
        entity_id: "binary_sensor.front_door",
        state: "",
        max_age_seconds: 120,
        negate: false,
      },
      { kind: "mode", mode: "ill", negate: true },
    ],
  });

  const firstNegate = mounted.fieldset.querySelector(
    '[data-condition-field="negate"][data-condition-path="0"]',
  );
  change(firstNegate, true);
  assert.equal(mounted.changes.at(-1).conditions[0].negate, true);
  assert.deepEqual(mounted.changes.at(-1).conditions[1], value.conditions[1]);
  assert.deepEqual(value.conditions[0], {
    kind: "mode",
    mode: "holidays",
    negate: false,
  });
});

test("a nested kind cannot be changed to the absent root-only value", () => {
  const value = {
    kind: "all",
    conditions: [{ kind: "mode", mode: "normal", negate: false }],
    negate: false,
  };
  const mounted = mount({ value });
  const nestedKind = mounted.fieldset.querySelector(
    '[data-condition-field="kind"][data-condition-path="0"]',
  );
  const absent = nestedKind.querySelector('option[value=""]');
  assert.ok(
    absent === null || absent.disabled,
    "nested selectors must not offer an active None",
  );
  if (absent) change(nestedKind, "");
  assert.deepEqual(mounted.changes, []);
  assert.deepEqual(value.conditions[0], {
    kind: "mode",
    mode: "normal",
    negate: false,
  });
});

test("entity conditions may omit max age and display the backend default", () => {
  const value = {
    kind: "entity_state",
    entity_id: "binary_sensor.front_door",
    state: "off",
    negate: false,
  };
  const mounted = mount({
    value,
    allowlist: ["binary_sensor.front_door"],
  });

  const age = mounted.fieldset.querySelector(
    '[data-condition-field="max_age_seconds"]',
  );
  assert.ok(
    age,
    "an omitted optional max age must not make the condition unsupported",
  );
  assert.equal(age.value, "120");
  assert.deepEqual(mounted.changes, []);
  assert.equal("max_age_seconds" in value, false);
});

test("text input retains focus and DOM identity across keystrokes", () => {
  const mounted = mount({
    value: {
      kind: "entity_state",
      entity_id: "binary_sensor.front_door",
      state: "off",
      max_age_seconds: 120,
      negate: false,
    },
    allowlist: ["binary_sensor.front_door"],
  });
  const state = mounted.fieldset.querySelector(
    '[data-condition-field="state"]',
  );
  state.focus();
  input(state, "on");

  assert.equal(document.activeElement, state);
  assert.equal(state.isConnected, true);
  assert.equal(
    mounted.fieldset.querySelector('[data-condition-field="state"]'),
    state,
  );
  assert.equal(mounted.changes.at(-1).state, "on");
});

test("disabled, stale, detached, and superseded controls cannot emit mutations", () => {
  const value = { kind: "mode", mode: "normal", negate: false };

  const disabled = mount({ value, disabled: true });
  const disabledMode = controlForLabel(
    disabled.fieldset,
    CONDITION_COPY.en.mode,
  );
  assert.equal(disabledMode.disabled, true);
  change(disabledMode, "vacation");
  assert.deepEqual(disabled.changes, []);

  let stale = false;
  const staleForm = mount({ value, isStale: () => stale });
  const staleMode = controlForLabel(staleForm.fieldset, CONDITION_COPY.en.mode);
  stale = true;
  change(staleMode, "ill");
  assert.deepEqual(staleForm.changes, []);

  const detached = mount({ value });
  const detachedMode = controlForLabel(
    detached.fieldset,
    CONDITION_COPY.en.mode,
  );
  detached.fieldset.remove();
  change(detachedMode, "guests");
  assert.deepEqual(detached.changes, []);

  const rerendered = mount({ value });
  const oldMode = controlForLabel(rerendered.fieldset, CONDITION_COPY.en.mode);
  change(rerendered.fieldset.querySelector("input[type='checkbox']"), true);
  change(oldMode, "holidays");
  assert.equal(
    rerendered.changes.length,
    1,
    "a control detached by rerender must be inert",
  );
  assert.deepEqual(value, { kind: "mode", mode: "normal", negate: false });
});

test("group choices enforce depth three and the global twenty-node budget", () => {
  const depthThree = mount({
    value: {
      kind: "all",
      conditions: [
        {
          kind: "any",
          conditions: [{ kind: "mode", mode: "normal" }],
        },
      ],
    },
  });
  const deepestKind = depthThree.fieldset.querySelector(
    '[data-condition-field="kind"][data-condition-path="0.0"]',
  );
  assert.equal(deepestKind.querySelector('option[value="all"]').disabled, true);
  assert.equal(deepestKind.querySelector('option[value="any"]').disabled, true);
  change(deepestKind, "all");
  assert.deepEqual(depthThree.changes, []);

  const twentyNodes = {
    kind: "all",
    negate: true,
    conditions: Array.from({ length: 19 }, () => ({
      kind: "mode",
      mode: "normal",
    })),
  };
  const budget = mount({ value: twentyNodes });
  const budgetAdds = [...budget.fieldset.querySelectorAll("button")].filter(
    (button) => button.textContent === CONDITION_COPY.en.add,
  );
  assert.equal(budgetAdds.length, 1);
  assert.ok(budgetAdds.every((button) => button.disabled));
  budgetAdds[0].click();
  assert.deepEqual(budget.changes, []);

  const budgetLeafKind = budget.fieldset.querySelector(
    '[data-condition-field="kind"][data-condition-path="18"]',
  );
  assert.equal(
    budgetLeafKind.querySelector('option[value="all"]').disabled,
    true,
  );
  assert.equal(
    budgetLeafKind.querySelector('option[value="any"]').disabled,
    true,
  );
  change(budgetLeafKind, "any");
  assert.deepEqual(budget.changes, []);

  const replacement = mount({ value: twentyNodes });
  const rootKind = replacement.fieldset.querySelector(
    '[data-condition-field="kind"][data-condition-path=""]',
  );
  change(rootKind, "any");
  assert.deepEqual(replacement.changes, [{ ...twentyNodes, kind: "any" }]);
});

test("unsupported existing conditions stay untouched until explicit replacement", () => {
  const unsupported = {
    kind: "future_condition",
    payload: '<img src=x onerror="globalThis.pwned=true">',
  };
  const original = clone(unsupported);
  const mounted = mount({ value: unsupported });

  assert.deepEqual(mounted.changes, []);
  assert.deepEqual(unsupported, original);
  assert.equal(mounted.fieldset.querySelectorAll("img,script").length, 0);
  assert.equal(
    mounted.fieldset.textContent.includes(unsupported.payload),
    false,
  );

  const replace = [...mounted.fieldset.querySelectorAll("button")].find(
    (button) => button.textContent === CONDITION_COPY.en.replace,
  );
  assert.ok(replace);
  replace.click();
  assert.deepEqual(mounted.changes, [null]);
  assert.deepEqual(unsupported, original);
});

test("known kinds with unknown keys require explicit replacement", () => {
  const value = {
    kind: "mode",
    mode: "ill",
    negate: true,
    future_field: "preserve until click",
  };
  const mounted = mount({ value });
  assert.deepEqual(mounted.changes, []);
  assert.ok(
    mounted.fieldset.textContent.includes(CONDITION_COPY.en.unsupported),
  );

  const replace = [...mounted.fieldset.querySelectorAll("button")].find(
    (button) => button.textContent === CONDITION_COPY.en.replace,
  );
  replace.click();

  assert.deepEqual(mounted.changes, [null]);
  assert.equal(value.future_field, "preserve until click");
});

test("non-boolean negate is unsupported and cannot silently coerce", () => {
  const value = { kind: "mode", mode: "normal", negate: "false" };
  const mounted = mount({ value });

  assert.ok(
    mounted.fieldset.textContent.includes(CONDITION_COPY.en.unsupported),
  );
  assert.equal(
    mounted.fieldset.querySelector('[data-condition-field="negate"]'),
    null,
  );
  assert.deepEqual(mounted.changes, []);
  assert.equal(value.negate, "false");
});

test("an absent condition adds no hidden-invalid form blocker", () => {
  const form = document.createElement("form");
  document.getElementById("root").replaceChildren(form);
  const fieldset = renderConditionForm({ value: null });
  form.append(fieldset);

  assert.equal(form.checkValidity(), true);
  assert.equal(fieldset.querySelectorAll("input").length, 0);
  assert.equal(fieldset.querySelector("select").required, false);
});

test("values and allowlist labels are rendered as text, never HTML", () => {
  const attack =
    '<img src=x onerror="globalThis.pwned=true"><script>bad()</script>';
  const mounted = mount({
    value: {
      kind: "entity_state",
      entity_id: attack,
      state: attack,
      max_age_seconds: 120,
      negate: false,
    },
    allowlist: [attack],
  });

  assert.equal(mounted.fieldset.querySelectorAll("img,script").length, 0);
  assert.equal(
    controlForLabel(mounted.fieldset, CONDITION_COPY.en.entity).value,
    attack,
  );
  assert.equal(
    controlForLabel(mounted.fieldset, CONDITION_COPY.en.state).value,
    attack,
  );
  assert.equal(globalThis.pwned, undefined);
});
