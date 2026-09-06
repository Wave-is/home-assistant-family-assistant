/**
 * Pure condition validation and normalization for routine conditions.
 *
 * Implements strict domain validation matching routine_conditions.py and
 * routine_validation.py:
 * - null represents optional absent condition and returns null
 * - strict types, keys, and values
 * - entity allowlist enforcement (DomainError("forbidden"))
 * - rejects non-objects, arrays, cycles, and unknown keys
 * - never mutates input
 * - throws Error with .code and .field properties, never leaking sensitive values
 */

const MODES = new Set(["normal", "holidays", "guests", "ill", "vacation"]);
const ENTITY_REGEX = /^[a-z0-9_]+\.[a-z0-9_]+$/;
const CLOCK_REGEX = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

function throwInvalidField(field) {
  const err = new Error(`invalid_field: ${field}`);
  err.code = "invalid_field";
  err.field = field;
  throw err;
}

function throwForbidden() {
  const err = new Error("forbidden");
  err.code = "forbidden";
  err.field = "";
  throw err;
}

function assertStrictKeys(obj, allowedKeys, requiredKeys) {
  const actualKeys = Object.keys(obj);
  const unknown = actualKeys.filter((k) => !allowedKeys.has(k));
  const missing = [...requiredKeys].filter((k) => !actualKeys.includes(k));

  if (unknown.length > 0 || missing.length > 0) {
    const sorted = [...unknown, ...missing].sort();
    throwInvalidField(sorted[0]);
  }
}

function assertValidTimezone(zone) {
  if (
    typeof zone !== "string" ||
    !zone.trim() ||
    zone.length > 80 ||
    /^[+-]/.test(zone)
  ) {
    throwInvalidField("timezone");
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone });
  } catch {
    throwInvalidField("timezone");
  }
}

function validateNode(cond, depth, budget, visited, allowedEntitySet) {
  if (
    cond === null ||
    typeof cond !== "object" ||
    Array.isArray(cond) ||
    depth > 3 ||
    budget[0] <= 0
  ) {
    throwInvalidField(depth > 3 ? "conditions" : "condition");
  }

  if (visited.has(cond)) {
    throwInvalidField("condition");
  }
  visited.add(cond);

  budget[0] -= 1;

  const kind = cond.kind;
  if (
    typeof kind !== "string" ||
    !["mode", "entity_state", "time_window", "all", "any"].includes(kind)
  ) {
    throwInvalidField("kind");
  }

  let negate = false;
  if (Object.prototype.hasOwnProperty.call(cond, "negate")) {
    if (typeof cond.negate !== "boolean") {
      throwInvalidField("negate");
    }
    negate = cond.negate;
  }

  if (kind === "mode") {
    assertStrictKeys(
      cond,
      new Set(["kind", "negate", "mode"]),
      new Set(["kind", "mode"]),
    );
    const mode = cond.mode;
    if (typeof mode !== "string" || !MODES.has(mode)) {
      throwInvalidField("mode");
    }
    visited.delete(cond);
    return [1, { kind: "mode", mode, negate }];
  }

  if (kind === "entity_state") {
    assertStrictKeys(
      cond,
      new Set(["kind", "negate", "entity_id", "state", "max_age_seconds"]),
      new Set(["kind", "entity_id", "state"]),
    );
    const entityId = cond.entity_id;
    if (
      typeof entityId !== "string" ||
      entityId.length > 255 ||
      !ENTITY_REGEX.test(entityId)
    ) {
      throwInvalidField("entity_id");
    }

    if (!allowedEntitySet.has(entityId)) {
      throwForbidden();
    }

    const state = cond.state;
    if (
      typeof state !== "string" ||
      state.trim().length === 0 ||
      [...state].length > 100 ||
      state === "unknown" ||
      state === "unavailable"
    ) {
      throwInvalidField("state");
    }

    let maxAge = 120;
    if (Object.prototype.hasOwnProperty.call(cond, "max_age_seconds")) {
      const rawAge = cond.max_age_seconds;
      if (
        typeof rawAge !== "number" ||
        !Number.isInteger(rawAge) ||
        rawAge < 1 ||
        rawAge > 3600
      ) {
        throwInvalidField("max_age_seconds");
      }
      maxAge = rawAge;
    }

    visited.delete(cond);
    return [
      1,
      {
        kind: "entity_state",
        entity_id: entityId,
        state,
        max_age_seconds: maxAge,
        negate,
      },
    ];
  }

  if (kind === "time_window") {
    assertStrictKeys(
      cond,
      new Set(["kind", "negate", "start", "end", "timezone"]),
      new Set(["kind", "start", "end", "timezone"]),
    );

    const start = cond.start;
    if (typeof start !== "string" || !CLOCK_REGEX.test(start)) {
      throwInvalidField("start");
    }

    const end = cond.end;
    if (typeof end !== "string" || !CLOCK_REGEX.test(end)) {
      throwInvalidField("end");
    }

    if (start === end) {
      throwInvalidField("time_window");
    }

    const timezone = cond.timezone;
    assertValidTimezone(timezone);

    visited.delete(cond);
    return [
      1,
      {
        kind: "time_window",
        start,
        end,
        timezone,
        negate,
      },
    ];
  }

  // kind === "all" || kind === "any"
  assertStrictKeys(
    cond,
    new Set(["kind", "negate", "conditions"]),
    new Set(["kind", "conditions"]),
  );
  const children = cond.conditions;
  if (!Array.isArray(children) || children.length < 1 || children.length > 19) {
    throwInvalidField("conditions");
  }

  let totalNodes = 1;
  const normalizedChildren = [];
  for (const child of children) {
    const [subNodes, normChild] = validateNode(
      child,
      depth + 1,
      budget,
      visited,
      allowedEntitySet,
    );
    totalNodes += subNodes;
    normalizedChildren.push(normChild);
  }

  visited.delete(cond);
  return [
    totalNodes,
    {
      kind,
      conditions: normalizedChildren,
      negate,
    },
  ];
}

/**
 * Pure validator and normalizer for routine conditions.
 *
 * @param {unknown} value - Condition AST or null
 * @param {{ allowlist?: string[] | Set<string> }} [options] - Allowed entities
 * @returns {object|null} Normalized condition object or null if value is null
 */
export function normalizeCondition(value, { allowlist = [] } = {}) {
  if (value === null) {
    return null;
  }

  const allowedEntitySet = new Set(
    Array.isArray(allowlist) || allowlist instanceof Set ? allowlist : [],
  );

  const budget = [20];
  const visited = new Set();
  const [, normalized] = validateNode(
    value,
    1,
    budget,
    visited,
    allowedEntitySet,
  );
  return normalized;
}
