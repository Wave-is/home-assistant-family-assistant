/* Private dashboard conversation with current-scope retries. */

import { CONVERSATION_COPY } from "./conversation-copy.js";

const ROLES = new Set(["owner", "parent", "adult", "child"]);

const clone = (value) => JSON.parse(JSON.stringify(value));
const deepFreeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
};
const exactKeys = (value, keys) =>
  Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      JSON.stringify(Object.keys(value).sort()) ===
        JSON.stringify([...keys].sort()),
  );
const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};

const STYLE = `
  .conversation-chat,.conversation-form,.conversation-learning{display:grid;gap:10px;min-width:0}
  .conversation-form label,.conversation-learning form{display:grid;gap:6px}
  .conversation-form input,.conversation-learning input{box-sizing:border-box;max-width:100%;min-width:0;width:100%}
  .conversation-actions{display:flex;flex-wrap:wrap;gap:8px}.conversation-reply{white-space:pre-wrap;overflow-wrap:anywhere}
  .conversation-learning{margin-top:16px}.conversation-learning>div{overflow-wrap:anywhere}
  @media(max-width:520px){.conversation-actions>button{width:100%}}
`;

function copyOf(card) {
  const language = String(
    card?._config?.language || card?._hass?.language || "en",
  ).split(/[-_]/)[0];
  return CONVERSATION_COPY[language] || CONVERSATION_COPY.en;
}

function sourceOf(data) {
  const source = data?.conversation_source;
  if (
    !exactKeys(source, ["enabled", "configured", "allowed", "revision"]) ||
    typeof source.enabled !== "boolean" ||
    typeof source.configured !== "boolean" ||
    typeof source.allowed !== "boolean" ||
    (source.allowed
      ? !(
          source.enabled === true &&
          typeof source.revision === "string" &&
          /^[0-9a-f]{32}$/.test(source.revision)
        )
      : source.revision !== null)
  )
    return null;
  return source;
}

function actorMember(data) {
  return Array.isArray(data?.members)
    ? data.members.find((item) => item?.id === data?.actor) || null
    : null;
}

function accessOf(card) {
  const data = card?._data;
  const source = sourceOf(data);
  const member = actorMember(data);
  const user = card?._hass?.user?.id;
  if (
    !source?.allowed ||
    !ROLES.has(data?.role) ||
    member?.active !== true ||
    member.role !== data.role ||
    !Number.isSafeInteger(member.revision) ||
    member.revision < 1 ||
    !Array.isArray(data?.settings?.modules) ||
    !data.settings.modules.includes("conversation") ||
    !Number.isSafeInteger(card?._generation) ||
    card._generation < 1 ||
    typeof card?._entry !== "string" ||
    !card._entry ||
    typeof user !== "string" ||
    !user
  )
    return null;
  return {
    entry: card._entry,
    generation: card._generation,
    user,
    actor: data.actor,
    actorRevision: member.revision,
    role: data.role,
    module: true,
    enabled: source.enabled,
    configured: source.configured,
    allowed: source.allowed,
    sourceRevision: source.revision,
  };
}

function sameAccess(card, expected) {
  const current = accessOf(card);
  return Boolean(
    current && expected && JSON.stringify(current) === JSON.stringify(expected),
  );
}

function projection(data) {
  const member = actorMember(data);
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    module: Array.isArray(data?.settings?.modules)
      ? data.settings.modules.includes("conversation")
      : false,
    source: data?.conversation_source ?? null,
    member: member
      ? {
          id: member.id,
          role: member.role,
          active: member.active,
          revision: member.revision,
        }
      : null,
  };
}

