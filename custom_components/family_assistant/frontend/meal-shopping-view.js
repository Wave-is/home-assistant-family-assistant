/* Parent-only, reviewable transfer from published meals to shopping records. */

import { MEAL_SHOPPING_COPY } from "./meal-shopping-copy.js";

const PARENTS = new Set(["owner", "parent"]);
const TERMINAL = new Set(["accepted", "covered"]);

const node = (tag, text, className) => {
  const value = document.createElement(tag);
  if (text !== undefined && text !== null) value.textContent = String(text);
  if (className) value.className = className;
  return value;
};

const copyOf = (card) => {
  const language = card._config?.language || card._hass?.language || "en";
  return MEAL_SHOPPING_COPY[language.split("-")[0]] || MEAL_SHOPPING_COPY.en;
};

const text = (copy, key, fallback) => copy[key] || fallback;
const clone = (value) => JSON.parse(JSON.stringify(value));

const LOCAL_STYLE = `
  .meal-shopping-section{display:grid;gap:14px;margin-top:18px}
  .meal-shopping-proposal,.meal-shopping-review{min-width:0}
  .meal-shopping-lines{display:grid;gap:10px;margin-top:12px}
  .meal-shopping-line{border-top:1px solid var(--divider-color,#dfe9e7);padding-top:10px;min-width:0}
  .meal-shopping-amounts{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:4px 12px;margin:8px 0 0}
  .meal-shopping-amounts dt{color:var(--secondary-text-color,#657d80)}
  .meal-shopping-amounts dd{margin:0;text-align:end;overflow-wrap:anywhere}
  .meal-shopping-status{display:inline-block;margin:6px 0}
  .meal-shopping-confirm{margin-top:12px}
  .meal-shopping-proposal>summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}
  @media(max-width:520px){.meal-shopping-amounts{font-size:14px;gap:8px}.meal-shopping-amounts dt{line-height:1.3}}
`;

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value))
    return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
}

function amount(value, unit) {
  return `${value ?? 0} ${unit || ""}`.trim();
}

function appendLines(parent, proposal, copy) {
  const list = node("div", null, "meal-shopping-lines");
  for (const line of Array.isArray(proposal.lines) ? proposal.lines : []) {
    const row = node("section", null, "meal-shopping-line");
    row.append(node("strong", line.name || ""));
    const values = node("dl", null, "meal-shopping-amounts");
    for (const [key, value] of [
      ["required", line.required],
      ["stock", line.stock],
      ["open_shopping", line.open_shopping],
      ["deficit", line.deficit],
      ["quantity", line.quantity],
    ]) {
      values.append(
        node("dt", text(copy, key, key)),
        node("dd", amount(value, line.unit)),
      );
    }
    row.append(values);
    if (line.shopping_id) {
      row.append(
        node(
          "p",
          `${text(copy, "shopping_id", "Shopping item")}: ${line.shopping_id}`,
          "sub meal-shopping-receipt-id",
        ),
      );
    }
    list.append(row);
  }
  parent.append(list);
}

function proposalHeading(parent, proposal, copy) {
  parent.append(
    node("h3", proposal.plan_title || text(copy, "plan", "Meal plan")),
    node(
      "p",
      `${text(copy, "week_start", "Week starting")}: ${proposal.week_start || ""}`,
      "sub",
    ),
    node(
      "p",
      text(copy, `status_${proposal.status}`, proposal.status || ""),
      `badge meal-shopping-status meal-shopping-status-${proposal.status || "unknown"}`,
    ),
  );
}

