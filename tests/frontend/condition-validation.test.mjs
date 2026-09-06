import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeCondition } from "../../custom_components/family_assistant/frontend/condition-validation.js";

test("only explicit null disables a condition", () => {
  assert.equal(normalizeCondition(null), null);
  assert.throws(() => normalizeCondition(undefined), { code: "invalid_field" });
  assert.equal(
    normalizeCondition(null, { allowlist: ["binary_sensor.motion"] }),
    null,
  );
});

test("nested valid normalization defaults and strict shapes", () => {
  const input = {
    kind: "all",
    conditions: [
      {
        kind: "mode",
        mode: "normal",
      },
      {
        kind: "entity_state",
        entity_id: "binary_sensor.motion",
        state: "on",
      },
      {
        kind: "time_window",
        start: "08:00",
        end: "20:00",
        timezone: "Europe/Kyiv",
      },
      {
        kind: "any",
        conditions: [
          {
            kind: "mode",
            mode: "vacation",
            negate: true,
          },
          {
            kind: "entity_state",
            entity_id: "sensor.kitchen_temp",
            state: "22",
            max_age_seconds: 300,
            negate: false,
          },
        ],
      },
    ],
  };

  const norm = normalizeCondition(input, {
    allowlist: ["binary_sensor.motion", "sensor.kitchen_temp"],
  });

  assert.deepEqual(norm, {
    kind: "all",
    negate: false,
    conditions: [
      {
        kind: "mode",
        mode: "normal",
        negate: false,
      },
      {
        kind: "entity_state",
        entity_id: "binary_sensor.motion",
        state: "on",
        max_age_seconds: 120,
        negate: false,
      },
      {
        kind: "time_window",
        start: "08:00",
        end: "20:00",
        timezone: "Europe/Kyiv",
        negate: false,
      },
      {
        kind: "any",
        negate: false,
        conditions: [
          {
            kind: "mode",
            mode: "vacation",
            negate: true,
          },
          {
            kind: "entity_state",
            entity_id: "sensor.kitchen_temp",
            state: "22",
            max_age_seconds: 300,
            negate: false,
          },
        ],
      },
    ],
  });
});

test("source immutability: deep freeze or cloned input is not modified", () => {
  const child = Object.freeze({
    kind: "entity_state",
    entity_id: "binary_sensor.door",
    state: "open",
  });
  const input = Object.freeze({
    kind: "all",
    conditions: [child],
  });

  // Should succeed without trying to mutate the frozen objects
  const norm = normalizeCondition(input, {
    allowlist: ["binary_sensor.door"],
  });

  assert.notEqual(norm, input);
  assert.equal(norm.conditions[0].max_age_seconds, 120);
  assert.equal("max_age_seconds" in child, false);
});

test("global node count limit (max 20 total nodes across tree)", () => {
  // 1 root + 19 children = 20 nodes (allowed)
  const children20 = Array.from({ length: 19 }, () => ({
    kind: "mode",
    mode: "normal",
  }));
  const valid20 = {
    kind: "all",
    conditions: children20,
  };
  const norm = normalizeCondition(valid20);
  assert.equal(norm.conditions.length, 19);

  // Global shared budget across multiple branches:
  // Root (1) + branch1 (1 + 10 = 11) + branch2 (1 + 9 = 10) = 22 nodes (exceeds 20)
  const branch1 = {
    kind: "any",
    conditions: Array.from({ length: 10 }, () => ({
      kind: "mode",
      mode: "normal",
    })),
  };
  const branch2 = {
    kind: "any",
    conditions: Array.from({ length: 9 }, () => ({
      kind: "mode",
      mode: "normal",
    })),
  };
  const exceededTree = {
    kind: "all",
    conditions: [branch1, branch2],
  };

  assert.throws(
    () => normalizeCondition(exceededTree),
    (err) => err.code === "invalid_field" && err.field === "condition",
  );
});

