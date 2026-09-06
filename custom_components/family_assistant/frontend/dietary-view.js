/* Private dietary profiles with explicit review and adult sharing consent. */

import { DIETARY_COPY } from "./dietary-copy.js";

const ACTIVE_ROLES = new Set(["owner", "parent", "adult", "child"]);
const COLLECTIONS = ["self", "managed_children", "shared_adults"];

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
const copyOf = (card) => {
  const language = card._config?.language || card._hass?.language || "en";
  return DIETARY_COPY[language.split("-")[0]] || DIETARY_COPY.en;
};
const text = (copy, key, fallback) => copy[key] || fallback;

const LOCAL_STYLE = `
  .dietary-section{margin-top:16px}.dietary-content{display:grid;gap:14px;padding-top:12px}
  .dietary-group{display:grid;gap:10px}.dietary-profile{min-width:0}
  .dietary-values{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px}
  .dietary-value{min-width:0}.dietary-value strong{display:block}.dietary-value ul{margin:5px 0 0;padding-inline-start:20px}
  .dietary-form{display:grid;gap:12px}.dietary-form textarea{box-sizing:border-box;min-height:76px;resize:vertical;width:100%}
  .dietary-review-list{margin:5px 0 0;padding-inline-start:20px}
  @media(max-width:520px){.dietary-values{grid-template-columns:minmax(0,1fr)}}
`;

function profilesOf(card) {
  const value = card._data?.pantry?.dietary_profiles;
  return value && typeof value === "object" ? value : null;
}

function rowsOf(card, collection) {
  const profiles = profilesOf(card);
  if (!profiles || !COLLECTIONS.includes(collection)) return [];
  if (collection === "self") return profiles.self ? [profiles.self] : [];
  return Array.isArray(profiles[collection]) ? profiles[collection] : [];
}

function currentRow(card, collection, memberId) {
  return rowsOf(card, collection).find((row) => row.member_id === memberId);
}

function currentMember(card, memberId) {
  return (card?._data?.members || []).find((member) => member.id === memberId);
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function sameVersion(left, right) {
  return (
    Boolean(left) &&
    Boolean(right) &&
    left.member_id === right.member_id &&
    left.status === right.status &&
    left.revision === right.revision
  );
}

function dietaryProjection(data) {
  const enabled = data?.settings?.modules?.includes("pantry");
  const profiles = data?.pantry?.dietary_profiles;
  const profileRows = profiles
    ? [
        ...(profiles.self ? [profiles.self] : []),
        ...(Array.isArray(profiles.managed_children)
          ? profiles.managed_children
          : []),
        ...(Array.isArray(profiles.shared_adults) ? profiles.shared_adults : []),
      ]
    : [];
  const relevantIds = new Set(profileRows.map((row) => row.member_id));
  const members = (data?.members || [])
    .filter((member) => relevantIds.has(member.id))
    .map(({ id, name, role, active, revision }) => ({
      id,
      name,
      role,
      active,
      revision,
    }));
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    enabled: Boolean(enabled),
    profiles: profiles && typeof profiles === "object" ? profiles : null,
    members,
  };
}

function draftAllowedAfterRefresh(card, draft) {
  const data = card?._data;
  const expectedScope = JSON.stringify([
    card?._generation,
    card?._entry,
    data?.actor,
    data?.role,
  ]);
  if (
    !draft ||
    draft.scope !== expectedScope ||
    !ACTIVE_ROLES.has(data?.role) ||
    !data?.actor ||
    !data?.settings?.modules?.includes("pantry") ||
    !data?.pantry?.dietary_profiles
  )
    return false;
  const row = currentRow(card, draft.collection, draft.memberId);
  const member = currentMember(card, draft.memberId);
  if (!row) return false;
  const capable =
    draft.kind === "access" ? row.can_share === true : row.can_edit === true;
  return (
    capable &&
    validRevision(draft.memberRevision) &&
    member?.revision === draft.memberRevision &&
    (Boolean(draft.pending) || sameVersion(draft.source, row))
  );
}

