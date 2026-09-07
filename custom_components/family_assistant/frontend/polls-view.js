/* Role-scoped family polls with frozen, explicitly reviewed mutations. */

import { wallTime, wallTimeCandidates } from "./local-time.js";
import { POLLS_COPY } from "./polls-copy.js";

const PARENTS = new Set(["owner", "parent"]);

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
  .polls-section,.polls-list,.poll-form,.poll-review,.poll-fields{display:grid;gap:12px;min-width:0}
  .polls-section{margin-top:16px}.polls-section h3,.polls-section h4,.polls-section p{overflow-wrap:anywhere}
  .polls-section h3,.polls-section h4,.poll-form>p,.poll-review p{margin:2px 0}
  .poll-actions{display:flex;gap:8px;flex-wrap:wrap}.poll-actions>button{max-width:100%}
  .poll-options,.poll-results{margin:4px 0;padding-inline-start:22px}.poll-option-editor{display:block;min-width:0}
  .poll-option-editor>*+*{margin-top:8px}.poll-eligible{display:grid!important;grid-template-columns:minmax(0,1fr)!important;gap:6px}
  .poll-choice{display:flex!important;flex-direction:row!important;align-items:flex-start!important;gap:8px!important}
  .poll-choice input{flex:0 0 auto;margin-top:3px}.poll-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}
  .poll-review dt{font-weight:600}.poll-review dd{margin:0;overflow-wrap:anywhere}.poll-private{white-space:normal}
  @media(max-width:520px){.poll-actions>button{flex:1 1 100%}.poll-review dl{grid-template-columns:minmax(0,1fr)}.poll-review dd{margin-bottom:4px}}
