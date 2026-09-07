# Legacy migration contract

Status: design and read-only preflight; not an import or live cutover feature.
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
