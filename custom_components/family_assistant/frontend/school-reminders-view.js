/* Private, revision-bound school preparation reminder preferences. */

import { SCHOOL_REMINDERS_COPY } from "./school-reminders-copy.js";
import {inMemberContext,memberContextId} from "./panel-member-context.js";

const ROLES = new Set(["owner", "parent", "child"]);
const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/;

const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};
const clone = (value) => JSON.parse(JSON.stringify(value));
const deepFreeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
};

const STYLE = `
  .school-reminders{display:grid;gap:12px;margin-top:16px}.school-reminder-guide{margin:0}
  .school-reminder-list{display:grid;gap:8px}.school-reminder-row,.school-reminder-review{display:grid;gap:8px;min-width:0}
  .school-reminder-row p,.school-reminder-review p{margin:0;overflow-wrap:anywhere}
  .school-reminder-actions{display:flex;flex-wrap:wrap;gap:8px}.school-reminders .school-reminder-confirm{display:flex;flex-direction:row;justify-content:flex-start;gap:8px;align-items:flex-start}
  .school-reminder-confirm input{flex:0 0 auto;margin-top:3px}.school-reminder-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}
  .school-reminder-review dt{font-weight:600}.school-reminder-review dd{margin:0;overflow-wrap:anywhere}
  @media(max-width:520px){.school-reminder-actions>button{width:100%}.school-reminder-review dl{grid-template-columns:minmax(0,1fr)}.school-reminder-review dd{margin-bottom:4px}}
`;

function copyOf(card) {
  const language = card?._config?.language || card?._hass?.language || "en";
  return SCHOOL_REMINDERS_COPY[language.split("-")[0]] || SCHOOL_REMINDERS_COPY.en;
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

function reminderProjection(card) {
  const value = card?._data?.school?.preparation_reminders;
  return value && typeof value === "object" ? value : null;
}

function validPolicy(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      typeof value.enabled === "boolean" &&
      (value.days_before === 0 || value.days_before === 1) &&
      CLOCK.test(value.time) &&
      typeof value.timezone === "string" &&
      value.timezone,
  );
}

function validTarget(value) {
  return Boolean(
    value &&
      typeof value.member === "string" &&
      value.member &&
      validRevision(value.member_revision) &&
      validRevision(value.recipient_revision) &&
      typeof value.enabled === "boolean" &&
      (value.subscription_revision === null || validRevision(value.subscription_revision)) &&
      (!value.enabled || validRevision(value.subscription_revision)),
  );
}

function targets(card) {
  const rows = reminderProjection(card)?.self_targets;
  if (!Array.isArray(rows)) return [];
  const actor = member(card, card?._data?.actor);
  const seen = new Set();
  return rows.filter((row) => {
    const target = member(card, row?.member);
    if (
      !inMemberContext(card,row?.member) || !validTarget(row) ||
      seen.has(row.member) ||
      actor?.revision !== row.recipient_revision ||
      target?.active !== true ||
      target.role !== "child" ||
      target.revision !== row.member_revision ||
      (actor?.role === "child" && target.id !== actor.id)
    )
      return false;
    seen.add(row.member);
    return true;
  });
}

function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  const projection = reminderProjection(card);
  if (
    !data?.actor ||
    !ROLES.has(data?.role) ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !Array.isArray(data?.settings?.modules) ||
    !data.settings.modules.includes("school") ||
    !validPolicy(projection?.policy) ||
    !Array.isArray(projection?.self_targets)
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
  return Boolean(current && expected) && JSON.stringify(current) === JSON.stringify(expected);
}

function sameTarget(left, right) {
  return Boolean(
    left &&
      right &&
      left.member === right.member &&
      left.member_revision === right.member_revision &&
      left.recipient_revision === right.recipient_revision &&
      left.enabled === right.enabled &&
      left.subscription_revision === right.subscription_revision,
  );
}

function targetByMember(card, memberId) {
  return targets(card).find((item) => item.member === memberId) || null;
}

function expectedRevision(source) {
  return source.subscription_revision === null ? 1 : source.subscription_revision + 1;
}

function pendingAllowed(card, draft) {
  if (!sameAccess(card, draft?.access) || !draft?.pending) return false;
  const current = targetByMember(card, draft.source?.member);
  if (!current || current.member_revision !== draft.source.member_revision || current.recipient_revision !== draft.source.recipient_revision)
    return false;
  const preCommit = sameTarget(current, draft.source);
  const postCommit = Boolean(
    current.enabled === draft.desired &&
      current.subscription_revision === expectedRevision(draft.source),
  );
  return preCommit || postCommit;
}

function draftAllowed(card, draft, exact = true) {
  if (!sameAccess(card, draft?.access) || !draft?.source) return false;
  if (draft.pending) return pendingAllowed(card, draft);
  const current = targetByMember(card, draft.source.member);
  return Boolean(current && (!exact || sameTarget(current, draft.source)));
}

function projection(data) {
  const reminders = data?.school?.preparation_reminders;
  const enabledModules = Array.isArray(data?.settings?.modules) ? data.settings.modules : [];
  const projectedMembers = Array.isArray(data?.members) ? data.members : [];
  const relevantMembers = new Set([
    data?.actor,
    ...(Array.isArray(reminders?.self_targets)
      ? reminders.self_targets.map((item) => item?.member)
      : []),
  ]);
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    school: enabledModules.includes("school"),
    routines: enabledModules.includes("routines"),
    members: projectedMembers
      .filter((item) => relevantMembers.has(item?.id))
      .map(({ id, name, role, active, revision }) => ({
        id,
        name,
        role,
        active,
        revision,
      })),
    reminders: reminders
      ? {
          policy: reminders.policy ?? null,
          self_targets: reminders.self_targets ?? null,
        }
      : null,
  };
}