`;

function copyOf(card) {
  const language = card?._config?.language || card?._hass?.language || "en";
  return POLLS_COPY[language.split("-")[0]] || POLLS_COPY.en;
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

function currentMember(card, id) {
  const value = member(card, id);
  return value?.active === true &&
    value.role !== "guest" &&
    validRevision(value.revision)
    ? value
    : null;
}

function pollsData(data) {
  const value = data?.polls;
  return value &&
    Array.isArray(value.open) &&
    Array.isArray(value.closed) &&
    Array.isArray(value.archived)
    ? value
    : null;
}

function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  if (
    !data?.actor ||
    data.role === "guest" ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !Array.isArray(data?.settings?.modules) ||
    !data.settings.modules.includes("polls") ||
    typeof data.settings.timezone !== "string" ||
    !data.settings.timezone ||
    !pollsData(data)
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
    timezone: data.settings.timezone,
  };
}

function sameAccess(card, expected) {
  const current = access(card);
  return (
    Boolean(current && expected) &&
    JSON.stringify(current) === JSON.stringify(expected)
  );
}

function allPolls(card) {
  const data = pollsData(card?._data);
  return data ? [...data.open, ...data.closed, ...data.archived] : [];
}

function pollById(card, id) {
  return allPolls(card).find((item) => item?.id === id) || null;
}

function samePoll(left, right) {
  return (
    Boolean(left && right) &&
    left.id === right.id &&
    left.revision === right.revision &&
    left.status === right.status
  );
}

function ballotSnapshot(row) {
  const ballot = row?.own_ballot;
  return ballot &&
    typeof ballot.option_id === "string" &&
    validRevision(ballot.revision)
    ? { option_id: ballot.option_id, revision: ballot.revision }
    : null;
}

function sameBallot(left, right) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function memberSnapshot(card, id) {
  const item = currentMember(card, id);
  return item ? { member: item.id, revision: item.revision } : null;
}

function sameMemberSnapshot(card, snapshot) {
  return (
    Boolean(snapshot) &&
    JSON.stringify(memberSnapshot(card, snapshot.member)) ===
      JSON.stringify(snapshot)
  );
}

function expectedBallotRevision(source) {
  return source.ballot === null ? 1 : source.ballot.revision + 1;
}

function pendingAllowed(card, draft) {
  if (!sameAccess(card, draft?.access) || !draft?.pending) return false;
  if (draft.intent === "create") return PARENTS.has(card._data.role);
  const row = pollById(card, draft.source?.id);
  if (draft.intent === "vote") {
    if (!row || !["open", "closed"].includes(row.status)) return false;
    if (row.definition_revision !== draft.source.definitionRevision)
      return false;
    const currentBallot = ballotSnapshot(row);
    const preCommit =
      row.status === "open" &&
      row.can_vote === true &&
      sameBallot(currentBallot, draft.source.ballot);
    const postCommit =
      currentBallot?.option_id === draft.payload.option_id &&
      currentBallot.revision === expectedBallotRevision(draft.source);
    return preCommit || postCommit;
  }
  if (draft.intent === "close") {
    return (
      Boolean(row) &&
      ((row.status === "open" &&
        samePoll(row, draft.source) &&
        row.can_close === true) ||
        (row.status === "closed" &&
          row.revision === draft.source.revision + 1) ||
        (row.status === "archived" &&
          row.revision >= draft.source.revision + 2))
    );
  }
  if (draft.intent === "archive") {
    return (
      Boolean(row) &&
      ((row.status === "closed" &&
        samePoll(row, draft.source) &&
        row.can_archive === true) ||
        (row.status === "archived" &&
          row.revision === draft.source.revision + 1))
    );
  }
  if (draft.intent === "purge") {
    return (
      !row ||
      (row.status === "archived" &&
        samePoll(row, draft.source) &&
        row.can_purge === true)
    );
  }
  return false;
}

function draftAllowed(card, draft, exact = true) {
  if (!sameAccess(card, draft?.access)) return false;
  if (draft.pending) return pendingAllowed(card, draft);
  const parent = PARENTS.has(card._data.role);
  if (draft.intent === "create") {
    return (
      parent &&
      (draft.eligibleSnapshots || []).every((item) =>
        sameMemberSnapshot(card, item),
      )
    );
  }
  const row = pollById(card, draft.source?.id);
  if (draft.intent === "vote") {
    return (
      Boolean(row?.can_vote) &&
      row.status === "open" &&
      row.definition_revision === draft.source.definitionRevision &&
      (!exact || sameBallot(ballotSnapshot(row), draft.source.ballot))
    );
  }
  if (draft.intent === "close")
    return (
      parent &&
      row?.status === "open" &&
      row.can_close === true &&
      (!exact || samePoll(row, draft.source))
    );
  if (draft.intent === "archive")
    return (
      parent &&
      row?.status === "closed" &&
      row.can_archive === true &&
      (!exact || samePoll(row, draft.source))
    );
  if (draft.intent === "purge")
    return (
      card._data.role === "owner" &&
      row?.status === "archived" &&
      row.can_purge === true &&
      (!exact || samePoll(row, draft.source))
    );
  return false;
}

function refreshProjection(data) {
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    modules: Array.isArray(data?.settings?.modules)
      ? data.settings.modules.filter((item) => item === "polls")
      : [],
    timezone: data?.settings?.timezone ?? null,
    members: (data?.members || []).map(
      ({ id, name, role, active, revision }) => ({
        id,
        name,
        role,
        active,
        revision,
      }),
    ),
    polls: data?.polls ?? null,
  };
}

export function reconcilePollsRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(refreshProjection(previousData)) !==
    JSON.stringify(refreshProjection(card._data));
  let force =
    changed &&
    Boolean(
      card._pollsDraft || card.shadowRoot?.querySelector(".polls-section"),
    );
  if (
    card._pollsDraft &&
    !draftAllowed(card, card._pollsDraft, !card._pollsDraft.pending)
  ) {
    card._pollsDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

function rawText(value, maximum) {
  if (typeof value !== "string" || value.length > maximum)
    throw new Error("invalid");
  const result = value.trim();
  if (!result) throw new Error("invalid");
  return result;
}

function normalizedOptions(values) {
  if (!Array.isArray(values) || values.length < 2 || values.length > 10)
    throw new Error("invalid");
  const labels = values.map((value) => rawText(value, 120));
  const folded = labels.map((value) => value.toLocaleLowerCase());
  if (new Set(folded).size !== folded.length) throw new Error("invalid");
  return labels;
}

function displayTime(card, value) {
  try {
    return `${wallTime(value, card._data.settings.timezone).replace("T", " ")} · ${card._data.settings.timezone}`;
  } catch {
    return card._data.settings.timezone;
  }
}

function optionLabel(row, optionId, copy) {
  return (
    row?.options?.find((item) => item?.id === optionId)?.label || copy.no_vote
  );
}

function memberName(card, id, copy) {
  return member(card, id)?.name || copy.unavailable_member;
}

function definition(list, key, value) {
  list.append(node("dt", key), node("dd", value));
}

function button(card, label, action, primary, guard) {
  const control = card.button(
    label,
    () => {
      if (guard(control)) action();
    },
    primary,
  );
  control.type = "button";
  return control;
}

function choiceList(row) {
  return Array.isArray(row?.options)
    ? row.options.filter(
        (item) =>
          item && typeof item.id === "string" && typeof item.label === "string",
      )
    : [];
}

function createDeadlineControls(form, card, draft, copy, guard) {
  const input = card.input(
    form,
    "closes_at",
    copy.closes_at,
    "datetime-local",
    draft.deadlineWall,
  );
  const gap = node("p", copy.dst_gap, "notice");
  const ambiguous = node("p", copy.dst_ambiguous, "notice");
  gap.setAttribute("role", "alert");
  ambiguous.setAttribute("role", "alert");
  gap.hidden = true;
  ambiguous.hidden = true;
  const foldLabel = node("label", copy.dst_choice);
  const fold = node("select");
  fold.name = "deadline_fold";
  for (const [value, label] of [
    ["", copy.dst_choose],
    ["0", copy.dst_first],
    ["1", copy.dst_second],
  ]) {
    const option = node("option", label);
    option.value = value;
    fold.append(option);
  }
  fold.value = draft.deadlineFold === null ? "" : String(draft.deadlineFold);
  foldLabel.append(fold);
  foldLabel.hidden = true;
  form.append(gap, ambiguous, foldLabel);
  const candidates = () => {
    gap.hidden = true;
    ambiguous.hidden = true;
    foldLabel.hidden = true;
    if (!input.value) return [];
    try {
      const values = wallTimeCandidates(input.value, draft.access.timezone);
      if (!values.length) gap.hidden = false;
      if (values.length === 2) foldLabel.hidden = false;
      return values;
    } catch {
      gap.hidden = false;
      return [];
    }
  };
  input.addEventListener("input", () => {
    if (!guard(input)) return;
    draft.deadlineWall = input.value;
    draft.deadlineFold = null;
    fold.value = "";
    candidates();
  });
  fold.addEventListener("change", () => {
    if (!guard(fold)) return;
    draft.deadlineFold = fold.value === "" ? null : Number(fold.value);
    ambiguous.hidden = true;
  });
  return () => {
    const values = candidates();
    if (!values.length) throw new Error("invalid");
    if (values.length === 2 && ![0, 1].includes(draft.deadlineFold)) {
      ambiguous.hidden = false;
      throw new Error("invalid");
    }
    const result = values[draft.deadlineFold ?? 0];
    const delay = Date.parse(result) - Date.now();
    if (
      !Number.isFinite(delay) ||
      delay < 5 * 60_000 ||
      delay > 30 * 24 * 60 * 60_000
    )
      throw new Error("invalid");
    return result;
  };
}

export function renderPolls(card, body) {
  if (!card || !body || !card._data) return;
  const currentAccess = access(card);
  if (!currentAccess) {
    card._pollsDraft = null;
    return;
  }
  if (
    card._pollsDraft &&
    !draftAllowed(card, card._pollsDraft, !card._pollsDraft.pending)
  ) {
    card._pollsDraft = null;
    card._actionError = "conflict";
  }
  const copy = copyOf(card);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null, exact = true) => {
    if (draft && card._pollsDraft !== draft) return false;
    if (
      !sameAccess(card, draft?.access || currentAccess) ||
      (draft && !draftAllowed(card, draft, exact && !draft.pending))
    ) {
      card._pollsDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected) card.render();
      return false;
    }
    return !detached() && Boolean(control?.isConnected) && !card._writing;
  };
  const closeDraft = (draft) => {
    if (!guard(body, draft, false)) return;
    card._pollsDraft = null;
    card._actionError = null;
    card.render();
  };
  const startReview = (draft, action, payload, review) => {
    draft.action = action;
    draft.payload = deepFreeze(payload);
    draft.review = deepFreeze(review);
    draft.kind = "review";
    draft.confirmed = false;
    card._actionError = null;
    card.render();
  };
  const run = async (draft) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending) {
      draft.pending = deepFreeze({
        action: draft.action,
        payload: draft.payload,
        operation_id: crypto.randomUUID(),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    if (
      sameAccess(card, draft.access) &&
      card._pollsDraft === draft &&
      !card._actionError
    ) {
      card._pollsDraft = null;
      card.render();
    }
  };
  const section = node("section", null, "polls-section");
  section.append(node("style", STYLE));
  const guide = node("details");
  guide.append(
    node("summary", copy.help),
    node("p", copy.privacy_warning, "notice poll-private"),
    node("p", copy.no_automatic_effects, "sub"),
  );
  section.append(guide);
  const draft = card._pollsDraft;

  const localButton = (label, action, primary = false, targetDraft = null) =>
    button(card, label, action, primary, (control) =>
      guard(control, targetDraft),
    );

  if (draft?.kind === "create") {
    const form = node("form", null, "item poll-form");
    form.dataset.pollForm = "create";
    form.append(
      node("h3", copy.create),
      node("p", copy.privacy_warning, "notice"),
    );
    const fields = node("div", null, "poll-fields");
    const question = card.input(
      fields,
      "question",
      copy.question,
      "text",
      draft.question,
    );
    question.maxLength = 240;
    question.addEventListener("input", () => {
      if (guard(question, draft)) draft.question = question.value;
    });
    form.append(fields, node("h4", copy.options));
    const options = node("div", null, "polls-list");
    draft.options.forEach((value, index) => {
      const row = node("fieldset", null, "poll-option-editor");
      const legend = node("legend", `${copy.option} ${index + 1}`);
      const input = node("input");
      input.type = "text";
      input.value = value;
      input.maxLength = 120;
      input.setAttribute("aria-label", `${copy.option} ${index + 1}`);
      input.addEventListener("input", () => {
        if (guard(input, draft)) draft.options[index] = input.value;
      });
      const remove = localButton(
        copy.remove_option,
        () => {
          if (draft.options.length <= 2) return;
          draft.options.splice(index, 1);
          card.render();
        },
        false,
        draft,
      );
      remove.disabled = draft.options.length <= 2;
      row.append(legend, input, remove);
      options.append(row);
    });
    form.append(options);
    if (draft.options.length < 10)
      form.append(
        localButton(
          copy.add_option,
          () => {
            draft.options.push("");
            card.render();
          },
          false,
          draft,
        ),
      );
    const eligible = node("fieldset", null, "poll-eligible");
    eligible.append(node("legend", copy.eligible));
    for (const item of members(card).filter((candidate) =>
      currentMember(card, candidate.id),
    )) {
      const label = node("label", null, "poll-choice");
      const checkbox = node("input");
      checkbox.type = "checkbox";
      checkbox.value = item.id;
      checkbox.checked = draft.eligible.includes(item.id);
      label.append(checkbox, node("span", item.name));
      eligible.append(label);
      checkbox.addEventListener("change", () => {
        if (!guard(checkbox, draft)) return;
        draft.eligible = [
          ...eligible.querySelectorAll('input[type="checkbox"]'),
        ]
          .filter((control) => control.checked)
          .map((control) => control.value);
        draft.eligibleSnapshots = draft.eligible.map((id) =>
          memberSnapshot(card, id),
        );
      });
    }
    form.append(eligible);
    const deadline = createDeadlineControls(
      form,
      card,
      draft,
      copy,
      (control) => guard(control, draft),
    );
    const actions = node("div", null, "poll-actions");
    const submit = localButton(copy.review_create, () => {}, true, draft);
    submit.type = "submit";
    actions.append(
      submit,
      localButton(copy.cancel, () => closeDraft(draft), false, draft),
    );
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(form, draft)) return;
      try {
        const optionLabels = normalizedOptions(draft.options);
        if (draft.eligible.length < 1 || draft.eligible.length > 50)
          throw new Error("invalid");
        const snapshots = draft.eligible.map((id) => memberSnapshot(card, id));
        if (snapshots.some((item) => !item)) throw new Error("invalid");
        draft.eligibleSnapshots = snapshots;
        const payload = {
          actor_revision: draft.access.actorRevision,
          question: rawText(question.value, 240),
          options: optionLabels,
          eligible: snapshots,
          closes_at: deadline(),
          confirm_private_ballot_limits: true,
        };
        startReview(draft, "polls.create", payload, {
          question: payload.question,
          options: clone(payload.options),
          eligible: snapshots.map((item) =>
            memberName(card, item.member, copy),
          ),
          closes: displayTime(card, payload.closes_at),
        });
      } catch {
        card._actionError = "invalid_field";
        card.render();
      }
    });
    section.append(form);
  } else if (draft?.kind === "vote") {
    const row = pollById(card, draft.source.id);
    const form = node("form", null, "item poll-form");
    form.dataset.pollForm = "vote";
    form.append(
      node("h3", row.question),
      node("p", copy.privacy_warning, "notice"),
    );
    const choices = node("fieldset", null, "poll-eligible");
    choices.append(node("legend", copy.options));
    for (const item of choiceList(row)) {
      const label = node("label", null, "poll-choice");
      const radio = node("input");
      radio.type = "radio";
      radio.name = "option_id";
      radio.value = item.id;
      radio.checked = draft.optionId === item.id;
      label.append(radio, node("span", item.label));
      choices.append(label);
      radio.addEventListener("change", () => {
        if (guard(radio, draft)) draft.optionId = radio.value;
      });
    }
    form.append(choices);
    const actions = node("div", null, "poll-actions");
    const submit = localButton(copy.review_vote, () => {}, true, draft);
    submit.type = "submit";
    actions.append(
      submit,
      localButton(copy.cancel, () => closeDraft(draft), false, draft),
    );
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(form, draft)) return;
      const selected = choiceList(row).find(
        (item) => item.id === draft.optionId,
      );
      if (!selected || selected.id === draft.source.ballot?.option_id) {
        card._actionError = "invalid_field";
        card.render();
        return;
      }
      const payload = {
        id: row.id,
        definition_revision: draft.source.definitionRevision,
        voter_revision: draft.access.actorRevision,
        option_id: selected.id,
        ballot_revision: draft.source.ballot?.revision ?? null,
      };
      startReview(draft, "polls.vote", payload, {
        question: row.question,
        option: selected.label,
      });
    });
    section.append(form);
  } else if (draft?.kind === "review") {
    const form = node("form", null, "item poll-form poll-review");
    form.dataset.pollForm = "review";
    const headings = {
      create: copy.review_create,
      vote: copy.review_vote,
      close: copy.review_close,
      archive: copy.review_archive,
      purge: copy.review_purge,
    };
    form.append(node("h3", headings[draft.intent]));
    const list = node("dl");
    definition(list, copy.question, draft.review.question);
    if (draft.intent === "create") {
      definition(list, copy.options, draft.review.options.join(" · "));
      definition(list, copy.eligible, draft.review.eligible.join(", "));
      definition(list, copy.closes_at, draft.review.closes);
    } else if (draft.intent === "vote") {
      definition(list, copy.your_vote, draft.review.option);
    } else {
      definition(list, copy.revision, draft.source.revision);
    }
    form.append(list, node("p", copy.privacy_warning, "notice"));
    if (draft.intent === "purge")
      form.append(node("p", copy.purge_warning, "notice"));
    if (draft.pending) form.append(node("p", copy.retry_hint, "notice"));
    const confirmations = {
      create: copy.confirm_create,
      vote: copy.confirm_vote,
      close: copy.confirm_close,
      archive: copy.confirm_archive,
      purge: copy.confirm_purge,
    };
    const label = node("label", null, "poll-choice");
    const confirmed = node("input");
    confirmed.type = "checkbox";
    confirmed.name = "confirmed";
    confirmed.checked = draft.confirmed === true;
    confirmed.disabled = Boolean(draft.pending);
    label.append(confirmed, node("span", confirmations[draft.intent]));
    confirmed.addEventListener("change", () => {
      if (guard(confirmed, draft) && !draft.pending)
        draft.confirmed = confirmed.checked;
    });
    form.append(label);
    const actions = node("div", null, "poll-actions");
    const submit = localButton(
      draft.pending ? copy.retry : copy.save,
      () => {},
      true,
      draft,
    );
    submit.type = "submit";
    actions.append(
      submit,
      localButton(copy.cancel, () => closeDraft(draft), false, draft),
    );
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(form, draft, !draft.pending)) return;
      if (!draft.pending && !confirmed.checked) return;
      draft.confirmed = true;
      void run(draft);
    });
    section.append(form);
  } else {
    if (PARENTS.has(card._data.role)) {
      section.append(
        localButton(
          copy.create,
          () => {
            const next = {
              intent: "create",
              kind: "create",
              access: deepFreeze(clone(currentAccess)),
              question: "",
              options: ["", ""],
              eligible: [],
              eligibleSnapshots: [],
              deadlineWall: "",
              deadlineFold: null,
            };
            card._pollsDraft = next;
            card._actionError = null;
            card.render();
          },
          true,
        ),
      );
    }

    const renderRow = (row, status) => {
      if (
        !row ||
        row.status !== status ||
        typeof row.id !== "string" ||
        !validRevision(row.revision)
      )
        return null;
      const item = node(
        status === "archived" ? "details" : "article",
        null,
        "item poll-row",
      );
      item.dataset.pollId = row.id;
      if (status === "archived") item.append(node("summary", row.question));
      else item.append(node("h4", row.question));
      const content =
        status === "archived" ? node("div", null, "poll-fields") : item;
      content.append(
        node(
          "p",
          `${copy[`status_${status}`]} · ${copy.revision} ${row.revision}`,
          "sub",
        ),
        node(
          "p",
          `${copy.closes_at}: ${displayTime(card, row.closes_at)}`,
          "sub",
        ),
      );
      if (status === "open") {
        const labels = node("ul", null, "poll-options");
        for (const option of choiceList(row))
          labels.append(node("li", option.label));
        content.append(labels, node("p", copy.results_hidden, "sub"));
      } else {
        const results = node("ul", null, "poll-results");
        for (const option of choiceList(row)) {
          const result = (row.results || []).find(
            (entry) => entry?.option_id === option.id,
          );
          results.append(
            node(
              "li",
              `${option.label}: ${Number.isSafeInteger(result?.count) ? result.count : 0}`,
            ),
          );
        }
        content.append(
          node(
            "p",
            `${copy.results} · ${copy.cast_count}: ${row.cast_count ?? 0}`,
            "sub",
          ),
          results,
        );
      }
      if (status !== "archived") {
        content.append(
          node("p", `${copy.eligible_count}: ${row.eligible_count}`, "sub"),
          node(
            "p",
            `${copy.your_vote}: ${row.own_ballot ? optionLabel(row, row.own_ballot.option_id, copy) : copy.no_vote}`,
            "sub",
          ),
        );
      }
      if (PARENTS.has(card._data.role) && Array.isArray(row.eligible)) {
        const names = row.eligible.map((entry) =>
          memberName(card, entry.member, copy),
        );
        content.append(
          node("p", `${copy.eligible}: ${names.join(", ")}`, "sub"),
        );
        if (row.created_by)
          content.append(
            node(
              "p",
              `${copy.created_by}: ${memberName(card, row.created_by, copy)}`,
              "sub",
            ),
          );
      }
      const actions = node("div", null, "poll-actions");
      if (status === "open" && row.can_vote === true) {
        const voteSource = deepFreeze({
          id: row.id,
          definitionRevision: row.definition_revision,
          ballot: ballotSnapshot(row),
        });
        actions.append(
          localButton(
            row.own_ballot ? copy.revote : copy.vote,
            () => {
              const live = pollById(card, voteSource.id);
              if (
                live?.status !== "open" ||
                live.can_vote !== true ||
                live.definition_revision !== voteSource.definitionRevision ||
                !sameBallot(ballotSnapshot(live), voteSource.ballot)
              ) {
                card._actionError = "conflict";
                card.render();
                return;
              }
              card._pollsDraft = {
                intent: "vote",
                kind: "vote",
                access: deepFreeze(clone(currentAccess)),
                source: voteSource,
                optionId: voteSource.ballot?.option_id ?? null,
              };
              card._actionError = null;
              card.render();
            },
            true,
          ),
        );
      }
      const action =
        status === "open" && row.can_close === true
          ? ["close", copy.close, "polls.close"]
          : status === "closed" && row.can_archive === true
            ? ["archive", copy.archive, "polls.archive"]
            : status === "archived" &&
                row.can_purge === true &&
                card._data.role === "owner"
              ? ["purge", copy.purge, "polls.purge"]
              : null;
      if (action) {
        const source = deepFreeze({
          id: row.id,
          revision: row.revision,
          status: row.status,
        });
        actions.append(
          localButton(action[1], () => {
            const live = pollById(card, source.id);
            const allowed =
              samePoll(live, source) &&
              ((action[0] === "close" && live.can_close === true) ||
                (action[0] === "archive" && live.can_archive === true) ||
                (action[0] === "purge" && live.can_purge === true));
            if (!allowed) {
              card._actionError = "conflict";
              card.render();
              return;
            }
            const payload = {
              id: source.id,
              revision: source.revision,
              actor_revision: currentAccess.actorRevision,
              ...(action[0] === "purge" ? { confirm_delete: true } : {}),
            };
            card._pollsDraft = {
              intent: action[0],
              kind: "review",
              access: deepFreeze(clone(currentAccess)),
              source,
              action: action[2],
              payload: deepFreeze(payload),
              review: deepFreeze({ question: row.question }),
              confirmed: false,
            };
            card._actionError = null;
            card.render();
          }),
        );
      }
      if (actions.childNodes.length) content.append(actions);
      if (status === "archived") item.append(content);
      return item;
    };

    for (const [status, heading, empty] of [
      ["open", copy.open_polls, copy.no_open],
      ["closed", copy.closed_polls, copy.no_closed],
      ["archived", copy.archived_polls, copy.no_archived],
    ]) {
      const rows = pollsData(card._data)[status];
      if (status === "archived" && !PARENTS.has(card._data.role)) continue;
      const list = node("div", null, "polls-list");
      list.append(node("h3", heading));
      let count = 0;
      for (const row of rows) {
        const rendered = renderRow(row, status);
        if (rendered) {
          list.append(rendered);
          count += 1;
        }
      }
      if (!count) list.append(node("p", empty, "sub"));
      section.append(list);
    }
  }
  body.append(section);
}