export function renderMealShopping(card, body) {
  if (!card || !body || !card._data) return;
  const data = card._data;
  const role = data.role;
  const actor = data.actor;
  const modules = data.settings?.modules || [];
  const parent = PARENTS.has(role) && Boolean(card.parent ?? true);
  const enabled = modules.includes("pantry") && modules.includes("shopping");

  if (!parent || !actor) {
    card._mealShoppingDraft = null;
    return;
  }

  const copy = copyOf(card);
  if (!enabled) {
    card._mealShoppingDraft = null;
    body.append(
      node(
        "div",
        text(copy, "module_off", "Pantry and Shopping are required."),
        "notice meal-shopping-disabled",
      ),
    );
    return;
  }

  const generation = card._generation;
  const entry = card._entry;
  const scope = JSON.stringify([generation, entry, actor, role]);
  const staleIdentity = () => {
    const liveModules = card._data?.settings?.modules || [];
    return (
      card._generation !== generation ||
      card._entry !== entry ||
      card._data?.actor !== actor ||
      card._data?.role !== role ||
      !PARENTS.has(card._data?.role) ||
      !Boolean(card.parent ?? true) ||
      !liveModules.includes("pantry") ||
      !liveModules.includes("shopping")
    );
  };
  const detached = () => !body.isConnected;
  const guardControl = (control) => {
    if (staleIdentity()) {
      // A focused form can suppress FamilyCard's normal refresh render.  Drop
      // its private snapshot immediately when the live identity loses access.
      card._mealShoppingDraft = null;
      if (!detached() && control?.isConnected) card.render();
      return false;
    }
    return !detached() && Boolean(control?.isConnected);
  };

  if (card._mealShoppingDraft?.scope !== scope) {
    if (card._mealShoppingDraft) card._actionError = "conflict";
    card._mealShoppingDraft = null;
  }

  // The meals editor owns the form area while it is open.  A failed transfer
  // remains private and retryable, but is not rendered beside another form.
  if (card._mealsDraft) return;

  const livePlans = () =>
    Array.isArray(card._data?.pantry?.meal_plans)
      ? card._data.pantry.meal_plans
      : [];
  const liveProposals = () =>
    Array.isArray(card._data?.pantry?.meal_shopping)
      ? card._data.pantry.meal_shopping
      : [];
  const plans = livePlans();
  const proposals = liveProposals();
  const terminalPlanIds = new Set(
    proposals
      .filter((proposal) => TERMINAL.has(proposal.status))
      .map((proposal) => proposal.source_plan_id),
  );
  const currentPlan = (id, revision) =>
    livePlans().find(
      (plan) =>
        plan.id === id &&
        plan.revision === revision &&
        plan.status === "published" &&
        !liveProposals().some(
          (proposal) =>
            proposal.source_plan_id === id && TERMINAL.has(proposal.status),
        ),
    );
  const currentProposal = (id, revision) => {
    const proposal = liveProposals().find(
      (proposal) =>
        proposal.id === id &&
        proposal.revision === revision &&
        proposal.status === "open" &&
        !liveProposals().some(
          (other) =>
            other.source_plan_id === proposal.source_plan_id &&
            TERMINAL.has(other.status),
        ),
    );
    if (!proposal) return undefined;
    const source = livePlans().find(
      (plan) =>
        plan.id === proposal.source_plan_id &&
        plan.revision === proposal.source_revision &&
        plan.status === "published",
    );
    return source ? proposal : undefined;
  };

  const localButton = (label, action, primary = false) => {
    const button = card.button(
      label,
      () => {
        if (!guardControl(button) || card._writing) return;
        action();
      },
      primary,
    );
    button.type = "button";
    return button;
  };

  const finish = async (draft, valid) => {
    if (
      staleIdentity() ||
      detached() ||
      card._writing ||
      card._mealShoppingDraft !== draft
    )
      return;
    if (!draft.pending) {
      if (!valid()) {
        card._mealShoppingDraft = null;
        card._actionError = "conflict";
        card.render();
        return;
      }
      draft.pending = deepFreeze({
        action: draft.action,
        payload: clone(draft.payload),
        operation_id: crypto.randomUUID(),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    // command() refreshes and replaces the body before resolving.  Detachment
    // here is expected; identity changes are the condition that forbids cleanup.
    if (
      !staleIdentity() &&
      card._mealShoppingDraft === draft &&
      !card._actionError
    ) {
      card._mealShoppingDraft = null;
      card.render();
    }
  };

  const beginPrepare = (plan) => {
    if (staleIdentity() || detached() || card._writing) return;
    const fresh = currentPlan(plan.id, plan.revision);
    if (!fresh) {
      card._actionError = "conflict";
      card.render();
      return;
    }
    const draft = {
      type: "prepare",
      action: "pantry.meal_shop_prepare",
      payload: { id: plan.id, revision: plan.revision },
      original: deepFreeze(clone(plan)),
      scope,
    };
    card._actionError = null;
    card._mealShoppingDraft = draft;
    void finish(draft, () => Boolean(currentPlan(plan.id, plan.revision)));
  };

  const beginAccept = (proposal) => {
    if (staleIdentity() || detached() || card._writing) return;
    const fresh = currentProposal(proposal.id, proposal.revision);
    if (!fresh) {
      card._actionError = "conflict";
      card.render();
      return;
    }
    card._actionError = null;
    card._mealShoppingDraft = {
      type: "accept",
      action: "pantry.meal_shop_accept",
      payload: { id: proposal.id, revision: proposal.revision },
      original: deepFreeze(clone(proposal)),
      reviewed: false,
      scope,
    };
    card.render();
  };

  const close = () => {
    if (staleIdentity() || detached()) return;
    card._mealShoppingDraft = null;
    card._actionError = null;
    card.render();
  };

  // Add calculation to the existing published meal-plan row, not to drafts or
  // archives.  A terminal receipt permanently removes it for that plan ID.
  let eligible = 0;
  for (const plan of plans) {
    if (plan.status !== "published" || terminalPlanIds.has(plan.id)) continue;
    eligible += 1;
    const row = [...body.querySelectorAll("[data-meal-plan]")].find(
      (candidate) => candidate.dataset.mealPlan === String(plan.id),
    );
    if (!row) continue;
    let actions = row.querySelector(":scope > .actions");
    if (!actions) {
      actions = node("div", null, "actions");
      row.append(actions);
    }
    actions.append(
      localButton(text(copy, "calculate", "Calculate shopping needs"), () =>
        beginPrepare(plan),
      ),
    );
  }

  const section = node("section", null, "meal-shopping-section");
  const style = node("style", LOCAL_STYLE);
  section.append(
    style,
    node("h2", text(copy, "title", "Meal plan shopping")),
    node(
      "p",
      text(copy, "prepare_hint", "Calculation creates a private proposal."),
      "sub",
    ),
  );
  if (!eligible && !terminalPlanIds.size) {
    section.append(
      node(
        "p",
        text(copy, "no_published", "Publish a meal plan first."),
        "sub",
      ),
    );
  }
  section.append(node("h3", text(copy, "proposals", "Private proposals")));
  if (!proposals.length) {
    section.append(
      node(
        "p",
        text(copy, "no_proposals", "No meal shopping proposals yet."),
        "sub",
      ),
    );
  }

  const draft = card._mealShoppingDraft;
  for (const proposal of proposals) {
    // The active review already shows this exact open calculation. Keep final
    // receipts accessible without repeating every line below the form.
    if (
      draft?.type === "accept" &&
      draft.original?.id === proposal.id &&
      proposal.status === "open"
    )
      continue;
    const archived = proposal.status !== "open";
    const row = node(
      archived ? "details" : "article",
      null,
      "item meal-shopping-proposal",
    );
    row.dataset.mealShoppingProposal = proposal.id;
    if (archived)
      row.append(
        node(
          "summary",
          `${proposal.plan_title || text(copy, "plan", "Meal plan")} · ${text(copy, `status_${proposal.status}`, proposal.status || "")}`,
        ),
      );
    proposalHeading(row, proposal, copy);
    appendLines(row, proposal, copy);
    row.append(
      node(
        "p",
        text(copy, "rounding_hint", "Shopping amounts may be rounded."),
        "sub",
      ),
    );
    if (proposal.status === "open") {
      row.append(
        localButton(
          text(copy, "accept", "Send to shopping list"),
          () => beginAccept(proposal),
          true,
        ),
      );
    } else if (TERMINAL.has(proposal.status)) {
      if (proposal.transfer_count !== undefined) {
        row.append(
          node(
            "p",
            `${text(copy, "transfer_count", "Shopping records created")}: ${proposal.transfer_count}`,
            "sub",
          ),
        );
      }
      const ids = [
        ...(Array.isArray(proposal.shopping_ids) ? proposal.shopping_ids : []),
        ...(proposal.lines || []).map((line) => line.shopping_id),
      ].filter((id, index, all) => Boolean(id) && all.indexOf(id) === index);
      if (ids.length) {
        row.append(
          node(
            "p",
            `${text(copy, "shopping_ids", "Created shopping items")}: ${ids.join(", ")}`,
            "sub meal-shopping-receipt-ids",
          ),
        );
      } else if (proposal.status === "covered") {
        row.append(
          node(
            "p",
            text(copy, "terminal_empty_hint", "Nothing was added."),
            "sub",
          ),
        );
      }
      row.append(
        node(
          "p",
          text(copy, "after_transfer_hint", "Edit shopping items manually."),
          "notice",
        ),
      );
    }
    section.append(row);
  }

  if (draft?.scope === scope) {
    const review = node("form", null, "item meal-shopping-review");
    review.dataset.mealShoppingForm = draft.type;
    if (draft.type === "accept") {
      proposalHeading(review, draft.original, copy);
      appendLines(review, draft.original, copy);
      review.append(
        node(
          "p",
          text(copy, "rounding_hint", "Shopping amounts may be rounded."),
          "sub",
        ),
        node(
          "p",
          text(copy, "accept_hint", "Only shopping records are created."),
          "notice",
        ),
      );
      const label = node("label", null, "check meal-shopping-confirm");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = "reviewed";
      checkbox.checked = Boolean(draft.reviewed);
      label.append(
        checkbox,
        node("span", text(copy, "confirm_accept", "I reviewed every amount.")),
      );
      review.append(label);
      checkbox.addEventListener("change", () => {
        if (!guardControl(checkbox) || draft.pending || card._writing) return;
        draft.reviewed = checkbox.checked;
      });
    } else {
      review.append(
        node("h3", draft.original?.title || text(copy, "plan", "Meal plan")),
        node(
          "p",
          `${text(copy, "week_start", "Week starting")}: ${draft.original?.week_start || ""}`,
          "sub",
        ),
        node(
          "p",
          text(copy, "prepare_hint", "Private proposal only."),
          "notice",
        ),
      );
    }

    const actions = node("div", null, "actions");
    const submit = localButton(
      draft.pending
        ? text(copy, "retry", "Retry exact request")
        : text(copy, "accept", "Send to shopping list"),
      () => {},
      true,
    );
    submit.type = "submit";
    actions.append(submit, localButton(text(copy, "cancel", "Cancel"), close));
    review.append(actions);
    review.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guardControl(review) || card._writing) return;
      if (draft.type === "accept") {
        const checkbox = review.elements.reviewed;
        if (!draft.pending) {
          if (!checkbox?.checked) return;
          draft.reviewed = true;
        }
        void finish(draft, () =>
          Boolean(currentProposal(draft.payload.id, draft.payload.revision)),
        );
      } else if (draft.pending) {
        void finish(draft, () => true);
      }
    });
    section.prepend(review);
  }

  body.append(section);
}
