/* Restore keyboard context across a passive, authority-stable card rerender. */

const CONTROL_SELECTOR =
  'button, summary, input:not([type="hidden"]), select, textarea, [tabindex]';
const MAX_KEY_PART = 512;

function plain(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function bounded(value, limit = MAX_KEY_PART) {
  if (typeof value !== "string") return null;
  const result = value.trim().replace(/\s+/g, " ");
  return result && result.length <= limit ? result : null;
}

function currentScope(card) {
  const data = card?._data;
  if (
    !plain(data) ||
    typeof data.actor !== "string" ||
    typeof data.role !== "string" ||
    !Number.isSafeInteger(data.revision) ||
    data.revision < 0 ||
    !Array.isArray(data.members) ||
    !Array.isArray(data.settings?.modules)
  )
    return null;
  const actor = data.members.find((member) => member?.id === data.actor);
  if (
    !actor ||
    actor.active !== true ||
    actor.role !== data.role ||
    !Number.isSafeInteger(actor.revision) ||
    actor.revision < 1
  )
    return null;
  const modules = data.settings.modules;
  if (!modules.every((module) => typeof module === "string")) return null;
  const entry = bounded(card?._entry, 128);
  const view = bounded(card?._view, 64);
  if (!entry || !view || !Number.isSafeInteger(card?._generation)) return null;
  const user = card?._hass?.user?.id;
  if (user !== undefined && user !== null && !bounded(user, 128)) return null;
  return JSON.stringify({
    entry,
    generation: card._generation,
    user: user || null,
    view,
    revision: data.revision,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
    modules: [...new Set(modules)].sort(),
  });
}

function keyFor(element) {
  if (
    element?.nodeType !== 1 ||
    typeof element.matches !== "function" ||
    !element.matches(CONTROL_SELECTOR)
  )
    return null;
  const tag = element.tagName.toLowerCase();
  const id = bounded(element.id, 256);
  if (id) return JSON.stringify(["id", id]);
  const explicit = bounded(element.getAttribute("data-focus-key"), 256);
  if (explicit) return JSON.stringify(["focus", explicit]);
  const aria = bounded(element.getAttribute("aria-label"));
  const name = bounded(element.getAttribute("name"), 256);
  const type = bounded(element.getAttribute("type"), 64);
  if (tag === "input") {
    if (!name) return null;
    const value = ["radio", "checkbox"].includes(type)
      ? bounded(element.getAttribute("value") || "on", 256)
      : null;
    return JSON.stringify(["input", type || "text", name, value, aria]);
  }
  if (tag === "select" || tag === "textarea") {
    if (!name && !aria) return null;
    return JSON.stringify([tag, name, aria]);
  }
  if (tag === "button") {
    const text = bounded(element.textContent);
    if (!name && !aria && !text) return null;
    return JSON.stringify([
      "button",
      type || "submit",
      name,
      bounded(element.getAttribute("value"), 256),
      aria,
      text,
    ]);
  }
  if (tag === "summary") {
    const text = bounded(element.textContent);
    return text || aria ? JSON.stringify(["summary", aria, text]) : null;
  }
  const tabIndex = bounded(element.getAttribute("tabindex"), 16);
  const text = bounded(element.textContent);
  return aria || text
    ? JSON.stringify(["tabindex", tag, tabIndex, aria, text])
    : null;
}

function allControls(root) {
  return root ? [...root.querySelectorAll(CONTROL_SELECTOR)] : [];
}

function uniqueControl(root, key) {
  if (!key) return null;
  const matches = allControls(root).filter(
    (element) => keyFor(element) === key,
  );
  return matches.length === 1 ? matches[0] : null;
}

function directSummary(details) {
  return (
    [...details.children].find((child) => child.tagName === "SUMMARY") || null
  );
}

function disclosureKey(details) {
  const id = bounded(details.id, 256);
  if (id) return JSON.stringify(["details-id", id]);
  const explicit = bounded(details.getAttribute("data-disclosure-key"), 256);
  if (explicit) return JSON.stringify(["details-key", explicit]);
  const summary = directSummary(details);
  const summaryKey = keyFor(summary);
  return summaryKey ? JSON.stringify(["details-summary", summaryKey]) : null;
}

function disclosureStates(root) {
  const candidates = [...root.querySelectorAll("details")]
    .map((details) => ({ details, key: disclosureKey(details) }))
    .filter((item) => item.key);
  const counts = new Map();
  for (const item of candidates)
    counts.set(item.key, (counts.get(item.key) || 0) + 1);
  return candidates
    .filter((item) => counts.get(item.key) === 1)
    .map((item) =>
      Object.freeze({ key: item.key, open: item.details.open === true }),
    );
}

function restoreDisclosures(root, states) {
  let restored = 0;
  const changed = [];
  for (const state of states) {
    const matches = [...root.querySelectorAll("details")].filter(
      (details) => disclosureKey(details) === state.key,
    );
    if (matches.length !== 1) continue;
    if (matches[0].open !== state.open) changed.push([matches[0], state.open]);
    restored += 1;
  }
  if (!changed.length) return restored;
  // HTMLDetailsElement.open queues a native `toggle` event. Suppress only the
  // exact restoration events so passive refresh cannot be interpreted as user
  // intent or start a private lazy load in a later module.
  const pending = new Map(changed);
  let cleanupTimer;
  const cleanup = () => {
    root.removeEventListener("toggle", suppress, true);
    for (const type of ["pointerdown", "keydown", "click"])
      root.removeEventListener(type, abandon, true);
    if (cleanupTimer !== undefined)
      root.ownerDocument?.defaultView?.clearTimeout(cleanupTimer);
  };
  const finish = (details) => {
    pending.delete(details);
    if (!pending.size) cleanup();
  };
  const abandon = (event) => {
    const details = event.target?.closest?.("details");
    if (pending.has(details)) finish(details);
  };
  const suppress = (event) => {
    if (!pending.has(event.target)) return;
    const expected = pending.get(event.target);
    finish(event.target);
    const expectedState = expected ? "open" : "closed";
    const priorState = expected ? "closed" : "open";
    const stateMatches =
      event.target.open === expected &&
      (typeof event.newState !== "string" ||
        event.newState === expectedState) &&
      (typeof event.oldState !== "string" || event.oldState === priorState);
    if (stateMatches) event.stopImmediatePropagation();
  };
  root.addEventListener("toggle", suppress, true);
  for (const type of ["pointerdown", "keydown", "click"])
    root.addEventListener(type, abandon, true);
  for (const [details, open] of changed) details.open = open;
  cleanupTimer = root.ownerDocument?.defaultView?.setTimeout(cleanup, 100);
  return restored;
}

function focusable(element) {
  return Boolean(
    element?.isConnected &&
    !element.hasAttribute("disabled") &&
    !element.closest("[hidden]") &&
    element.getAttribute("aria-hidden") !== "true",
  );
}

export function captureFocusRefresh(card) {
  const scope = currentScope(card);
  const root = card?.shadowRoot;
  if (!scope || !root) return null;
  return Object.freeze({
    scope,
    root,
    activeElement: root.activeElement || null,
  });
}

/**
 * Invoke one synchronous render and restore stable keyboard/disclosure context.
 * Call only in the existing refresh branch that has already decided to rerender.
 */
export function renderWithFocusRefresh(card, snapshot, render) {
  if (typeof render !== "function") return false;
  const root = card?.shadowRoot;
  const safe = Boolean(
    snapshot &&
    root &&
    snapshot.root === root &&
    snapshot.scope === currentScope(card),
  );
  const active = safe ? root.activeElement : null;
  const candidateKey = active && focusable(active) ? keyFor(active) : null;
  const focusKey =
    candidateKey && uniqueControl(root, candidateKey) === active
      ? candidateKey
      : null;
  // If focus left the shadow root while the request was pending, active is null;
  // never pull it back from another card or from the surrounding dashboard.
  const disclosures = safe ? disclosureStates(root) : [];

  render();

  if (
    !safe ||
    !card?.isConnected ||
    card.shadowRoot !== root ||
    snapshot.scope !== currentScope(card)
  )
    return false;
  restoreDisclosures(root, disclosures);
  // Respect focus intentionally placed by the renderer itself.
  if (!focusKey || root.activeElement) return false;
  const replacement = uniqueControl(root, focusKey);
  if (!focusable(replacement)) return false;
  replacement.focus({ preventScroll: true });
  return root.activeElement === replacement;
}
