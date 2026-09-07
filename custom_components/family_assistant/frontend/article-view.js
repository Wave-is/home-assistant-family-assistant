/* Explicit, transient article request and verified citation rendering. */

import { ARTICLE_COPY } from "./article-copy.js";

const ROLES = new Set(["owner", "parent", "adult", "child"]);
const URL_TEXT = /(?:https?:\/\/|www\.|\[[^\]]*\]\([^)]*\)|\b(?:[a-z0-9-]+\.)+[a-z]{2,63}\b)/i;

const clone = (value) => JSON.parse(JSON.stringify(value));
const deepFreeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value))
    return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
};
const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};
const exactKeys = (value, keys) =>
  Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      JSON.stringify(Object.keys(value).sort()) ===
        JSON.stringify([...keys].sort()),
  );

const STYLE = `
  .article-section,.article-content,.article-form,.article-review,.article-result{display:grid;gap:10px;min-width:0}.article-section{margin-top:16px}
  .article-form label{display:grid;gap:5px}.article-form input[type=url]{box-sizing:border-box;max-width:100%;min-width:0;width:100%}
  .article-actions{display:flex;flex-wrap:wrap;gap:8px}.article-confirm{display:flex!important;grid-template-columns:auto minmax(0,1fr);align-items:start;gap:8px!important}
  .article-confirm input{margin-top:3px}.article-review p,.article-result p{margin:0;overflow-wrap:anywhere}.article-answer{white-space:pre-wrap}
  .article-source{display:grid;gap:5px;padding-top:8px;border-top:1px solid var(--divider-color,#ddd)}.article-source a{overflow-wrap:anywhere}
  @media(max-width:520px){.article-actions>button{width:100%}}
`;

function copyOf(card) {
  const language = String(
    card?._config?.language || card?._hass?.language || "en",
  ).split(/[-_]/)[0];
  return ARTICLE_COPY[language] || ARTICLE_COPY.en;
}

