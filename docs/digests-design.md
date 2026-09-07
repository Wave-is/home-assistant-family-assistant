# Private family digests: first implementation contract

Status: design only. The product vision names personal morning and evening digests
([vision](vision.md#714-голосования-дайджесты-и-присутствие)); the implementation status still lists
digests as planned ([implementation status](implementation-status.md)). This contract adds a
bounded daily/weekly notification slice. It is not an activity feed, surveillance report, or
general export of `Engine.view`.

## Product and privacy boundary

A digest is generated for one current household member and is delivered only to that same
member's current private Telegram binding. A parent cannot subscribe another person, and a
family-group target is never valid. Owner policy enables a digest kind for the household; a
member's separate self-consent enables delivery to that member. Owner, parent, adult, and child
may consent for themselves while current and active. Guests receive no projection and cannot
subscribe.

The first slice supports three kinds through one implementation:

- `morning`: items for the scheduled local date;
- `evening`: items for the next local date;
- `weekly`: items for the seven local dates beginning on the day after its scheduled weekday.

The schedule is a convenience summary, not evidence that a person saw or completed anything.
It never changes a task, routine, shopping item, pantry quantity, poll, score, reward, penalty,
financial value, device, alarm, or presence state. It never calls an LLM or external search.

Counts are still personal information and may reveal one person's state in a small household.
"Counts only" therefore means data minimization, not anonymity. All counts are computed only
from rows that the recipient could currently open through the corresponding domain projection.

### Detail versus counts

The renderer builds a fresh, recipient-specific snapshot from explicit allowlists. It must not
serialize the general `Engine.view` result or scan raw buckets and filter afterward.

| Source | Detail permitted | Counts permitted |
| --- | --- | --- |
| Tasks | Current tasks assigned to the recipient: title, status and due time only | Parent/owner may receive a total for other currently authorized tasks; other roles only their own total |
| Calendar | Confirmed occurrences where the recipient is a participant, escort or creator: title and time only | Count of other occurrences, including family-visible events, already visible to that recipient |
| Routines | Recipient's current assigned step: routine title and step title only | Count of other shared runs visible to that recipient |
| School | Child recipient's own current lessons: subject, start time and bounded materials | Parent/owner receives counts only; no child lesson titles, rooms, materials, homework reports, or backpack contents |
| Shopping and pantry | No item names, notes, provenance, quantities, expiry dates, or proposal text | Current authorized open-shopping, low-stock and expiring-item totals only |
| Maintenance | Recipient's own assigned ordinary task may appear under Tasks | Current authorized open fault/service totals only; never asset notes, serials, warranty, documents or fault reports |
| Polls | No question, choice, electorate, option result, own ballot or voter mapping | Number of currently eligible open polls and closed result sets available to the recipient |

Meal plans and recipes are excluded from the first slice. Court, rewards, point balances and
transactions, alarms, MikroTik/network state, notification history, audit/journal entries,
assistant memory, operation IDs and channel identifiers are also excluded.

The following never enter either details or counts: dietary profiles or allergy notes, presence
observations or entity IDs, media IDs/metadata/bytes, task report or review text, historical
reports, poll ballots, routine conditions/nonces, private pantry notes, correction phrases, and
raw HA attributes. A future source must be added to the allowlist with its own privacy tests; a
new `Engine.view` field is not included automatically.

Each section is capped at 10 detail rows, sorted deterministically by local time then stable ID.
Overflow is rendered as a count. The whole Telegram message is capped at 3,800 characters and
uses escaped/unformatted user text with link previews disabled. RU, UK and EN templates state
when a section is counts-only. Truncation removes a complete trailing row, never half a title.

## Settings, consent and projection

Add module key `digests`, disabled by default. Owner-managed settings are additive fields of
`settings.save` and preserve their previous values when omitted:

```text
digest_morning_enabled: bool = false
digest_morning_time: HH:MM = "07:00"
digest_evening_enabled: bool = false
digest_evening_time: HH:MM = "19:00"
digest_weekly_enabled: bool = false
digest_weekly_weekday: int = 6       # Monday=0, Sunday=6
digest_weekly_time: HH:MM = "18:00"
```

Times use the household `settings.timezone`; malformed zones, booleans used as weekdays, and
values outside `0..6` are rejected before mutation. Two enabled kinds may share a time, but they
remain visibly separate messages with separate markers. `settings.digest_policy` is the dedicated
owner-reviewed full-policy action; the general settings action also preserves and validates these
additive fields. Both advance `settings.digest_policy_revision` on any effective policy, time zone
or Digests-module change. `policy_fingerprint` covers that monotonic revision, module state, time
zone and all seven fields, so an A → B → A change cannot revive an older queued descriptor.

`digests.access_set` accepts exactly:

```text
{
  recipient_revision,
  subscription_revision,   # null to create, strict current revision to update
  morning, evening, weekly  # strict booleans
}
```

The authenticated actor is always the recipient; there is no recipient field to forge. Creation
with all three values false is rejected. An existing subscription may disable all kinds and is
retained as a tombstone-like preference record. Stored records contain only recipient ID and
epoch, the three booleans, revision and update timestamp. Any member edit, deactivation, guest
transition or role change makes the record ineffective and requires fresh self-consent. A cached
command receipt is returned only while the same actor epoch and exact resulting subscription are
current. The opaque receipt is `{revision,status:"enabled"|"disabled"}`.

`digests.view(state, actor)` returns only the current actor's controls:

```text
{
  policy: {
    timezone,
    morning: {enabled,time}, evening: {enabled,time},
    weekly: {enabled,weekday,time}
  },
  self: {
    recipient_revision, subscription_revision,
    morning, evening, weekly, can_edit, health
  } | null
}
```

It never returns another member's subscription. With the module disabled or an invalid/guest
actor it returns `{policy:null,self:null}`. `health` is only `ok` or `attention` for the actor's
own delivery state; it contains no event IDs or other recipients. Generic `Engine.view` may carry
this control projection, but not digest contents. A card preview, if implemented, uses a separate
authenticated `family_assistant/digest_preview` WebSocket command that resolves the same current
actor and invokes the bounded snapshot builder. The LLM planner cannot invoke consent or preview.

## Scheduling, descriptors and delivery

`digests.tick(ctx)` runs inside the existing Engine tick transaction. It does no work unless the
module, global kind policy, and a current matching self-subscription are enabled. It uses
`recurrence.local_clock` for the configured local date and time: a nonexistent spring-gap time is
skipped, and the first autumn-fold occurrence is selected once. A trigger is eligible only from
its exact instant through five minutes later. Downtime outside that window produces no catch-up.

The period keys are `YYYY-MM-DD/morning`, `YYYY-MM-DD/evening`, and
`YYYY-Www/weekly:<scheduled-local-date>`. Before notifying, tick computes only whether at least
one allowed section is nonempty. It does not persist the snapshot. One marker key is the compact
JSON tuple `[recipient,kind,period_key]`.

The outbox key is `family_digest`. Its data has exactly:

```text
{
  schema: 1,
  kind,
  period_key,
  window_start, window_end,        # ISO local dates; end is exclusive
  recipient_revision,
  subscription_revision,
  policy_fingerprint,
  scheduled_at, expires_at         # aware UTC timestamps
}
```

There are no titles, names, member/source IDs, counts, choices, notes or rendered fragments in
the descriptor. The outbox's existing `recipient` is the sole routing identity. The marker value
contains only `event_id` and the same recipient/subscription/policy revisions. Evening messages
expire six hours after the scheduled instant and weekly messages after 24 hours. Morning messages
expire at the earlier of six hours or the next household-local midnight, so a deliberately late
"morning" schedule cannot turn into a backdated next-day summary. The five-minute creation window
is not the delivery expiry.

`delivery_allowed(state,event,now)` is pure and fail-closed. At notification claim and again
immediately before transport it checks the exact event schema, digest module, current policy and
fingerprint, current active non-guest recipient epoch, exact enabled subscription revision/kind,
matching marker, expiry, and that a freshly authorized snapshot is nonempty. The target resolver
returns only that recipient's current bot/private-chat binding. The Telegram renderer repeats
recipient/target validation and rebuilds content from a fresh state snapshot immediately before
send. A disabled source module or revoked row simply disappears; if no allowed content remains,
the event is superseded. Normal task/calendar changes may update the eventual digest rather than
invalidating it, because no old content was persisted.

Existing quiet hours remain authoritative. They may defer a non-urgent digest, but never beyond
`expires_at`; after expiry the event is superseded rather than delivered late. Disabling the
module, global kind, self-subscription, recipient or Telegram binding supersedes pending and
`awaiting_channel` work and pending deliveries. A `sending`, `sent`, or `uncertain` transport is
not described as recalled: revocation is checked up to transport dispatch, and a network request
already in flight cannot be withdrawn.

The marker survives policy disable/re-enable and source edits for its period, so neither produces
a duplicate. Store rollback leaves marker and event atomic because both are created in one Engine
transaction. A restart in the trigger window observes the persisted marker.

## Retention and health

Daily generation makes a marker-only cap insufficient: it would eventually become a permanent
outage while old outbox rows continued growing. The first implementation therefore includes
digest-specific pruning in tick, before capacity checks:

- sent, superseded and resolved daily marker/event pairs are removed after 35 days;
- sent, superseded and resolved weekly pairs are removed after 16 weeks;
- failed pairs are retained for 90 days for diagnosis, then removed;
- pending, `awaiting_channel`, sending and uncertain pairs are never pruned automatically.

Pruning requires an exact marker-to-event match, key `family_digest`, terminal state and an
expired retention horizon. It removes the marker and its digest outbox event together, never an
unrelated notification. It stores no content archive. Digest markers and retained digest events
are each capped at 10,000. At either cap, tick creates nothing and a counts-only
`digest_retention_attention` health issue is exposed to the household owner through HA Repairs;
it contains retained/unresolved totals but no recipient or event identifiers. Resolving uncertain
delivery remains an explicit existing notification workflow. Pruning and health transitions must
not mutate state on every clock tick.

`digest_retired` holds at most three monotonic local scheduled dates, one per kind.
Deleting exact canonical marker/event pairs advances the corresponding retired-through
date in the same Engine transaction. Creation rejects older/equal scheduled dates for
every recipient even after clock, policy, module or time-zone rollback. This compact
boundary never deletes unresolved events or resets on configuration changes. Malformed
boundaries fail closed and expose retention health. Displayed and in-flight card
previews are invalidated by an observed global state revision or module-list change;
the independent subscription retry scope does not use that content version.

## Integration points and acceptance

The implementation slice needs `domain/digests.py` (`handle`, `authorize_replay`, `view`, `tick`,
`delivery_allowed`, `snapshot`, and bounded pruning), additive Engine buckets
`digest_subscriptions`, `digest_markers` and `digest_retired`, module/settings validation and Engine dispatch/tick/
projection wiring. Notifications registers `family_digest` with both current-source gates.
Telegram adds private targeting and RU/UK/EN send-time rendering. Config Flow exposes owner global
policy; the dedicated card exposes only self-consent and authenticated live preview. No new
scheduler, HA entity, device service, family-group command, or assistant tool is added.

Focused acceptance must prove:

1. strict self-only consent, revisions, role/active/module checks, stale replay rejection and
   Store rollback without partial subscription writes;
2. parent, adult and child snapshots include only their authorized details/counts, with sibling,
   report, media, dietary, presence, ballot, audit and identifier canaries absent;
3. spring-gap skip, first-fold exactly once, weekly weekday boundaries, five-minute window,
   restart deduplication and no downtime catch-up under the household zone;
4. policy/timezone, recipient epoch, role, module, subscription and Telegram-binding revocation
   after durable enqueue all block claim or final dispatch;
5. source revocation during quiet-hour deferral removes that source, an empty digest is
   superseded, and an already-started network send is reported honestly;
6. quiet hours defer within the applicable morning-midnight, six-hour or 24-hour TTL and expiry
   prevents a stale send;
7. concurrent ticks, Store faults and exact retries create one event/marker per recipient, kind
   and period and never duplicate after disable/re-enable or source edits;
8. the outbox, audit, LLM and card-control projections contain no rendered text, source counts,
   source IDs or excluded-domain canaries; health contains only bounded operational totals, and
   only the dedicated preview and final private renderer receive the content snapshot;
9. row/message caps, hostile Unicode/markup, deterministic ordering and RU/UK/EN truncation keep
   complete sections under Telegram limits with link previews disabled;
10. retention deletes only exact old terminal digest pairs, preserves pending/sending/uncertain
    and unrelated notifications, stops safely at capacity, and raises/clears counts-only health;
11. tick/render leave tasks, shopping, pantry, routines, polls, court/points, media, presence,
    devices and external transports unchanged except for the one durable digest intent and its
    normal delivery receipts;
12. actual HA WebSocket tests use two linked users to prove self projection and preview isolation,
    reload persistence, private Telegram targeting, final send-time revocation, and zero family-
    group or LLM output.

Advanced natural-language summaries, presence-aware delivery, user-selected sections, historical
analytics, attachments, email/push channels and cross-household delivery remain later gates.