export function reconcileConversationRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(projection(previousData)) !==
    JSON.stringify(projection(card._data));
  let force =
    changed &&
    Boolean(
      card._conversationDraft ||
        card.shadowRoot?.querySelector(".conversation-chat"),
    );
  if (
    card._conversationDraft &&
    !sameAccess(card, card._conversationDraft.access)
  ) {
    card._conversationDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

export function disposeConversation(card) {
  if (!card) return;
  if (card._conversationDraft) card._conversationDraft.requestToken = null;
  card._conversationDraft = null;
}

function cleanText(value, maximum, code) {
  if (typeof value !== "string" || value.length > maximum) throw new Error(code);
  const result = value.trim();
  if (!result) throw new Error(code);
  for (const character of result) {
    const point = character.charCodeAt(0);
    if (point < 32 && ![9, 10, 13].includes(point)) throw new Error(code);
  }
  return result;
}

function responseOf(value) {
  if (!exactKeys(value, ["reply"])) throw new Error("provider_bad_response");
  return cleanText(value.reply, 16384, "provider_bad_response");
}

function freshDraft(access) {
  return {
    access: deepFreeze(clone(access)),
    sessionId: crypto.randomUUID(),
    text: "",
    reply: null,
    pending: null,
    loading: false,
    requestToken: null,
  };
}

function appendInput(parent, name, labelText, value = "") {
  const label = node("label", labelText);
  const input = document.createElement("input");
  input.type = "text";
  input.name = name;
  input.value = value;
  input.required = true;
  input.autocomplete = "off";
  label.append(input);
  parent.append(label);
  return input;
}

export function renderConversation(card, body) {
  if (!card || !body || !card._data) return;
  const copy = copyOf(card);
  const source = sourceOf(card._data);
  if (!source) {
    disposeConversation(card);
    return;
  }
  const access = accessOf(card);
  if (
    card._conversationDraft &&
    !sameAccess(card, card._conversationDraft.access)
  ) {
    disposeConversation(card);
    card._actionError = "conflict";
  }

  const section = node("section", null, "conversation-chat");
  section.append(node("style", STYLE));
  body.append(section);
  if (!access) {
    section.append(node("p", copy.unavailable, "sub"));
    return;
  }
  if (!card._conversationDraft) card._conversationDraft = freshDraft(access);
  const draft = card._conversationDraft;

  const draftCurrent = () =>
    card._conversationDraft === draft && sameAccess(card, draft.access);
  const live = (control) =>
    draftCurrent() &&
    card.isConnected &&
    body.isConnected &&
    Boolean(control?.isConnected);
  const rejectStale = (control) => {
    if (live(control)) return false;
    if (!sameAccess(card, draft.access)) {
      disposeConversation(card);
      card._actionError = "conflict";
      if (card.isConnected) card.render();
    }
    return true;
  };

  if (draft.reply)
    section.append(node("div", draft.reply, "item conversation-reply"));
  if (!source.configured)
    section.append(node("p", copy.deterministic, "sub"));

  const form = node("form", null, "conversation-form");
  form.dataset.conversationForm = "chat";
  const input = appendInput(form, "message", copy.message, draft.text);
  input.maxLength = 4096;
  input.disabled = draft.loading || Boolean(draft.pending);
  input.addEventListener("input", () => {
    if (!rejectStale(input) && !draft.loading && !draft.pending)
      draft.text = input.value;
  });
  const actions = node("div", null, "conversation-actions");
  const submit = node(
    "button",
    draft.pending ? copy.retry : copy.send,
    "primary",
  );
  submit.type = "submit";
  submit.disabled = draft.loading || Boolean(card._writing);
  actions.append(submit);
  if (draft.pending && !draft.loading) {
    const startNew = node("button", copy.start_new);
    startNew.type = "button";
    startNew.disabled = Boolean(card._writing);
    startNew.addEventListener("click", () => {
      if (rejectStale(startNew) || draft.loading || card._writing) return;
      draft.pending = null;
      draft.reply = null;
      draft.text = "";
      draft.requestToken = null;
      card._actionError = null;
      card.render();
    });
    actions.append(startNew);
  }
  form.append(actions);
  section.append(form);
  if (draft.loading) {
    const status = node("p", copy.thinking, "notice");
    status.setAttribute("role", "status");
    section.append(status);
  } else if (draft.pending) {
    section.append(node("p", copy.uncertain_warning, "notice"));
  }

  const run = async () => {
    if (rejectStale(form) || draft.loading || card._writing) return;
    let text;
    try {
      text = draft.pending
        ? draft.pending.text
        : cleanText(input.value, 4096, "invalid_field");
    } catch (error) {
      card._actionError = error.message;
      card.render();
      return;
    }
    if (!draft.pending) {
      draft.text = text;
      draft.reply = null;
      draft.pending = deepFreeze({
        type: "family_assistant/chat",
        entry_id: draft.access.entry,
        text,
        operation_id: crypto.randomUUID(),
        session_id: draft.sessionId,
        actor_revision: draft.access.actorRevision,
        source_revision: draft.access.sourceRevision,
      });
    }
    const request = draft.pending;
    const token = {};
    draft.requestToken = token;
    draft.loading = true;
    card._actionError = null;
    card.render();
    try {
      const result = await card._hass.callWS(request);
      if (!draftCurrent() || draft.requestToken !== token) return;
      if (!card.isConnected) {
        disposeConversation(card);
        return;
      }
      draft.reply = responseOf(result);
      draft.pending = null;
      draft.text = "";
      card._actionError = null;
    } catch (error) {
      if (!draftCurrent() || draft.requestToken !== token) return;
      if (!card.isConnected) {
        disposeConversation(card);
        return;
      }
      card._actionError =
        error?.message === "provider_bad_response"
          ? "provider_bad_response"
          : error?.code || "provider_bad_response";
    } finally {
      if (draftCurrent() && draft.requestToken === token) {
        draft.requestToken = null;
        draft.loading = false;
        if (card.isConnected) {
          card.render();
          if (typeof card.refresh === "function") void card.refresh();
        }
      }
    }
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void run();
  });

  const learning = node("details", null, "conversation-learning");
  learning.append(node("summary", copy.learn), node("p", copy.learning_hint, "sub"));
  const learn = node("form");
  learn.dataset.conversationForm = "learn";
  const sourceInput = appendInput(learn, "source", copy.source_phrase);
  sourceInput.maxLength = 200;
  const canonicalInput = appendInput(learn, "canonical", copy.canonical_phrase);
  canonicalInput.maxLength = 200;
  const save = node("button", copy.save, "primary");
  save.type = "submit";
  save.disabled = Boolean(card._writing);
  learn.append(save);
  learn.addEventListener("submit", (event) => {
    event.preventDefault();
    if (rejectStale(learn) || card._writing) return;
    card.command("conversation.learn", {
      source: sourceInput.value,
      canonical: canonicalInput.value,
    });
  });
  learning.append(learn);
  for (const phrase of Array.isArray(card._data.learned_phrases)
    ? card._data.learned_phrases
    : []) {
    if (
      phrase?.active !== true ||
      typeof phrase.id !== "string" ||
      typeof phrase.source !== "string" ||
      typeof phrase.canonical !== "string"
    )
      continue;
    const item = node("div", null, "item");
    item.append(node("strong", phrase.source), node("p", phrase.canonical, "sub"));
    const forget = node("button", copy.forget);
    forget.type = "button";
    forget.disabled = Boolean(card._writing);
    forget.addEventListener("click", () => {
      if (!rejectStale(forget) && !card._writing)
        card.command("conversation.forget", { id: phrase.id });
    });
    item.append(forget);
    learning.append(item);
  }
  section.append(learning);
}

export const _test = { accessOf, responseOf, sourceOf };
