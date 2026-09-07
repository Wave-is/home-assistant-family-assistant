# Legacy migration contract

Status: read-only preflight, immutable source/member review and disabled-alarm
conversion proposals; not a complete import or live cutover feature.
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
