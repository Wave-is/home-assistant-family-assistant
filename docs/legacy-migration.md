# Legacy migration contract

Status: read-only preflight, immutable source/member review, private archive codec
and joined conversion proposals; not a complete import or live cutover feature.
The old private integrations remain running until a separately verified switch.
Only synthetic examples belong in this repository.

## Source boundaries

The reviewed legacy Assistant Store can contain either the schema-1 task ledger
directly or an envelope with `ledger`, `alarms`, `memories`,
`processed_home_updates`, and `sent_task_reminders`. The schema-1 Court Store is
separate. A Home Assistant Store file wrapper is not a domain payload: extraction
must validate its key/version and take its `data` explicitly, without guessing.

Task-ledger buckets are `tasks`, ordered `history`, `processed_commands` and
the next task/event sequences. Each task has `task_id`, `kind`, `state`, `title`,
`creator`, optional `assignee`/`reviewer`, `created_at`, `due_at`, report settings,
metadata and lifecycle timestamps. Shopping is a legacy task kind: quantity,
remaining quantity, unit and approval are in its metadata. Reminders are private
to their creator and must not become shared household tasks during conversion.

Alarm data has per-member `weekday`/`weekend` schedules and dated runs. Old runs
can contain plaintext challenge answers and Telegram-specific state. Preserve
them only in an owner-private historical archive; never reactivate a challenge,
output command, penalty or notification by importing a run. Active runs require
an explicit cutover decision. Imported schedules start disabled in shadow mode.

Court history contains events, member references, signed points, the source
week, cancellation details and transport metadata. Historical weeks are separate
from the currently open week. Reconcile current counters against uncancelled
current-week events; never sum all historical weeks into the current balance or
turn a cancelled penalty back into an active penalty.

## Required pipeline

1. Obtain a coherent, local source export and a verified rollback copy through
   the source application's supported API/backup procedure. A read-only scan of
   two independently changing files is not a coherent export.
2. Run bounded, non-mutating preflight. Report only fixed issue codes and counts:
   unsupported schema/status, broken references, ambiguous members/timestamps,
   invalid quantities, inconsistent balances and active alarm runs. Do not send
   source data to an LLM or print task titles, names, IDs or message bodies.
3. Review the explicit old-to-new member mapping. Never infer HA users, Telegram
   bindings, owner/admin roles or router credentials from a name or old log.
4. Build a deterministic conversion proposal with source fingerprint, mapping
   revision, counts, ID mappings, preserved private archive and all exceptions.
   No silent row dropping, invented dates, collapsed people or string truncation.
5. Apply once to an empty, owner-created shadow household through the integration
   runtime and Store API. Match the reviewed fingerprint and mapping under lock;
   write state plus receipt atomically. Never edit `.storage` directly. All
   transports, schedules, network writes and automatic consequences remain off.
6. Compare counts, quantities, statuses, balances, historical references and
   exact replay before/after restarting the isolated target. Test faults and
   rollback. Old transport delivery receipts must not become new command rights.
7. Only after acceptance: quiesce the legacy handler, take a final export,
   reconcile its delta, and explicitly switch one poller and the dashboards.
   Preserve the original source and rollback until the live acceptance is done.

The shared domain name means legacy and public `family_assistant` code cannot
be loaded side by side in one HA process. Shadow acceptance therefore runs in
an isolated HA instance, not by overwriting the working component directory.

## Implemented local review boundary

`migration.review.read_store_pair` accepts already obtained private bytes, not
paths, URLs or credentials. It requires the exact schema-1 Store keys
`family_assistant.tasks` and `family_court.ledger`; unsupported wrapper fields or
versions, duplicate JSON keys, invalid UTF-8, non-finite/unsafe numbers, excessive
depth and size fail with fixed codes. It never reads a live Store itself.

`source.review(mapping, members, mapping_revision=...)` requires a successful
preflight and an explicit old-to-existing-member mapping with current revisions.
Distinct old members cannot silently collapse into one target. An old history-only
system actor can be marked `archive_only: true`, but a task owner, recipient,
reviewer, court subject or alarm member cannot. Mapping never creates an HA user,
role, Telegram binding, command receipt or device permission.

