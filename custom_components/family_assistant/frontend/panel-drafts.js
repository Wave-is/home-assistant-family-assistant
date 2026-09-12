/* Tab-local drafts are untrusted input, never commands or provider configuration. */
export const DRAFT_TTL = 24 * 60 * 60 * 1000;
export const DRAFT_PREFIX = "family-assistant:panel-draft:v1:";
const roles = ["owner", "parent", "adult", "child", "guest"];
const languages = ["en", "ru", "uk"];
const fields = {
  family: {name:128, language:2, timezone:128},
  member: {name:128, role:6, language:2, aliasesText:1620, ha_user_id:128, birth_date:10, avatar:16, active:null},
};
const text = (value, max) => typeof value === "string" && value.length <= max;
const revision = value => Number.isSafeInteger(value) && value >= 1;

export function draftKey(user, entry) {
  return user && entry ? `${DRAFT_PREFIX}${encodeURIComponent(user)}:${encodeURIComponent(entry)}` : null;
}

export function createDraft({user, entry, kind, draft, wizard=false, onboardingRevision=null}, now=Date.now()) {
  if (!fields[kind]) return null;
  const values = Object.fromEntries(Object.keys(fields[kind]).map(key => [key, draft[key]]));
  const record = {version:1, user, entry, kind, savedAt:now, status:"editing", wizard,
    onboardingRevision:wizard ? onboardingRevision : null,
    memberId:kind === "member" ? draft.id ?? null : null,
    revision:draft.revision ?? null, values};
  return decodeDraft(JSON.stringify(record), user, entry, now);
}

export function decodeDraft(raw, user, entry, now=Date.now()) {
  try {
    if (typeof raw !== "string" || raw.length > 12000) return null;
    const record = JSON.parse(raw);
    if (!record || record.version !== 1 || record.user !== user || record.entry !== entry
      || !text(user, 128) || !user || !text(entry, 128) || !entry || !fields[record.kind]
      || !["editing", "submitted"].includes(record.status) || typeof record.wizard !== "boolean"
      || !Number.isSafeInteger(record.savedAt) || record.savedAt > now || now - record.savedAt >= DRAFT_TTL) return null;
    const keys = ["version", "user", "entry", "kind", "savedAt", "status", "wizard", "onboardingRevision", "memberId", "revision", "values"];
    if (Object.keys(record).some(key => !keys.includes(key))) return null;
    if (record.kind === "family") {
      if (record.memberId !== null || !revision(record.revision)) return null;
    } else if (record.wizard || (record.memberId === null ? record.revision !== null :
      !text(record.memberId, 128) || !record.memberId || !revision(record.revision))) return null;
    if (record.wizard ? !revision(record.onboardingRevision) : record.onboardingRevision !== null) return null;
    const values = record.values, shape = fields[record.kind];
    if (!values || typeof values !== "object" || Object.keys(values).length !== Object.keys(shape).length) return null;
    for (const [key, max] of Object.entries(shape)) {
      if (max === null ? typeof values[key] !== "boolean" : !text(values[key], max)) return null;
    }
    if (!languages.includes(values.language) || (record.kind === "member" && !roles.includes(values.role))) return null;
    return record;
  } catch {return null;}
}

export function draftConflict(record, data) {
  if (record.status === "submitted") return "submitted";
  if (record.kind === "family") {
    return record.revision !== data.settings_revision || (record.wizard &&
      (record.onboardingRevision !== data.onboarding?.revision || data.onboarding?.step !== 1)) ? "stale" : null;
  }
  if (record.memberId === null) return null;
  const member = (data.members || data.view.members).find(item => item.id === record.memberId);
  return !member || member.revision !== record.revision ? "stale" : null;
}
