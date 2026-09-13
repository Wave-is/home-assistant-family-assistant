# Frontend action coverage

`frontend-control-inventory.json` is the durable source/action inventory for all
17 published cards, the shared Lovelace editor, and the control panel. It is not
a declaration that every control or every product requirement is complete.

The inventory retains every frontend file hash and conservative source sites
for button factories, listeners, field factories/names, forms, commands, and
links. Shared helpers and dynamic loops are included explicitly. One site can
create multiple controls, and one control can use several sites; therefore the
site count must not be described as a count of distinct user-facing buttons.
Display-only Today and native `details`/`summary` interactions do not necessarily
have application click handlers.

Browser evidence has three separate levels:

- `handlers[].registered`: the listed passing fixture cases bound that handler.
- `handlers[].invoked` / `trusted`: the listener actually ran / received a native
  browser event. An empty invocation list is an explicit unvisited handler.
- `requests[]`: exact WebSocket type/action names and cases with attempted,
  resolved, or rejected synthetic fixture promises. A resolved promise is not
  proof that the real backend accepted the command or a device performed it.

References are numeric IDs into `cases`, which supplies test file, line, and
scenario title. The same source line can implement multiple choices or record
states; the named scenarios are the limit of the claim. Source sites that never
appear in recorded handler frames have no associated browser-handler evidence,
even if their helper or field may have appeared on screen. Unit tests remain
separate evidence, not silently promoted to browser/HA acceptance.

Handler groups use the first two registration stack frames; `source_frames`
separately retains all five collected frames with their scenario references.
This matters for nested button helpers: their third frame can identify the real
control even when its source line is absent from the two-frame group identity.
Neither a constructor line nor a form declaration must itself appear in a stack
to have a tested listener elsewhere in that form.

## Repeat the audit

Run from the public repository, with its Node dependencies and Python on PATH.
The server is localhost-only at port 8329 and uses fictional fixtures. No real
HA instance, integration options, provider, bot, or device may be substituted.

```powershell
$env:FA_CONTROL_AUDIT = '1'
node node_modules/@playwright/test/cli.js test --workers=4 --reporter=line,./tests/helpers/control-audit-reporter.mjs
node tests/helpers/frontend-control-inventory.mjs test-results/frontend-control-audit.json --patch
```

The second command emits a reviewable `apply_patch` patch for the durable JSON;
apply it with the editor's patch tool after reviewing the actual run result.
Do not replace full coverage with a passing partial run. `npm test` verifies
source hashes, all card/module entries, scenario references, and participation
of every browser spec. Normal `npm run test:browser` keeps the instrumentation
off unless `FA_CONTROL_AUDIT=1`; collection changes only the test environment.

To print exact unvisited handler IDs, summary counts, and per-module evidence:

```powershell
node tests/helpers/frontend-control-inventory.mjs --summary
node --test tests/frontend-control-inventory.test.js tests/frontend.test.js
```

Collection keeps source coordinates and action names only. It does not record
input values, payloads, response bodies, household identifiers, or credentials.
The adapter preserves listener removal, method identity, and the original
behavior of fixture methods wrapped by a scenario.
Audit-only local script/page-load failures are attached as
`frontend-load-diagnostics`; they contain synthetic error messages and resource
paths, not WS payloads or response bodies.

## Reproduced runtime defects repaired by this audit

- Changing household/view while a read or write was pending could leave the new
  card permanently loading/disabled. New configurations now own fresh busy flags;
  late old-context responses cannot change them.
- A late router refresh could clear the new context's active write flag. Its
  finalizer now checks the same context fence as the response.
- A slow pre-command projection could suppress post-save readback, then replace
  the saved view with stale data. An independent read sequence invalidates the
  older projection without invalidating the submitted operation/retry identity.
- Ordinary HA state updates repeatedly re-queried an unresolved household picker
  or failed initial load. Those states now wait for explicit/periodic refresh;
  account and configuration changes still initiate a fresh load.
- Opening Archive for a completed/cancelled task or Refund for a fulfilled reward
  re-rendered its history section collapsed, hiding the review form. The matching
  section now stays open during its active review, including failed-save retry.
- A full shopping purchase whose response was lost moved into collapsed history,
  hiding its exact retry. Its active purchase review now keeps history open.
- An invitation clipboard retry retained its previous error, and late clipboard
  completion could affect a different invitation/context. Clipboard status now
  belongs to its exact invitation and is cleared/fenced independently.