test("depth limit (max depth 3, depth 4 throws invalid_field conditions)", () => {
  // Depth 1: all
  // Depth 2: any
  // Depth 3: mode -> valid
  const validDepth3 = {
    kind: "all",
    conditions: [
      {
        kind: "any",
        conditions: [
          {
            kind: "mode",
            mode: "normal",
          },
        ],
      },
    ],
  };
  assert.ok(normalizeCondition(validDepth3));

  // Depth 1: all
  // Depth 2: all
  // Depth 3: all
  // Depth 4: mode -> throws conditions
  const invalidDepth4 = {
    kind: "all",
    conditions: [
      {
        kind: "all",
        conditions: [
          {
            kind: "all",
            conditions: [
              {
                kind: "mode",
                mode: "normal",
              },
            ],
          },
        ],
      },
    ],
  };
  assert.throws(
    () => normalizeCondition(invalidDepth4),
    (err) => err.code === "invalid_field" && err.field === "conditions",
  );
});

test("all / any must have between 1 and 19 children", () => {
  assert.throws(
    () => normalizeCondition({ kind: "all", conditions: [] }),
    (err) => err.code === "invalid_field" && err.field === "conditions",
  );
  assert.throws(
    () =>
      normalizeCondition({
        kind: "all",
        conditions: Array.from({ length: 20 }, () => ({
          kind: "mode",
          mode: "normal",
        })),
      }),
    (err) => err.code === "invalid_field" && err.field === "conditions",
  );
});

test("booleans: negate strict type, rejects truthy/falsy numeric or string coercion", () => {
  for (const badNegate of [1, 0, "true", "false", null, {}, []]) {
    assert.throws(
      () =>
        normalizeCondition({
          kind: "mode",
          mode: "normal",
          negate: badNegate,
        }),
      (err) => err.code === "invalid_field" && err.field === "negate",
    );
  }
});

test("numeric coercion: max_age_seconds strictly integer 1..3600, no strings or floats", () => {
  for (const badAge of [
    "120",
    12.5,
    0,
    3601,
    null,
    true,
    false,
    NaN,
    Infinity,
  ]) {
    assert.throws(
      () =>
        normalizeCondition(
          {
            kind: "entity_state",
            entity_id: "binary_sensor.motion",
            state: "on",
            max_age_seconds: badAge,
          },
          { allowlist: ["binary_sensor.motion"] },
        ),
      (err) => err.code === "invalid_field" && err.field === "max_age_seconds",
    );
  }
});

test("bad keys and extra properties are rejected with alphabetical priority", () => {
  assert.throws(
    () =>
      normalizeCondition({
        kind: "mode",
        mode: "normal",
        extra_key: 123,
      }),
    (err) => err.code === "invalid_field" && err.field === "extra_key",
  );

  // When multiple unknown/missing keys exist, sorted alphabetically
  assert.throws(
    () =>
      normalizeCondition({
        kind: "mode",
        // missing 'mode'
        z_extra: "bad",
        a_extra: "bad",
      }),
    (err) => err.code === "invalid_field" && err.field === "a_extra",
  );
});

test("entity allowlist validation and revocation", () => {
  const cond = {
    kind: "entity_state",
    entity_id: "binary_sensor.front_door",
    state: "open",
  };

  // Allowed
  const norm = normalizeCondition(cond, {
    allowlist: ["binary_sensor.front_door"],
  });
  assert.equal(norm.entity_id, "binary_sensor.front_door");

  // Revoked / forbidden
  assert.throws(
    () =>
      normalizeCondition(cond, {
        allowlist: ["binary_sensor.back_door"],
      }),
    (err) => err.code === "forbidden",
  );

  // Empty allowlist
  assert.throws(
    () => normalizeCondition(cond, { allowlist: [] }),
    (err) => err.code === "forbidden",
  );
});

