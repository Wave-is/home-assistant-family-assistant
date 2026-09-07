/* Self-consent UI for normalized, display-only presence evidence. */

import { PRESENCE_COPY } from "./presence-copy.js";

const ROLES = new Set(["owner", "parent", "adult", "child"]);
const STATUSES = new Set(["reported_home", "reported_away", "unknown"]);
const REASONS = new Set([
  "fresh",
  "stale",
  "unavailable",
  "unconfigured",
  "not_shared",
]);

const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};
const clone = (value) => JSON.parse(JSON.stringify(value));
const deepFreeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value))
    return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
};

const STYLE = `
  .presence{display:grid;gap:12px}.presence-guide{margin:0}.presence-list{display:grid;gap:8px}
  .presence-self,.presence-shared-row,.presence-review{display:grid;gap:8px;min-width:0}
  .presence p,.presence dd{overflow-wrap:anywhere}.presence-self p,.presence-shared-row p,.presence-review p{margin:0}
  .presence-actions{display:flex;flex-wrap:wrap;gap:8px}.presence .presence-confirm{display:flex;flex-direction:row;justify-content:flex-start;gap:8px;align-items:flex-start}
  .presence-confirm input{flex:0 0 auto;margin-top:3px}.presence-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}
  .presence-review dt{font-weight:600}.presence-review dd{margin:0}.presence-observation{font-variant-numeric:tabular-nums}
  @media(max-width:520px){.presence-actions>button{width:100%}.presence-review dl{grid-template-columns:minmax(0,1fr)}.presence-review dd{margin-bottom:4px}}
`;

function copyOf(card) {
  const language = card?._config?.language || card?._hass?.language || "en";
  return PRESENCE_COPY[language.split(/[-_]/)[0]] || PRESENCE_COPY.en;
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}

function member(card, id) {
  return members(card).find((item) => item?.id === id) || null;
}

function validEvidence(row) {
  return Boolean(
    row &&
    typeof row.member === "string" &&
    row.member &&
    validRevision(row.member_revision) &&
    STATUSES.has(row.status) &&
    REASONS.has(row.reason) &&
    (row.observed_at === null || typeof row.observed_at === "string"),
  );
}

function validSelf(row) {
  return Boolean(
    validEvidence(row) &&
    typeof row.enabled === "boolean" &&
    typeof row.can_edit === "boolean" &&
    (row.binding_revision === null || validRevision(row.binding_revision)) &&
    (row.subscription_revision === null ||
      validRevision(row.subscription_revision)) &&
    (!row.can_edit || validRevision(row.binding_revision)) &&
    (!row.enabled ||
      (row.can_edit && validRevision(row.subscription_revision))),
  );
}

function presence(card) {
  const value = card?._data?.presence;
  return value && typeof value === "object" ? value : null;
}

function selfRow(card) {
  const row = presence(card)?.self;
  const actor = member(card, card?._data?.actor);
  if (
    !validSelf(row) ||
    row.member !== actor?.id ||
    row.member_revision !== actor.revision
  )
    return null;
  return row;
}

function sharedRows(card) {
  if (!["owner", "parent"].includes(card?._data?.role)) return [];
  const rows = presence(card)?.shared;
  if (!Array.isArray(rows)) return [];
  const seen = new Set();
  return rows.filter((row) => {
    const current = member(card, row?.member);
    if (
      !validEvidence(row) ||
      row.member === card._data.actor ||
      seen.has(row.member) ||
      current?.active !== true ||
      current.revision !== row.member_revision
    )
      return false;
    seen.add(row.member);
    return true;
  });
}

function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  const row = selfRow(card);
  if (
    !data?.actor ||
    !ROLES.has(data?.role) ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !Array.isArray(data?.settings?.modules) ||
    !data.settings.modules.includes("presence") ||
    !row ||
    !Array.isArray(presence(card)?.shared)
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
  };
}

function sameAccess(card, expected) {
  const current = access(card);
  return (
    Boolean(current && expected) &&
    JSON.stringify(current) === JSON.stringify(expected)
  );
}

function sameSelf(left, right) {
  return Boolean(
    left &&
    right &&
    left.member === right.member &&
    left.member_revision === right.member_revision &&
    left.binding_revision === right.binding_revision &&
    left.subscription_revision === right.subscription_revision &&
    left.enabled === right.enabled &&
    left.can_edit === right.can_edit,
  );
}

function sourceSnapshot(row) {
  return {
    member: row.member,
    member_revision: row.member_revision,
    binding_revision: row.binding_revision,
    subscription_revision: row.subscription_revision,
    enabled: row.enabled,
    can_edit: row.can_edit,
  };
}