The immutable review pins both raw exports, mapping and all current target-member
fields. `matches(...)` fails if any has changed, even a transport binding without
a revision bump. Its summary contains only counts, fingerprints and fixed status;
`repr` is content-free. Explicitly private payload methods return fresh copies for
the future local converter. These objects must not be sent to an LLM, diagnostic
export or ordinary family view. A matching fingerprint proves unchanged inputs,
not coherent capture: `coherence_verified` and `import_available` remain false.

## Disabled-alarm conversion proposal

`migration.alarm_plan.build_alarm_plan(review, timezone, members=current_members)`
converts the reviewed weekday/weekend schedules into modern save payloads. It
revalidates both frozen sources and every current member field, not just a member
ID. Missing targets, changed bindings, stale revisions, forged reviews and active
legacy wake-up runs fail closed. Source timezone is not guessed: it is an explicit
operator input, included in the immutable fingerprint.

All proposed schedules are **disabled, gentle, zero penalty**, regardless of the
old enabled state. Original enabled flags, finished runs, old challenge material,
delivery metadata and unknown fields remain only in the unchanged decoded alarm
archive accessible through the deliberately private payload method. They cannot
become live challenges, commands, receipts or notification rights. Raw Store-file
bytes remain in the source review. Public summaries contain only fixed status,
counts and fingerprints; returned dictionaries cannot mutate the frozen plan.

This helper has no HA, filesystem, transport or Engine side effects. Modern-domain
tests validate proposed payloads on a fictional state. A future complete converter
must apply a matched whole-source plan under lock to an empty shadow household and
persist its private archive atomically. This helper does not establish coherent
capture, import other task/shopping/court records, expose an import endpoint, or
permit partial household cutover. Private reminders and unknown shopping quantities
must not be silently converted into shared tasks or an invented quantity of one.

The alpha.8 candidate adds explicit `delivery_scope: personal` for convertible
no-report reminders: mapped creator and assignee must be identical, current identity
revision is retained, and the modern task engine permits only that person to view,
complete or archive. No parent review, reassignment, group incident or penalty is
introduced. The complete raw reminder and history remain in the private archive.
See [personal reminders](personal-reminders.md) for privacy and transport limits.
Reminders with unsupported notes/report state still block; later text-history
support below describes convertible ordinary report tasks. This is not a
partial-import permission or a coherence claim.

## Joined conversion review and private archive

`migration.conversion.build_conversion_review(review, timezone, members=...)`
collects alarm, task, shopping and current-score proposals in a single immutable
review. Its summary exposes fixed codes, counts and fingerprints only. Every
blocked row remains present in the owner-private source archive. Raw sources are
stored once, with the reviewed mapping, not as repeated overlapping copies.
There is still no apply endpoint or claim of coherent capture.

`migration.archive.encode_private_review` produces **private bytes containing the
entire source**, not a sanitized diagnostic export. Keep them only in owner-private
local storage or backup; never send them to an LLM, public issue, ordinary family
view or log. `decode_private_review` preserves the exact original Store-file bytes
and revalidates all current target identities before accepting a saved review.
Strict envelope/version/UTF-8/base64/size and JSON checks reject malformed input.
Fingerprints detect changed inputs; they are not an authorization token or a
signature against someone who can rewrite the archive. The codec does not itself
read or write files. The isolated HA test roundtrips it through the real Store API.

Shopping proposals preserve source creators, assigned buyers, partial quantities
and current approval state. Unknown quantities, precision finer than the modern
six-decimal model, unsupported states and names over 200 characters are explicit
blockers, not guesses or silent truncation. Cancellation never becomes approval
or a purchase. A cancelled pending proposal is non-active archived work; the
original approval and history remain private. Legacy transport/history events
are not fabricated as new authenticated shopping commands.