test("unknown-state and unavailable values rejected, length limits, trim verification", () => {
  assert.throws(
    () =>
      normalizeCondition(
        {
          kind: "entity_state",
          entity_id: "binary_sensor.motion",
          state: "unknown",
        },
        { allowlist: ["binary_sensor.motion"] },
      ),
    (err) => err.code === "invalid_field" && err.field === "state",
  );

  assert.throws(
    () =>
      normalizeCondition(
        {
          kind: "entity_state",
          entity_id: "binary_sensor.motion",
          state: "unavailable",
        },
        { allowlist: ["binary_sensor.motion"] },
      ),
    (err) => err.code === "invalid_field" && err.field === "state",
  );

  assert.throws(
    () =>
      normalizeCondition(
        {
          kind: "entity_state",
          entity_id: "binary_sensor.motion",
          state: "   ",
        },
        { allowlist: ["binary_sensor.motion"] },
      ),
    (err) => err.code === "invalid_field" && err.field === "state",
  );

  assert.throws(
    () =>
      normalizeCondition(
        {
          kind: "entity_state",
          entity_id: "binary_sensor.motion",
          state: "x".repeat(101),
        },
        { allowlist: ["binary_sensor.motion"] },
      ),
    (err) => err.code === "invalid_field" && err.field === "state",
  );

  // Preserve original text without stripping internal or edge whitespace if nonempty
  const norm = normalizeCondition(
    {
      kind: "entity_state",
      entity_id: "binary_sensor.motion",
      state: " hello world ",
    },
    { allowlist: ["binary_sensor.motion"] },
  );
  assert.equal(norm.state, " hello world ");
  const unicode = {
    kind: "entity_state",
    entity_id: "sensor.synthetic",
    state: "💡".repeat(100),
  };
  assert.equal(
    normalizeCondition(unicode, { allowlist: ["sensor.synthetic"] }).state,
    unicode.state,
  );
  assert.throws(
    () =>
      normalizeCondition(
        { ...unicode, state: unicode.state + "💡" },
        {
          allowlist: ["sensor.synthetic"],
        },
      ),
    { code: "invalid_field", field: "state" },
  );
});

test("clocks and timezone: strict HH:MM, different start/end, IANA timezone Intl validation", () => {
  // Identical start/end
  assert.throws(
    () =>
      normalizeCondition({
        kind: "time_window",
        start: "10:00",
        end: "10:00",
        timezone: "Europe/Kyiv",
      }),
    (err) => err.code === "invalid_field" && err.field === "time_window",
  );

  // Bad clock formats
  for (const badClock of ["10:0", "10:000", "24:00", "09:60", "9:00", "now"]) {
    assert.throws(
      () =>
        normalizeCondition({
          kind: "time_window",
          start: badClock,
          end: "12:00",
          timezone: "UTC",
        }),
      (err) => err.code === "invalid_field" && err.field === "start",
    );
  }

  // Bare numeric offsets or invalid IANA names rejected
  for (const badTz of [
    "+02:00",
    "-05:00",
    "+00:00",
    "Invalid/Timezone",
    "",
    "   ",
    "a".repeat(81),
  ]) {
    assert.throws(
      () =>
        normalizeCondition({
          kind: "time_window",
          start: "08:00",
          end: "16:00",
          timezone: badTz,
        }),
      (err) => err.code === "invalid_field" && err.field === "timezone",
    );
  }

  // Valid IANA timezone
  const norm = normalizeCondition({
    kind: "time_window",
    start: "08:00",
    end: "16:00",
    timezone: "America/New_York",
  });
  assert.equal(norm.timezone, "America/New_York");
});

test("rejects cycles, non-objects, arrays as root, and unknown kind", () => {
  // Cycle detection
  const cyclic = { kind: "all", conditions: [] };
  cyclic.conditions.push(cyclic);
  assert.throws(
    () => normalizeCondition(cyclic),
    (err) => err.code === "invalid_field" && err.field === "condition",
  );

  // Arrays or primitives as condition
  for (const nonObj of ["string", 123, true, [], [{}], () => {}]) {
    assert.throws(
      () => normalizeCondition(nonObj),
      (err) => err.code === "invalid_field" && err.field === "condition",
    );
  }

  // Unknown kind
  assert.throws(
    () => normalizeCondition({ kind: "unsupported" }),
    (err) => err.code === "invalid_field" && err.field === "kind",
  );
});

test("mode membership: strictly normal, holidays, guests, ill, vacation", () => {
  for (const validMode of ["normal", "holidays", "guests", "ill", "vacation"]) {
    const res = normalizeCondition({ kind: "mode", mode: validMode });
    assert.equal(res.mode, validMode);
  }

  for (const badMode of ["party", "sleep", "Normal", "VACATION", ""]) {
    assert.throws(
      () => normalizeCondition({ kind: "mode", mode: badMode }),
      (err) => err.code === "invalid_field" && err.field === "mode",
    );
  }
});
