# Family polls: bounded local domain contract

This checkpoint implements a deliberately small family decision tool, not a survey or an
opinion-inference system. A poll contains one question, two to ten choices, and an explicit
electorate of one to fifty current household members. It never changes tasks, points,
devices, alarms, routines, shopping, or any external service.

## State and limits

`polls` stores at most 500 definitions, including at most 100 open polls. IDs use the `PL`
sequence. Open and closed records contain an immutable `definition_revision` (currently
`1`), question, ordered `{id,label}` choices, exact `{member,member_revision}` electorate,
UTC `closes_at`, creator epoch, and status timestamps. A separate `poll_ballots` bucket maps
poll ID and member ID to the member epoch, option ID, independent ballot revision, and local
timestamps. This mapping is private internal state.

Questions are at most 240 characters; option labels are at most 120 and case-fold uniquely.
Deadlines are aware timestamps, normalized to whole-second UTC, and must be between five
minutes and thirty days after creation. A caller must explicitly acknowledge the limits of
the private-ballot model during creation.

Commands are:

- `create`: parent/owner, with current `actor_revision`, question, options, exact eligible
  member epochs, deadline, and `confirm_private_ballot_limits: true`.
- `vote`: an eligible member, with poll ID, immutable definition revision, current voter
  revision, option ID, and `ballot_revision` (`null` for the first vote). A member may change
  a vote until closure; only that ballot revision advances.
- `close`: parent/owner, with exact poll and actor revisions. This may close early.
- `archive`: parent/owner, with exact closed poll and actor revisions.
- `purge`: owner only, exact archived revision and `confirm_delete: true`.

Every command has strict exact fields. Poll lifecycle receipts contain only
`{id,revision,status}`, vote receipts only `{id,ballot_revision}`, and purge receipts only
`{id,status:'deleted'}`. Thus Engine audit and idempotency records do not acquire question,
choice, electorate, or ballot content.

## Time, results, and restart behavior

`tick(ctx)` closes overdue records using the recorded deadline as `closed_at`; it has no
outbox or other side effects. `view(state, actor, now)` can project an overdue open record as
closed before the next durable tick, but only when its caller supplies `now`. Omitting `now`
does not read the wall clock. Root Engine integration must pass its explicit request time and
call `polls.tick` from the existing clock transaction; this is not a second scheduler.

Results are counts in original option order plus `cast_count`. No voter-to-choice mapping is
ever projected. A member epoch change revokes that identity's live eligibility and own-ballot
view, but a ballot validly cast under the frozen electorate remains in the final aggregate.
This makes results deterministic after membership edits without resurrecting the old
identity's access.

## Projections and privacy

The projection is `{open,closed,archived}`. An active non-guest voter sees only polls where
their exact current epoch is eligible, their own `{option_id,revision}`, and aggregate results
only after effective closure. Parents see all live polls plus the electorate and a derived
`current` flag, but still never see individual ballot choices. Only parents see archived
polls; only an owner receives `can_purge`.

Archiving freezes aggregates and electorate size, removes the entire ballot mapping, and
removes eligible and creator identifiers from the definition. The card/API projection is
bounded to the newest 100 archived records. Records are never automatically deleted; the
owner's explicit purge is the only deletion path. This prevents an unbounded ballot-history
store while retaining a reviewable aggregate and an explicit retention decision.

Telegram and cards should render the same authorized projection. Private Telegram chats may
offer vote buttons carrying the displayed definition and ballot revisions. Family-group
messages must not collect or reveal votes; a group message may at most direct an eligible
member to their private view. All labels are untrusted text and require normal platform
escaping. There are no automatic reminders in this slice.

## Integrated boundaries

The Engine prepares additive private ballot/review buckets, dispatches `polls.*`,
reauthorizes cached receipts, projects current authorized views, closes due polls and
prunes expired reviews in its existing clock transaction. Config Flow owns only module
opt-in; it does not hold poll content. The dedicated card uses the same domain commands.

Telegram stores opaque five-minute review descriptors, not rendered questions or options
in the outbox. Actor epoch, bot, recipient, exact review and expiry are checked at claim
and again at transport. Confirmation updates reuse the review's first operation ID.
Private poll quotes are not automatically forwarded to the model. The numbered list
builds complete question blocks with scoped buttons; truncation never leaves buttons for
an omitted question. See the [user guide](polls.md).

There are no reminders or downstream automatic actions. Access to older archives beyond
the bounded newest-100 view, global journal retention and production acceptance remain
separate gates; they are not implied by the local domain and synthetic adapter tests.