The stale pre-command read and unresolved-household refresh findings came from
the requested bounded read-only AGY Gemini 3.8 Flash source review and were
independently reproduced with failing tests before repair. An earlier broad AGY
review timed out and is not verification.

## Source-only control review

`source_control_review` records the one-pass static review of button, listener
and form sites absent from the observed registration frames. Genuine conditional
controls now have named scenarios: document/task pagination, unavailable recurring
assignee removal, local Lovelace editor changes, the panel household selector,
parent alarm Stop, frozen single-task Close, failed-photo-preview Cancel, pantry
archive, manual-service consumable Remove, network profile adoption/delegation,
and routine modes/start/parent override/cancellation.

The remaining static dispositions are deliberately not marked clicked:

- Generic court creation/reversal in `family-assistant.js` is bypassed by the
  dedicated court renderer; the old generic form also has no normal published
  creation route. Specialized editors own the reachable actions.
- The availability helper's error Retry is bypassed by the common card error
  return, which supplies the reachable Retry. Its module/role shells are used.
- Fallback helper listeners for objects without `card.button` do not run in any
  published card, since all inherit `FamilyCard.button`.
- Constructor/form declaration lines, multiline factories, and unsupported
  lifecycle event kinds are not additional user-facing click/submit actions.

These are routing/source dispositions, not a blanket dead-code claim and not
permission to delete compatibility helpers. The complete conservative source
inventory remains available for review.

## Limits

Final bounded audit snapshot: **385/385 Chromium scenarios passed** (55 suites,
3.0 minutes). The manifest contains 81 files and 1,196 conservative source sites;
557 registered handler groups, of which 465 were invoked and 426 received trusted
events. The 92 uninvoked groups remain explicit: one click, zero submit, 51 input,
39 change and one keydown. Another 644 source lines have no registered handler
frame, considering all five collected frames; many are field/helper declarations,
not individual clickable controls. All 115 observed WS action names have resolved
synthetic responses; 59 also have rejected-response cases, leaving 56 without that
failure evidence. These counts do not establish
that every possible button, field combination, role or backend path passed.

The one unrecorded click is the Connections → Configure Telegram native-link
alias (`family-panel.js:546`, caller 531). Its named `control-final-actions`
scenario passed and verified the locally intercepted native destination, but
this full run did not retain that listener's invocation before navigation.
The browser assertion is retained as separate evidence, not converted into a
fabricated invocation or trusted-event count. The language-assistant alias and
Advanced native-link paths have recorded invocation evidence.

The exact remaining file/line/column identities are `handlers` with an empty
`invoked` list (or the `--summary` output). Unregistered source sites are not
silently classified as working: the source-only review above distinguishes real
conditional actions, wrapper declarations and non-published fallback routes.

Unvisited handlers and all untested role/value/time/state combinations remain
open. Native HA configuration links are not followed to a real installation.
Real cameras/microphones, external providers, messages, device effects, full
legacy home/energy parity and household cutover are not covered here. Native
Options, Telegram/backend acceptance and the legacy declaration inventory have
their own separate checks owned by the corresponding workstreams.

`control_notes` classifies no-navigation guards, alternate submit paths, native
navigation boundaries and common recurrence factories. Named scenarios explicitly
submit the school/task selection guards and digest/presence/network/panel forms;
they assert either no mutation or the exact reviewed request. Explicit
`requestSubmit()` retains HTML validation and dispatches a submit event; it does
not establish every browser keyboard/Enter behavior. Trusted-event evidence is
recorded separately. The semantic sweeps also check all 15 panel capability
switches, family/profile failed saves, onboarding packs/back/completion,
native-link discard refusal, read-only recognition, task/reward/calendar/court
transitions, and draft Cancel/Back/hide/close-without-rollback controls.

An intermediate 353-case run had one school-work scenario time out before any
card mounted (the snapshot contained only `main`). No console/network evidence
established its cause. The following focused run passed all 17 school-work cases
and all 10 source-only scenarios; no runtime change was made for that failure.
Load diagnostics were added to make a recurrence diagnosable. This unexplained
intermediate failure is not presented as a reproduced and repaired product bug.

Health's current error workflow returns to its action list and does not retain
the reason form. Its test explicitly reopens the review and enters the same
reason, proving the same operation is reused; it does not claim a persistent
health draft or a one-click retry control exists. Native setup navigation is
intercepted by a local synthetic page and is not native HA Options acceptance.
