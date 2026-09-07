# UI release acceptance gaps

Audit date: 2026-09-07. This is a source review of the current public working
tree against [the accepted vision](vision.md) and the
[implementation matrix](implementation-status.md). It does not promote a
fixture, screenshot, or synthetic provider check to live acceptance.

Severity in this document is UI-release severity:

- **P0** blocks the documented normal installation path or makes the principal
  UI unavailable.
- **P1** leaves a required baseline workflow, localization, or accessibility
  behavior incomplete but has a documented workaround or a narrower usable
  path.

## What is already present

The frontend registers the Today card plus sixteen dedicated card aliases, and
all use a visual editor that selects only households visible to the current HA
user (`frontend/family-assistant.js:252-253, 654-695`). The shared editor and
card copy have EN/RU/UK key-parity tests. Module-specific browser suites cover
mobile layouts, role-filtered projections, named reviews, stale forms, and many
lost-response retries. Errors rendered by the shared card use a live alert
(`family-assistant.js:404`). These are useful implementation results, but they
do not close the gaps below.

## Confirmed implementation gaps

| Priority | Gap | Evidence and release effect |
| --- | --- | --- |
| **P0** | **The card resource is not registered automatically.** | Runtime registers only the static URL (`runtime.py:102-114`). The setup guides still require Advanced Mode and manual creation of `/family_assistant/frontend/family-assistant.js` as a dashboard Resource (`setup.en.md:131-137`, with the same steps in RU/UK). Until that is done, the card picker cannot discover any Family Assistant card. This contradicts the vision's ordinary no-YAML setup and the matrix's explicit “automatic card resource registration” next step. |
| **P1** | **The initial wizard stops after household basics and module switches.** | `async_step_user` proceeds only to `async_step_modules`, which immediately creates the entry (`config_flow.py:69-116`). Member editing, HA-account linking, Telegram, notification policy, siren, optional providers, and diagnostics exist as later Options flows or guides, but the accepted ten-stage newcomer flow in vision §9 is not implemented as a guided sequence. The controls are not absent; discovery, progress, safe skip/resume, and a final readiness check are. |
| **P1** | **Family Today is not the accepted role-aware overview.** | `renderToday` shows only three totals, visible member point balances, and active alarm runs (`family-assistant.js:561-575`). It does not render presence, nearby calendar/school items, due or overdue task detail, shopping detail, pending decisions, active consequences, provider/Telegram health, or problems needing attention from vision §7.1. Its browser acceptance only checks that a heading renders in three languages/dark mode and that the page does not overflow (`tests/browser/cards.spec.js:216-222`). |
| **P1** | **Several dedicated cards have an unexplained empty body when unavailable.** | School, Maintenance, Polls, Presence, and Digests clear their private draft and return when their access/module gate is absent (`school-view.js:509-515`, `maintenance-view.js:549-555`, `polls-view.js:428-434`, `presence-view.js:313-319`, `digests-view.js:531-537`). Tests explicitly accept no section for guests or module revocation, for example `frontend-polls.test.js:345-371`, `frontend-presence.test.js:318-324`, and `frontend-digests.test.js:314-319`. Hiding private data is correct; leaving only the card heading is not the vision's understandable empty/error state. A generic localized “module disabled” or “not available for this role” state can disclose no record data. |
| **P1** | **Periodic refresh can discard keyboard focus outside forms.** | Every connected card refreshes every ten seconds (`family-assistant.js:254`). Refresh preserves the DOM only when the active element is inside a `form`; focus on an action button, disclosure summary, radio list, or read-only control is replaced (`family-assistant.js:283`). The code has visible focus styling, but there is no cross-card regression for preserving/restoring a stable focus anchor, nor shared `aria-busy`/loading status. This makes a complete keyboard workflow timing-dependent. |
| **P1** | **Two baseline editors expose only a subset of already implemented commands.** | The alarm domain supports revision-bound edits, exception dates, second-check range, and grace (`domain/alarms.py:127-220`); the card only creates a preset weekday/weekend/every-day schedule and later offers enable/test (`family-assistant.js:326-347, 627-641`). Task-series save supports revision-bound edits, checklist, and report type (`domain/task_series.py:33-100`); the Tasks card only creates a reduced series and later enables/disables it (`family-assistant.js:355-396`). This matches the matrix's open API-only control gate and forces non-UI callers for normal corrections. |
| **P1** | **User-facing metadata and health fall back to internal English/codes.** | Card-picker registrations always use `COPY.en`, regardless of HA language (`family-assistant.js:694`). The Health card prints the raw module key and falls back to a raw health code (`family-assistant.js:577-587`), so a state such as `digests · digest_retention_attention` is not the localized Repairs wording. The EN/RU/UK setup guides also list only seven views although seventeen aliases are registered (`setup.en.md:139`, equivalent RU/UK section). Core form dictionaries are aligned; this is a remaining surface/localized-diagnostics gap, not evidence that every card body is untranslated. |

## Live acceptance gates, not implementation defects

The following remain release gates even after the UI gaps above are fixed:

- install, upgrade, cache refresh, multi-entry unload/reload, and card discovery
  with an actual packaged HACS release;
- a real user completing BotFather enrollment, private-chat and family-group
  linking, poller restart/conflict recovery, and delivery review;
- physical siren audibility and authorized RouterOS/topology checks;
- real configured Ollama, SearXNG, Mealie, calendar, and presence sources;
- an assistive-technology pass with keyboard-only use, screen reader, zoom,
  reduced motion, light/dark themes, and representative mobile devices;
- encrypted archive restore, legacy migration/shadow comparison, and controlled
  household cutover.

These need explicit environments and authorization. Synthetic Chromium and
actual-HA-with-fake-provider tests are necessary evidence, not substitutes.

## Next three bounded slices

1. **Automatic frontend bootstrap (P0).** Add one supported, idempotent HA
   frontend-resource registrar with multi-entry lifecycle handling and a
   versioned module URL; never edit Lovelace `.storage` directly. Cover fresh
   install, reload, last-entry unload, cache/version change, YAML/storage
   dashboard modes, and failure cleanup in an actual-HA smoke helper. Then
   remove the Advanced Mode/manual Resource step and update the complete card
   list in all three setup guides.

2. **Shared availability and focus shell (P1).** Centralize localized
   module-off, role-unavailable, loading, and retry states without exposing why
   a private row is absent. Preserve a stable focus key across background
   refresh, move focus into newly opened reviews, restore it on cancel/success,
   and expose busy/status semantics. Add keyboard tests for a button, disclosure,
   radio group, revocation, and the ten-second refresh boundary; localize Health
   labels/codes and remove the English-only card-picker metadata fallback where
   the supported HA API permits.

3. **Role-aware Today/Health overview (P1).** Move Today into a bounded helper
   that consumes only existing server-projected rows. Start with due/overdue
   tasks, approvals, upcoming calendar/school/alarm items, shopping count,
   normalized presence, and counts-only health/Repair attention; provide links
   or labels to the owning card rather than duplicate mutation forms. Test
   parent/child/adult/guest projections, disabled modules, empty/error states,
   EN/RU/UK, narrow/zoomed layouts, and zero mutation during render.

The guided multi-stage onboarding sequence and full alarm/task-series editors
remain the next P1 controls after these three slices; their existing Options/API
workarounds make them less urgent than card availability, cross-card access
clarity, and the principal overview.