export function reconcileSchoolRemindersRefresh(card, previousData) {
  if (!card) return false;
  const changed = JSON.stringify(projection(previousData)) !== JSON.stringify(projection(card._data));
  let force = changed && Boolean(card._schoolReminderDraft || card.shadowRoot?.querySelector(".school-reminders"));
  if (card._schoolReminderDraft && !draftAllowed(card, card._schoolReminderDraft, !card._schoolReminderDraft.pending)) {
    card._schoolReminderDraft = null;
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

export function renderSchoolReminders(card, body) {
  if (!card || !body || !card._data) return;
  const currentAccess = access(card);
  if (!currentAccess) {
    card._schoolReminderDraft = null;
    return;
  }
  if (card._schoolReminderDraft && !draftAllowed(card, card._schoolReminderDraft, !card._schoolReminderDraft.pending)) {
    card._schoolReminderDraft = null;
    card._actionError = "conflict";
  }

  const copy = copyOf(card);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null, exact = true) => {
    if (draft && card._schoolReminderDraft !== draft) return false;
    if (!sameAccess(card, draft?.access || currentAccess) || (draft && !draftAllowed(card, draft, exact && !draft.pending))) {
      card._schoolReminderDraft = null;
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
    card._schoolReminderDraft = null;
    card._actionError = null;
    card.render();
  };
  const run = async (draft) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending) {
      const payload = {
        member: draft.source.member,
        member_revision: draft.source.member_revision,
        recipient_revision: draft.source.recipient_revision,
        subscription_revision: draft.source.subscription_revision,
        enabled: draft.desired,
      };
      draft.pending = deepFreeze({
        action: "school.preparation_reminder_access_set",
        payload,
        operation_id: crypto.randomUUID(),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    if (sameAccess(card, draft.access) && card._schoolReminderDraft === draft && !card._actionError) {
      card._schoolReminderDraft = null;
      card.render();
    }
  };

  const section = node("section", null, "school-reminders");
  section.append(node("style", STYLE), node("h3", copy.title));
  if(memberContextId(card)!==null)section.append(node("p",`${copy.recipient}: ${memberName(card,card._data.actor,copy)}`,"sub school-reminder-recipient"));
  const policy = reminderProjection(card).policy;
  section.append(node("p", policy.enabled ? copy.policy_on : copy.policy_off, "sub school-reminder-policy"));
  if (!card._data.settings.modules.includes("routines"))
    section.append(node("p", copy.routines_off, "sub school-reminder-routines-off"));
  section.append(
    node(
      "p",
      `${copy.schedule}: ${policy.time} · ${policy.days_before === 0 ? copy.same_day : copy.day_before} · ${copy.timezone}: ${policy.timezone}`,
      "sub school-reminder-schedule",
    ),
  );
  const guide = node("details", null, "school-reminder-guide");
  guide.append(node("summary", copy.guide), node("p", copy.help, "sub"), node("p", copy.no_effects, "sub"));
  section.append(guide);

  const draft = card._schoolReminderDraft;
  if (draft) {
    const review = node("form", null, "item school-reminder-review");
    review.append(node("h4", copy.review_title));
    const details = node("dl");
    appendDefinition(details, copy.recipient, memberName(card, draft.access.actor, copy));
    appendDefinition(details, copy.child, draft.targetName);
    appendDefinition(details, copy.choice, draft.desired ? copy.receive : copy.do_not_receive);
    appendDefinition(
      details,
      copy.version,
      draft.source.subscription_revision === null ? copy.absent : draft.source.subscription_revision,
    );
    review.append(details);
    const confirmation = node("label", null, "school-reminder-confirm");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.name = "confirmed";
    checkbox.required = true;
    checkbox.disabled = Boolean(draft.pending);
    if (draft.pending) checkbox.checked = true;
    confirmation.append(checkbox, node("span", copy.confirm));
    review.append(confirmation);
    const actions = node("div", null, "school-reminder-actions");
    const submit = localButton(draft.pending ? copy.retry : copy.save, () => run(draft), true, draft);
    submit.disabled = !draft.pending;
    if (!draft.pending)
      checkbox.addEventListener("change", () => {
        if (!guard(checkbox, draft)) return;
        submit.disabled = !checkbox.checked || card._writing;
      });
    actions.append(submit, localButton(copy.cancel, () => close(draft), false, draft));
    review.append(actions);
    review.addEventListener("submit", (event) => event.preventDefault());
    section.append(review);
    body.append(section);
    return;
  }

  const rows = targets(card);
  if (!rows.length) section.append(node("p", copy.no_targets, "sub"));
  else {
    const list = node("div", null, "school-reminder-list");
    for (const row of rows) {
      const item = node("article", null, "item school-reminder-row");
      item.dataset.schoolReminderMember = row.member;
      const targetName = memberName(card, row.member, copy);
      item.append(node("strong", targetName));
      item.append(node("p", `${copy.preference}: ${row.enabled ? copy.enabled : copy.disabled}`, "sub"));
      if (row.subscription_revision === null || row.subscription_revision < Number.MAX_SAFE_INTEGER) {
        const open = localButton(row.enabled ? copy.disable : copy.enable, () => {
          const current = targetByMember(card, row.member);
          if (!guard(open) || !sameTarget(current, row)) return;
          card._schoolReminderDraft = {
            kind: "review",
            access: deepFreeze(clone(currentAccess)),
            source: deepFreeze(clone(row)),
            desired: !row.enabled,
            targetName,
            pending: null,
          };
          card._actionError = null;
          card.render();
        });
        item.append(open);
      }
      list.append(item);
    }
    section.append(list);
  }
  body.append(section);
}