function expectedRevision(source) {
  return source.subscription_revision === null
    ? 1
    : source.subscription_revision + 1;
}

function pendingAllowed(card, draft) {
  if (!sameAccess(card, draft?.access) || !draft?.pending) return false;
  const current = selfRow(card);
  if (
    !current ||
    current.member_revision !== draft.source.member_revision ||
    current.binding_revision !== draft.source.binding_revision
  )
    return false;
  return (
    sameSelf(current, draft.source) ||
    (current.enabled === draft.desired &&
      current.subscription_revision === expectedRevision(draft.source))
  );
}

function draftAllowed(card, draft, exact = true) {
  if (!sameAccess(card, draft?.access) || !draft?.source) return false;
  if (draft.pending) return pendingAllowed(card, draft);
  const current = selfRow(card);
  return Boolean(current && (!exact || sameSelf(current, draft.source)));
}

function projection(data) {
  const enabledModules = Array.isArray(data?.settings?.modules)
    ? data.settings.modules
    : [];
  const projectedMembers = Array.isArray(data?.members) ? data.members : [];
  const rows = data?.presence;
  const relevant = new Set([
    data?.actor,
    rows?.self?.member,
    ...(Array.isArray(rows?.shared)
      ? rows.shared.map((row) => row?.member)
      : []),
  ]);
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    module: enabledModules.includes("presence"),
    timezone: data?.settings?.timezone ?? null,
    members: projectedMembers
      .filter((item) => relevant.has(item?.id))
      .map(({ id, name, role, active, revision }) => ({
        id,
        name,
        role,
        active,
        revision,
      })),
    presence: rows
      ? {
          self: rows.self ?? null,
          shared: Array.isArray(rows.shared) ? rows.shared : null,
        }
      : null,
  };
}