// FamilyCard calls this after replacing `_data`, before deciding whether a
// focused form may suppress render. A changed private projection must replace
// the old DOM even when the focused form belongs to another meals-card module.
export function reconcileDietaryRefresh(card, previousData) {
  if (!card) return false;
  let forceRender =
    JSON.stringify(dietaryProjection(previousData)) !==
    JSON.stringify(dietaryProjection(card._data));
  if (card._dietaryDraft && !draftAllowedAfterRefresh(card, card._dietaryDraft)) {
    card._dietaryDraft = null;
    card._actionError = "conflict";
    forceRender = true;
  }
  return forceRender;
}

function memberName(card, row, copy, collection) {
  const member = currentMember(card, row.member_id);
  if (member?.name) return member.name;
  return collection === "self"
    ? text(copy, "your_profile", "Your preferences")
    : text(copy, "family_member", "Family member");
}

function listValues(raw, field, seen) {
  const values = String(raw ?? "")
    .split(/\r?\n/)
    .filter((line) => line.trim());
  if (values.length > 30) throw new Error(field);
  return values.map((line) => {
    if (line.length > 80) throw new Error(field);
    const value = line.trim();
    const identity = value.toLocaleLowerCase("en-US");
    if (seen.has(identity)) throw new Error(field);
    seen.add(identity);
    return value;
  });
}

function savePayload(row, values) {
  const note = String(values.allergy_note ?? "");
  if (note.length > 1000) throw new Error("allergy_note");
  const seen = new Set();
  return {
    member_id: row.member_id,
    ...(row.revision === undefined ? {} : { revision: row.revision }),
    likes: listValues(values.likes, "likes", seen),
    dislikes: listValues(values.dislikes, "dislikes", seen),
    avoid: listValues(values.avoid, "avoid", seen),
    allergy_note: note.trim(),
  };
}

function initialValues(row) {
  return {
    likes: (row.likes || []).join("\n"),
    dislikes: (row.dislikes || []).join("\n"),
    avoid: (row.avoid || []).join("\n"),
    allergy_note: row.allergy_note || "",
  };
}

function appendList(parent, label, values, copy) {
  const block = node("div", null, "dietary-value");
  block.append(node("strong", label));
  if (!Array.isArray(values) || !values.length) {
    block.append(node("span", text(copy, "none", "None recorded"), "sub"));
  } else {
    const list = node("ul");
    for (const value of values) list.append(node("li", value));
    block.append(list);
  }
  parent.append(block);
}

function appendProfileValues(parent, row, copy) {
  const values = node("div", null, "dietary-values");
  appendList(values, text(copy, "likes", "Likes"), row.likes, copy);
  appendList(values, text(copy, "dislikes", "Dislikes"), row.dislikes, copy);
  appendList(values, text(copy, "avoid", "Avoid"), row.avoid, copy);
  const note = node("div", null, "dietary-value");
  note.append(
    node("strong", text(copy, "allergy_note", "Allergy note")),
    node(
      "span",
      row.allergy_note || text(copy, "none", "None recorded"),
      "sub",
    ),
  );
  values.append(note);
  parent.append(values);
}

function textarea(form, name, label, value, copy) {
  const wrapper = node("label", label);
  const input = node("textarea");
  input.name = name;
  input.value = value;
  input.dataset.dietaryField = name;
  input.maxLength = name === "allergy_note" ? 1000 : 2430;
  wrapper.append(input);
  if (name !== "allergy_note")
    wrapper.append(node("span", text(copy, "line_hint", "One item per line."), "sub"));
  form.append(wrapper);
  return input;
}