Court proposals seed only uncancelled events from the **source open week**, keeping
their original reasons and timestamps. Prior weeks and cancelled events remain
in the full private archive, without resurrecting their scores. The source's
current plus/minus counters must reconcile before review. A missing period or an
unrepresentable current reason is a blocker. Old Telegram parent identifiers are
not converted to a current authenticated actor; no role or approval is inferred.
This requires explicit historical attribution handling at the future apply step.

Task proposals currently cover ordinary no-report records with supported states,
preserved dates and zero reminder/penalty settings. When pre-overdue metadata lags
behind a later acceptance/start, a complete source history must reconcile the
current assignment, metadata and exact activity times before proposing its real
progress. Incomplete evidence or a source revision that actually rewound progress
still blocks; a timestamp alone is not proof. Convertible no-report personal reminders retain their self-only scope;
text-report tasks can now produce proposals from complete explicit event history.
Their reviewer and review actors must map to current owner/parent identities;
the proposal explicitly states the modern `household_parents` review policy.
The source history, submission timestamps, prior reports, feedback and separate
completion/cancellation/archive notes remain distinct. An old empty report is
preserved as empty, not fabricated or automatically completed. Unknown events,
inconsistent timestamps/notes and unverified assignment chains are explicit blockers.
Explicit reassignment archives the former assignee's report and review with
identity/submission/reassignment stamps. The new assignee receives no old report;
assigning back does not restore one. Old reports remain parent-only.
No-report tasks and personal reminders reconstruct separate terminal notes from
explicit history without inventing a submission, review authority or approval.
Nonparent designated reviewers require a separate authority review. The complete
old/new reviewer-set comparison still belongs to capture/cutover acceptance;
the proposal does not grant a role or constitute authorization to import.
A photo-required task with no historical submission can preserve its future
photo requirement and explicit lifecycle outcome without creating any attachment.
An old direct parent completion must have an explicit authorized source event;
it does not claim a photo exists. Any historical photo submission still requires
evidence resolution, even after rejection, reassignment or completion. A Telegram
photo reference is not a verified local attachment. All original notes and history
remain in the private archive.
`getFile` requires a file identifier; an old event/message reference alone is not
one. Telegram's pending update queue is not a history archive and retains updates
for at most 24 hours. Forwarding a message is a new external send, not read-only
retrieval, so it is not used as an automatic migration probe.
See [Telegram Bot API: updates](https://core.telegram.org/bots/api#getting-updates),
[files](https://core.telegram.org/bots/api#getfile) and
[forwarding](https://core.telegram.org/bots/api#forwardmessage).
**Zero reminder and penalty settings alone are not a shadow isolation mechanism:**
an open overdue task can still produce an incident when its module is activated.
The complete shadow runtime must keep all modules/transports/effects off, then
explicitly review activation. These planners must not be used for partial cutover.

## Explicit reviewer-set comparison

`migration.reviewer_policy.build_reviewer_policy_review` compares an explicitly
supplied **complete** old effective reviewer set for every report task with the
current target `household_parents` set. A designated reviewer alone may not be the
effective set: the legacy controller can also allow configured parents. The source
adapter must capture that policy; names and previous successful reviews do not prove it.

The schema-1 policy pins its revision and exact source/mapping review fingerprint.
Its per-task coverage must be exact, include each designated reviewer, exclude
duplicates and resolve every old actor through the explicit immutable mapping.
No identities are inferred or promoted. Private output lists mapped old, current,
added and removed reviewers per task. Public summaries contain fixed status, counts
and fingerprints only. Member, binding, source or policy changes invalidate replay.

`build_conversion_review(..., reviewer_policy=...)` includes this comparison in the
joined fingerprint/private payload. Omission is explicit `not_supplied`, never
implicit acceptance. Added/removed reviewers require a separate decision; historical
nonparent authority is not converted into a current role. Even equivalent sets do
not prove the supplied policy is truthful or coherently captured: `source_policy_verified`,
`coherence_verified` and `import_available` remain false. This is one acceptance gate,
not an import endpoint, source exporter, role grant or partial-cutover mechanism.