export function reconcilePresenceRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(projection(previousData)) !==
    JSON.stringify(projection(card._data));
  let force =
    changed &&
    Boolean(card._presenceDraft || card.shadowRoot?.querySelector(".presence"));
  if (
    card._presenceDraft &&
    !draftAllowed(card, card._presenceDraft, !card._presenceDraft.pending)
  ) {
    card._presenceDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

function memberName(card, id, copy) {
  return member(card, id)?.name || copy.unavailable_member;
}

function appendDefinition(list, term, description) {
  list.append(node("dt", term), node("dd", description));
}

function evidenceLabel(row, copy) {
  return copy[row.status] || copy.unknown;
}

function reasonLabel(row, copy) {
  return copy[row.reason] || copy.unavailable;
}

function observedLabel(card, value) {
  if (typeof value !== "string" || !value) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const language = card?._config?.language || card?._hass?.language || "en";
  const timezone = card?._data?.settings?.timezone;
  if (typeof timezone !== "string" || !timezone) return null;
  try {
    return `${new Intl.DateTimeFormat(language, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: timezone,
    }).format(date)} · ${timezone}`;
  } catch (_error) {
    return null;
  }
}

function appendEvidence(card, item, row, copy) {
  item.append(
    node("p", `${copy.status}: ${evidenceLabel(row, copy)}`, "presence-status"),
  );
  item.append(
    node(
      "p",
      `${copy.reason}: ${reasonLabel(row, copy)}`,
      "sub presence-reason",
    ),
  );
  const observed = observedLabel(card, row.observed_at);
  if (observed)
    item.append(
      node("p", `${copy.observed}: ${observed}`, "sub presence-observation"),
    );
}

export function renderPresence(card, body) {
  if (!card || !body || !card._data) return;
  const currentAccess = access(card);
  if (!currentAccess) {
    card._presenceDraft = null;
    return;
  }
  if (
    card._presenceDraft &&
    !draftAllowed(card, card._presenceDraft, !card._presenceDraft.pending)
  ) {
    card._presenceDraft = null;
    card._actionError = "conflict";
  }

  const copy = copyOf(card);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null, exact = true) => {
    if (draft && card._presenceDraft !== draft) return false;
    if (
      !sameAccess(card, draft?.access || currentAccess) ||
      (draft && !draftAllowed(card, draft, exact && !draft.pending))
    ) {
      card._presenceDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected) card.render();
      return false;
    }
    return !detached() && Boolean(control?.isConnected) && !card._writing;
  };
  const localButton = (label, action, primary = false, draft = null) => {
    const button = card.button(
      label,
      () => {
        if (guard(button, draft)) action();
      },
      primary,
    );
    button.type = "button";
    return button;
  };
  const close = (draft) => {
    if (!guard(body, draft, false)) return;
    card._presenceDraft = null;
    card._actionError = null;
    card.render();
  };
  const run = async (draft) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending) {
      draft.pending = deepFreeze({
        action: "presence.access_set",
        payload: {
          member: draft.source.member,
          member_revision: draft.source.member_revision,
          binding_revision: draft.source.binding_revision,
          subscription_revision: draft.source.subscription_revision,
          enabled: draft.desired,
        },
        operation_id: crypto.randomUUID(),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    if (
      sameAccess(card, draft.access) &&
      card._presenceDraft === draft &&
      !card._actionError
    ) {
      card._presenceDraft = null;
      card.render();
    }
  };

  const section = node("section", null, "presence");
  section.append(node("style", STYLE));
  const guide = node("details", null, "presence-guide");
  guide.append(
    node("summary", copy.guide),
    node("p", copy.help, "sub"),
    node("p", copy.sharing, "sub"),
    node("p", copy.no_effects, "sub"),
    node("p", copy.source_help, "sub"),
  );
  section.append(guide);

  const draft = card._presenceDraft;
  if (draft) {
    const review = node("form", null, "item presence-review");
    review.append(node("h3", copy.review_title));
    const details = node("dl");
    appendDefinition(details, copy.person, draft.memberName);
    appendDefinition(
      details,
      copy.choice,
      draft.desired ? copy.share_choice : copy.stop_choice,
    );
    appendDefinition(
      details,
      copy.member_version,
      draft.source.member_revision,
    );
    appendDefinition(
      details,
      copy.binding_version,
      draft.source.binding_revision,
    );
    appendDefinition(
      details,
      copy.subscription_version,
      draft.source.subscription_revision === null
        ? copy.absent
        : draft.source.subscription_revision,
    );
    review.append(details);
    const confirmation = node("label", null, "presence-confirm");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.name = "confirmed";
    checkbox.required = true;
    checkbox.disabled = Boolean(draft.pending);
    if (draft.pending) checkbox.checked = true;
    confirmation.append(checkbox, node("span", copy.confirm));
    review.append(confirmation);
    const actions = node("div", null, "presence-actions");
    const submit = localButton(
      draft.pending ? copy.retry : copy.save,
      () => run(draft),
      true,
      draft,
    );
    submit.type = "submit";
    submit.disabled = !draft.pending;
    if (!draft.pending)
      checkbox.addEventListener("change", () => {
        if (!guard(checkbox, draft)) return;
        submit.disabled = !checkbox.checked || card._writing;
      });
    actions.append(
      submit,
      localButton(copy.cancel, () => close(draft), false, draft),
    );
    review.append(actions);
    review.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!submit.disabled && guard(review, draft)) run(draft);
    });
    section.append(review);
    body.append(section);
    return;
  }

  const own = selfRow(card);
  const ownItem = node("article", null, "item presence-self");
  ownItem.dataset.presenceMember = own.member;
  ownItem.append(
    node("h3", copy.your_presence),
    node("strong", memberName(card, own.member, copy)),
  );
  appendEvidence(card, ownItem, own, copy);
  ownItem.append(
    node(
      "p",
      `${copy.preference}: ${own.enabled ? copy.enabled : copy.disabled}`,
      "sub presence-preference",
    ),
  );
  if (
    own.can_edit &&
    (own.subscription_revision === null ||
      own.subscription_revision < Number.MAX_SAFE_INTEGER)
  ) {
    const open = localButton(own.enabled ? copy.disable : copy.enable, () => {
      const current = selfRow(card);
      if (!guard(open) || !sameSelf(current, own)) return;
      card._presenceDraft = {
        kind: "review",
        access: deepFreeze(clone(currentAccess)),
        source: deepFreeze(sourceSnapshot(own)),
        desired: !own.enabled,
        memberName: memberName(card, own.member, copy),
        pending: null,
      };
      card._actionError = null;
      card.render();
    });
    ownItem.append(open);
  } else if (!own.can_edit)
    ownItem.append(node("p", copy.unavailable_action, "sub"));
  section.append(ownItem);

  if (["owner", "parent"].includes(card._data.role)) {
    section.append(node("h3", copy.shared_presence));
    const shared = sharedRows(card);
    if (!shared.length)
      section.append(node("p", copy.no_shared, "sub presence-no-shared"));
    else {
      const list = node("div", null, "presence-list");
      for (const row of shared) {
        const item = node("article", null, "item presence-shared-row");
        item.dataset.presenceMember = row.member;
        item.append(node("strong", memberName(card, row.member, copy)));
        appendEvidence(card, item, row, copy);
        list.append(item);
      }
      section.append(list);
    }
  }
  body.append(section);
}