function sourceOf(data) {
  const source = data?.article_source;
  if (
    !exactKeys(source, ["enabled", "configured", "allowed", "revision"]) ||
    typeof source.enabled !== "boolean" ||
    typeof source.configured !== "boolean" ||
    typeof source.allowed !== "boolean" ||
    (source.allowed
      ? !(
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
  const userId = card?._hass?.user?.id;
  if (
    !source?.allowed ||
    source.enabled !== true ||
    source.configured !== true ||
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
    typeof userId !== "string" ||
    !userId
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    user: userId,
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
    conversation: Array.isArray(data?.settings?.modules)
      ? data.settings.modules.includes("conversation")
      : false,
    source: data?.article_source ?? null,
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

export function reconcileArticleRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(projection(previousData)) !==
    JSON.stringify(projection(card._data));
  let force =
    changed &&
    Boolean(card._articleDraft || card.shadowRoot?.querySelector(".article-section"));
  if (card._articleDraft && !sameAccess(card, card._articleDraft.access)) {
    card._articleDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

export function disposeArticle(card) {
  if (card) card._articleDraft = null;
}

function normalizeUrl(value) {
  if (typeof value !== "string" || !value || value.length > 2048)
    throw new Error("article_invalid_url");
  let parsed;
  try {
    parsed = new URL(value);
  } catch (_error) {
    throw new Error("article_invalid_url");
  }
  if (
    parsed.protocol !== "https:" ||
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.hash ||
    (parsed.port && parsed.port !== "443")
  )
    throw new Error("article_invalid_url");
  return parsed.href;
}

function safeText(value, maximum, required = true) {
  if (typeof value !== "string" || value.length > maximum)
    throw new Error("provider_bad_response");
  const result = value.trim();
  if (required && !result) throw new Error("provider_bad_response");
  for (const character of result) {
    const code = character.charCodeAt(0);
    if (code < 32 && ![9, 10, 13].includes(code))
      throw new Error("provider_bad_response");
  }
  return result;
}

function validateResponse(value, draft) {
  if (!exactKeys(value, ["answer", "sources"]))
    throw new Error("provider_bad_response");
  const answer = safeText(value.answer, 3000);
  if (URL_TEXT.test(answer)) throw new Error("provider_bad_response");
  if (!Array.isArray(value.sources) || value.sources.length !== 1)
    throw new Error("provider_bad_response");
  const source = value.sources[0];
  if (!exactKeys(source, ["title", "url", "requested_url", "retrieved_at"]))
    throw new Error("provider_bad_response");
  const requested = normalizeUrl(source.requested_url);
  const final = normalizeUrl(source.url);
  const retrieved = safeText(source.retrieved_at, 64);
  if (
    requested !== draft.url ||
    !Number.isFinite(new Date(retrieved).getTime())
  )
    throw new Error("provider_bad_response");
  return deepFreeze({
    answer,
    sources: [
      {
        title: safeText(source.title, 200),
        url: final,
        requested_url: requested,
        retrieved_at: retrieved,
      },
    ],
  });
}

function appendButton(card, parent, label, action, primary, guard) {
  const button = card.button(
    label,
    () => {
      if (guard(button)) action();
    },
    primary,
  );
  button.type = "button";
  parent.append(button);
  return button;
}

export function renderArticle(card, body) {
  if (!card || !body || !card._data) return;
  const source = sourceOf(card._data);
  if (!source) {
    card._articleDraft = null;
    return;
  }
  const access = accessOf(card);
  if (card._articleDraft && !sameAccess(card, card._articleDraft.access)) {
    card._articleDraft = null;
    card._actionError = "conflict";
  }
  const copy = copyOf(card);
  const section = node("section", null, "article-section");
  section.append(node("style", STYLE), node("h3", copy.title));
  const content = node("div", null, "article-content");
  section.append(content);
  body.append(section);
  if (!access) {
    const message = !source.enabled
      ? copy.disabled
      : !source.configured
        ? copy.unavailable
        : copy.not_allowed;
    content.append(node("p", message, "sub"));
    return;
  }

  const detached = () => !body.isConnected;
  const draftCurrent = (draft) =>
    card._articleDraft === draft && sameAccess(card, draft.access);
  const guard = (control, draft = null) => {
    if (
      (draft && !draftCurrent(draft)) ||
      !sameAccess(card, draft?.access || access)
    ) {
      card._articleDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected) card.render();
      return false;
    }
    return (
      !detached() &&
      Boolean(control?.isConnected) &&
      !card._writing &&
      !draft?.loading
    );
  };
  const close = (draft) => {
    if (!guard(body, draft)) return;
    card._articleDraft = null;
    card._actionError = null;
    card.render();
  };
  const run = async (draft) => {
    if (!guard(body, draft)) return;
    if (!draft.pending) {
      draft.pending = deepFreeze({
        type: "family_assistant/article",
        entry_id: draft.access.entry,
        url: draft.url,
        operation_id: crypto.randomUUID(),
        source_revision: draft.access.sourceRevision,
      });
    }
    const request = draft.pending;
    draft.loading = true;
    card._actionError = null;
    for (const control of section.querySelectorAll("button,input"))
      control.disabled = true;
    const submit = section.querySelector('.article-review button[type="submit"]');
    if (submit) submit.textContent = copy.loading;
    try {
      const response = await card._hass.callWS(request);
      if (!draftCurrent(draft)) return;
      if (!card.isConnected) {
        card._articleDraft = null;
        return;
      }
      draft.result = validateResponse(response, draft);
      draft.phase = "result";
      draft.pending = null;
      draft.loading = false;
      card.render();
    } catch (error) {
      if (!draftCurrent(draft)) return;
      if (!card.isConnected) {
        card._articleDraft = null;
        return;
      }
      draft.loading = false;
      card._actionError =
        error?.message === "provider_bad_response"
          ? "provider_bad_response"
          : error?.code || "article_unavailable";
      card.render();
    }
  };

  const draft = card._articleDraft;
  if (!draft) {
    appendButton(
      card,
      content,
      copy.open,
      () => {
        const fresh = {
          access: deepFreeze(clone(access)),
          phase: "edit",
          url: "",
          confirmed: false,
          pending: null,
          result: null,
          loading: false,
        };
        card._articleDraft = fresh;
        card._actionError = null;
        card.render();
        queueMicrotask(() =>
          card.shadowRoot?.querySelector('.article-form input[name="url"]')?.focus(),
        );
      },
      true,
      (control) => guard(control),
    );
    return;
  }

  if (draft.phase === "edit") {
    const form = node("form", null, "article-form");
    form.dataset.articleForm = "edit";
    const label = node("label", copy.url);
    const input = document.createElement("input");
    input.type = "url";
    input.name = "url";
    input.required = true;
    input.maxLength = 2048;
    input.autocomplete = "off";
    input.value = draft.url;
    label.append(input);
    form.append(label, node("p", copy.url_hint, "sub"));
    input.addEventListener("input", () => {
      if (guard(input, draft)) draft.url = input.value;
    });
    const actions = node("div", null, "article-actions");
    const review = appendButton(
      card,
      actions,
      copy.review,
      () => {},
      true,
      (control) => guard(control, draft),
    );
    review.type = "submit";
    appendButton(
      card,
      actions,
      copy.cancel,
      () => close(draft),
      false,
      (control) => guard(control, draft),
    );
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(form, draft)) return;
      try {
        draft.url = normalizeUrl(input.value.trim());
        draft.phase = "review";
        draft.confirmed = false;
        card._actionError = null;
        card.render();
      } catch (error) {
        card._actionError = error.message;
        card.render();
      }
    });
    content.append(form);
    return;
  }

  if (draft.phase === "review") {
    const form = node("form", null, "article-form article-review");
    form.dataset.articleForm = "review";
    form.append(
      node("h4", copy.review_title),
      node("p", draft.url, "article-reviewed-url"),
      node("p", copy.disclosure, "sub"),
    );
    const confirm = node("label", null, "article-confirm");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "confirmed";
    checkbox.checked = draft.confirmed;
    checkbox.disabled = Boolean(draft.pending);
    confirm.append(checkbox, node("span", copy.confirm));
    form.append(confirm);
    checkbox.addEventListener("change", () => {
      if (guard(checkbox, draft) && !draft.pending)
        draft.confirmed = checkbox.checked;
    });
    if (draft.loading) form.append(node("p", copy.loading, "sub"));
    const actions = node("div", null, "article-actions");
    const submit = appendButton(
      card,
      actions,
      draft.pending ? copy.retry : copy.fetch,
      () => {},
      true,
      (control) => guard(control, draft),
    );
    submit.type = "submit";
    if (!draft.pending) {
      appendButton(
        card,
        actions,
        copy.back,
        () => {
          if (!guard(actions, draft)) return;
          draft.phase = "edit";
          draft.confirmed = false;
          card._actionError = null;
          card.render();
        },
        false,
        (control) => guard(control, draft),
      );
      appendButton(
        card,
        actions,
        copy.cancel,
        () => close(draft),
        false,
        (control) => guard(control, draft),
      );
    }
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(form, draft)) return;
      if (!draft.pending && !checkbox.checked) return;
      draft.confirmed = true;
      void run(draft);
    });
    content.append(form);
    return;
  }

  if (draft.phase === "result" && draft.result) {
    const result = node("article", null, "article-result");
    result.append(
      node("h4", copy.result),
      node("p", draft.result.answer, "article-answer"),
    );
    const source = draft.result.sources[0];
    const citation = node("div", null, "article-source");
    citation.append(node("strong", copy.source));
    const link = node("a", source.title);
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    citation.append(
      link,
      node("p", `${copy.requested}: ${source.requested_url}`, "sub"),
      node("p", `${copy.retrieved}: ${source.retrieved_at}`, "sub"),
    );
    result.append(citation);
    appendButton(
      card,
      result,
      copy.close,
      () => close(draft),
      false,
      (control) => guard(control, draft),
    );
    content.append(result);
  }
}

export const _test = { accessOf, normalizeUrl, sourceOf, validateResponse };