function appendReviewValues(parent, payload, copy) {
  for (const key of ["likes", "dislikes", "avoid"]) {
    const block = node("div", null, "dietary-value");
    block.append(node("strong", text(copy, key, key)));
    if (payload[key].length) {
      const list = node("ul", null, "dietary-review-list");
      for (const value of payload[key]) list.append(node("li", value));
      block.append(list);
    } else {
      block.append(node("span", text(copy, "none", "None recorded"), "sub"));
    }
    parent.append(block);
  }
  const note = node("div", null, "dietary-value");
  note.append(
    node("strong", text(copy, "allergy_note", "Allergy note")),
    node(
      "p",
      payload.allergy_note || text(copy, "none", "None recorded"),
      "sub",
    ),
  );
  parent.append(note);
}

export function renderDietaryProfiles(card, body) {
  if (!card || !body || !card._data) return;
  const role = card._data.role;
  const actor = card._data.actor;
  const enabled = card._data.settings?.modules?.includes("pantry");
  if (!ACTIVE_ROLES.has(role) || !actor || !enabled || !profilesOf(card)) {
    card._dietaryDraft = null;
    return;
  }

  const copy = copyOf(card);
  const generation = card._generation;
  const entry = card._entry;
  const scope = JSON.stringify([generation, entry, actor, role]);
  const staleIdentity = () =>
    card._generation !== generation ||
    card._entry !== entry ||
    card._data?.actor !== actor ||
    card._data?.role !== role ||
    !ACTIVE_ROLES.has(card._data?.role) ||
    !card._data?.settings?.modules?.includes("pantry") ||
    !profilesOf(card);
  const detached = () => !body.isConnected;

  const allowed = (draft, exact = false) => {
    const row = currentRow(card, draft.collection, draft.memberId);
    const member = currentMember(card, draft.memberId);
    if (!row) return false;
    const access = draft.kind === "access";
    const capability = access ? row.can_share === true : row.can_edit === true;
    return (
      capability &&
      validRevision(draft.memberRevision) &&
      member?.revision === draft.memberRevision &&
      (!exact || sameVersion(draft.source, row))
    );
  };
  const dropStale = (control, draft = card._dietaryDraft, exact = false) => {
    if (!staleIdentity() && (!draft || allowed(draft, exact))) return false;
    card._dietaryDraft = null;
    if (!detached() && control?.isConnected) card.render();
    return true;
  };
  const guard = (control, draft = null, exact = false) => {
    if (staleIdentity() || (draft && !allowed(draft, exact))) {
      dropStale(control, draft, exact);
      return false;
    }
    return !detached() && Boolean(control?.isConnected) && !card._writing;
  };

  if (card._dietaryDraft?.scope !== scope) {
    if (card._dietaryDraft) card._actionError = "conflict";
    card._dietaryDraft = null;
  } else if (
    card._dietaryDraft &&
    !allowed(card._dietaryDraft, !card._dietaryDraft.pending)
  ) {
    card._dietaryDraft = null;
    card._actionError = "conflict";
  }

  // Only one private editor is visible at a time on the meals card.
  if (card._mealsDraft || card._mealShoppingDraft) return;

  const localButton = (label, action, primary = false, draft = null) => {
    const button = card.button(
      label,
      () => {
        if (!guard(button, draft, Boolean(draft && !draft.pending))) return;
        action();
      },
      primary,
    );
    button.type = "button";
    return button;
  };

  const open = (kind, collection, row, targetName, extra = {}) => {
    if (staleIdentity() || detached() || card._writing) return;
    const current = currentRow(card, collection, row.member_id);
    const member = currentMember(card, row.member_id);
    const capability = kind === "access" ? current?.can_share : current?.can_edit;
    if (
      !capability ||
      !sameVersion(row, current) ||
      !validRevision(member?.revision)
    ) {
      card._actionError = "conflict";
      card.render();
      return;
    }
    card._actionError = null;
    card._dietaryDraft = {
      kind,
      collection,
      memberId: row.member_id,
      memberRevision: member.revision,
      targetName,
      source: deepFreeze(clone(row)),
      scope,
      ...extra,
    };
    if (kind === "clear") {
      card._dietaryDraft.payload = deepFreeze({
        member_id: row.member_id,
        revision: row.revision,
      });
    } else if (kind === "access") {
      card._dietaryDraft.payload = deepFreeze({
        member_id: row.member_id,
        revision: row.revision,
        member_revision: member.revision,
        share_with_parents: Boolean(extra.shareWithParents),
      });
    }
    card.render();
  };

  const close = () => {
    const draft = card._dietaryDraft;
    if (!guard(body, draft, false)) return;
    card._dietaryDraft = null;
    card._actionError = null;
    card.render();
  };

  const run = async (draft, action, payload) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending) {
      draft.pending = deepFreeze({
        action,
        payload: clone(payload),
        operation_id: crypto.randomUUID(),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    // FamilyCard refreshes and replaces body before resolving. Detachment is
    // expected here; only an identity/privacy change prevents cleanup.
    if (
      !staleIdentity() &&
      card._dietaryDraft === draft &&
      !card._actionError
    ) {
      card._dietaryDraft = null;
      card.render();
    }
  };

  const section = node("details", null, "dietary-section");
  section.open = Boolean(card._dietaryDraft);
  section.append(node("style", LOCAL_STYLE));
  section.append(node("summary", text(copy, "title", "Dietary preferences")));
  const content = node("div", null, "dietary-content");
  content.append(node("p", text(copy, "help", "Manual notes only."), "sub"));
  section.append(content);

  const appendRow = (collection, row) => {
    const name = memberName(card, row, copy, collection);
    const memberRevision = currentMember(card, row.member_id)?.revision;
    const memberIsCurrent = validRevision(memberRevision);
    const item = node("article", null, "item dietary-profile");
    item.dataset.dietaryMember = row.member_id;
    item.dataset.dietaryCollection = collection;
    item.append(
      node("strong", name),
      node("span", ` · ${text(copy, `status_${row.status}`, row.status)}`, "sub"),
    );
    if (row.status === "active") {
      appendProfileValues(item, row, copy);
      if (collection === "self" && row.can_share) {
        item.append(
          node(
            "p",
            row.share_with_parents
              ? text(copy, "shared", "Shared with parents")
              : text(copy, "not_shared", "Not shared with parents"),
            "sub",
          ),
        );
      }
    }
    const actions = node("div", null, "actions");
    if (row.can_edit && memberIsCurrent) {
      actions.append(
        localButton(text(copy, "edit", "Edit preferences"), () =>
          open("edit", collection, row, name, {
            values: initialValues(row),
          }),
        ),
      );
      if (row.status === "active")
        actions.append(
          localButton(text(copy, "clear", "Clear profile"), () =>
            open("clear", collection, row, name),
          ),
        );
    }
    if (
      collection === "self" &&
      row.status === "active" &&
      row.can_share &&
      memberIsCurrent
    ) {
      actions.append(
        localButton(
          row.share_with_parents
            ? text(copy, "stop_sharing", "Revoke sharing")
            : text(copy, "share", "Share with other parents"),
          () =>
            open("access", collection, row, name, {
              shareWithParents: !row.share_with_parents,
            }),
        ),
      );
    }
    if (actions.children.length) item.append(actions);
    else item.append(node("p", text(copy, "read_only", "Read-only"), "sub"));
    return item;
  };

  const draft = card._dietaryDraft;
  if (!draft) {
    const groups = [
      ["self", text(copy, "your_profile", "Your preferences")],
      ["managed_children", text(copy, "managed_children", "Managed children")],
      ["shared_adults", text(copy, "shared_adults", "Shared adults")],
    ];
    for (const [collection, label] of groups) {
      const rows = rowsOf(card, collection);
      if (!rows.length) continue;
      const group = node("section", null, "dietary-group");
      group.append(node("h3", label));
      for (const row of rows) group.append(appendRow(collection, row));
      content.append(group);
    }
  }
  if (draft?.scope === scope) {
    const form = node("form", null, "item dietary-form");
    form.dataset.dietaryForm = draft.kind;
    if (draft.kind === "edit") {
      form.append(node("h3", draft.targetName));
      for (const key of ["likes", "dislikes", "avoid", "allergy_note"]) {
        const input = textarea(
          form,
          key,
          text(copy, key, key),
          draft.values[key],
          copy,
        );
        const remember = () => {
          if (!guard(input, draft, true)) return;
          draft.values[key] = input.value;
        };
        input.addEventListener("input", remember);
        input.addEventListener("change", remember);
      }
      const actions = node("div", null, "actions");
      const review = localButton(text(copy, "review", "Review changes"), () => {}, true, draft);
      review.type = "submit";
      actions.append(review, localButton(text(copy, "cancel", "Cancel"), close, false, draft));
      form.append(actions);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!guard(form, draft, true)) return;
        try {
          for (const input of form.querySelectorAll("textarea"))
            draft.values[input.name] = input.value;
          draft.payload = deepFreeze(savePayload(draft.source, draft.values));
          draft.kind = "save";
          draft.reviewed = false;
          card._actionError = null;
          card.render();
        } catch {
          card._actionError = "invalid_field";
          card.render();
        }
      });
    } else {
      const titleKey =
        draft.kind === "save"
          ? "save_title"
          : draft.kind === "clear"
            ? "clear_title"
            : "share_title";
      form.append(
        node("h3", text(copy, titleKey, "Review dietary preferences")),
        node("p", draft.targetName, "sub"),
      );
      if (draft.kind === "save") appendReviewValues(form, draft.payload, copy);
      if (draft.kind === "clear")
        form.append(node("p", text(copy, "clear_hint", "Clear current content."), "sub"));
      if (draft.kind === "access")
        form.append(
          node(
            "p",
            draft.payload.share_with_parents
              ? text(copy, "share_next", "Parents will be able to read this profile.")
              : text(copy, "revoke_next", "Parent access will be revoked."),
            "sub",
          ),
        );
      const label = node("label", null, "check");
      const checkbox = node("input");
      checkbox.type = "checkbox";
      checkbox.name = "reviewed";
      checkbox.checked = Boolean(draft.reviewed);
      checkbox.disabled = Boolean(draft.pending);
      const confirmKey =
        draft.kind === "save"
          ? "confirm_save"
          : draft.kind === "clear"
            ? "confirm_clear"
            : draft.payload.share_with_parents
              ? "confirm_share"
              : "confirm_revoke";
      label.append(checkbox, node("span", text(copy, confirmKey, "Confirm")));
      form.append(label);
      checkbox.addEventListener("change", () => {
        if (!guard(checkbox, draft, !draft.pending) || draft.pending) return;
        draft.reviewed = checkbox.checked;
      });
      const actions = node("div", null, "actions");
      const submit = localButton(
        draft.pending
          ? text(copy, "retry", "Retry exact request")
          : text(copy, "confirm", "Confirm"),
        () => {},
        true,
        draft,
      );
      submit.type = "submit";
      actions.append(submit, localButton(text(copy, "cancel", "Cancel"), close, false, draft));
      form.append(actions);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!guard(form, draft, !draft.pending)) return;
        if (!draft.pending) {
          if (!checkbox.checked) return;
          draft.reviewed = true;
        }
        if (draft.kind === "save")
          void run(draft, "pantry.dietary_save", draft.payload);
        else if (draft.kind === "clear")
          void run(draft, "pantry.dietary_clear", draft.payload);
        else
          void run(draft, "pantry.dietary_access_set", draft.payload);
      });
    }
    content.prepend(form);
  }

  body.append(section);
}
