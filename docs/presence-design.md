# Opt-in household presence design

Status: proposed first slice; no presence runtime is implemented yet.

## Product boundary

The vision asks the Today view to show who is reported at home and later allows
non-urgent reminders to be delayed until someone returns. It also explicitly
forbids critical conclusions from one presence sensor
([vision](vision.md)). The first slice is therefore display-only evidence. It
does not suppress or send notifications, start routines, complete tasks, change
penalties, operate devices, or make safety/security decisions.

Presence is a separately configurable module, disabled by default. It reads one
explicitly selected Home Assistant `person` or `device_tracker` entity per
family member. It never discovers trackers, follows device-registry links, or
adds an entity from another module's allowlist. Configuring a source is not the
subject's consent to read or share it.

The following are deliberately outside this slice:

- coordinates, zones, routes, distances, travel times, and location history;
- Bluetooth, Wi-Fi, MikroTik, camera, alarm, or phone telemetry fusion;
- Telegram presence messages or family-group summaries;
- exposing presence to an LLM, search provider, Assist tools, diagnostics, or
  Home Assistant entity attributes;
- automatic “notify only at home” or “notify on return” policies. Those need a
  later reviewed, non-urgent notification contract and contradictory-evidence
  handling; the display result here is not sufficient authority.

This separation is important because routine conditions already have their own
owner-approved entity allowlist and three-valued stale-state evaluator
([routine_conditions.py](../custom_components/family_assistant/domain/routine_conditions.py),
[routines.py](../custom_components/family_assistant/domain/routines.py)). A
presence source must not be copied into that allowlist or become an implicit
routine condition.

## Consent and authority

The conservative first-slice rule is self-consent: an active, HA-linked,
non-guest member enables or disables only their own presence subscription.
Owners and parents cannot enable another member's subscription. They may remove
an entity binding in Options, which stops collection but does not manufacture a
consent change. A member without a linked HA user cannot opt in in this slice;
guardian-managed presence for such a child is an explicit product/legal-policy
decision, not an owner shortcut.

When enabled and current:

- the subject sees their own evidence;
- an owner or parent sees evidence shared by enabled subjects;
- an adult or child never sees another member's evidence;
- a guest sees no presence section and cannot act.

The member record revision binds both consent and source configuration. Any
member edit, deactivation, role change, unlink, or role round trip invalidates
the old consent and binding. The subject must explicitly opt in again after an
owner rebinds the source to the new member revision. This follows the existing
conservative consent-revision pattern used for dietary profiles
([dietary_profiles.py](../custom_components/family_assistant/domain/dietary_profiles.py)).

The recommended UX must state that enabling shares only the normalized
`reported home` / `reported away` / `unknown` evidence and its observation
time with current owners and parents. It must not claim continuous tracking,
confirmed occupancy, safety, or precise location.

## Durable domain state

Add a top-level `presence` bucket containing only versioned source lineage and
subscriptions:

```text
presence = {
  bindings: {
    <member_id>: {
      member, revision, member_revision, status,  # active | removed
      source_hash?                                # active only; never projected
    }
  },
  subscriptions: {
    <member_id>: {
      member, revision,
      member_revision, binding_revision,
      status,                 # enabled | disabled
      created_at, updated_at
    }
  }
}
```

The binding map is the Engine's content-minimized mirror of Config Entry source
lineage. It contains no entity ID. `source_hash` detects an unsupported same-
revision source replacement and is removed from a binding tombstone; it is never
projected, journaled, or included in diagnostics. A supported source change or
removal advances only that member's binding revision. This avoids both global
revocation and remove/re-add ABA.

There is at most one subscription per member. A disabled record is a content-free
tombstone: it retains `member`, `revision`, `member_revision`,
`binding_revision`, `status`, and timestamps, but no entity ID or observation.
Re-enabling requires the exact
disabled-record revision, so disabling cannot be bypassed by replaying an old
create. Observed states and observation times are never persisted in the
Engine Store, audit, processed result, memory, outbox, or incident records.

Use one action:

```text
presence.access_set {
  member,
  member_revision,
  binding_revision,
  subscription_revision,    # null only when no record exists; strict current int otherwise
  enabled                    # strict bool
}
```

The actor must be the named member, current, active, non-guest, and linked to
the authenticated HA user. `member_revision` and `binding_revision` must equal
the current member and content-minimized binding mirror. New records require `subscription_revision: null`; an existing active
or disabled record requires its strict positive revision. Exact fields only;
booleans are never accepted as revisions. A new disabled record is rejected as
an invalid transition. The opaque receipt is exactly
`{member, revision, status}`.

`authorize_replay(ctx, "access_set", payload, result)` rechecks the Presence
module, current self identity, active/non-guest role, exact current member
and binding revisions, and the current subscription lineage. A stored receipt never restores
access after module disablement, membership change, deactivation, unlink, or a
newer enable/disable decision. Same-operation/same-payload replay is handled by
the existing Engine processed journal before the domain handler; a changed
payload with the old operation ID remains an idempotency conflict
([engine.py](../custom_components/family_assistant/domain/engine.py)).

No notification is created by this action. The Engine audit and processed
journal retain the command fingerprint and opaque result, not the payload; the
result contains neither an entity ID nor observed state. Batch behavior remains
atomic through the existing copied-state Engine transaction.

## Source configuration in Options

The Config Entry options hold source identifiers because they are HA adapter
configuration, not family observations:

```text
presence_sources: {
  <member_id>: {
    revision: <strict positive safe integer>,
    status: "active",
    member_revision: <strict positive safe integer>,
    entity_id: "person.name" | "device_tracker.name"
  }
  # Removal retains {revision, status: "removed", member_revision} without entity_id.
}
presence_max_age_seconds: 300
```

Limits: at most 20 active bindings and 100 active-plus-removed lineage records,
one source per member, one member per source,
entity ID at most 255 characters, and max age a strict integer from 30 through
3600 seconds. The entity must exist in the HA entity registry and have exactly
the `person` or `device_tracker` domain. A currently missing or unavailable
state is allowed at configuration time and later projects as unknown; selecting
an arbitrary syntactically valid but unregistered ID is rejected.

Only the current family owner may edit these Options. A source change or removal
increments only that member's revision; removal retains the content-free record
so re-adding cannot return to an old revision. The flow freezes the displayed
binding revision and every selected member revision. It rechecks owner
identity, config-entry generation, backup gate, source revision, member epochs,
entity-registry identity, domains, duplicates, and limits immediately
before committing. A stale form conflicts rather than rebasing. Options should
use the HA entity selector restricted to the two domains, show the member name,
and explain that a binding remains unread until that member opts in. The current
HA owner must also pass Home Assistant's own
`user.permissions.check_entity(entity_id, POLICY_READ)` check for every selected
entity. A family role never grants HA entity access.

This requires a dedicated `presence_sources` item in the existing Options menu
as well as the Presence switch in the general module list
([config_flow.py](../custom_components/family_assistant/config_flow.py)). The
Engine Store and Config Entry options are not one transaction. Before committing
Options, an internal `Engine.system_update` calls
`presence.sync_bindings(ctx, proposed_options)`. It validates monotonic
per-member revisions and persists only `{member, revision, member_revision,
status, source_hash?}`. The epoch and source-hash comparisons make every partial
outcome fail closed: either side being newer prevents reads, a member change
makes the old binding inert, and a source form cannot commit a binding for a
member epoch that is not already current. Retrying an identical sync is
idempotent. No workflow should attempt a coupled member edit and source edit as
if they were atomic.

Turning the Presence module off must stop all reads and self-consent commands
immediately. Owner-only source Options may still be prepared, replaced, or
removed while the module is off; this grants no consent and performs no source
read. Bindings may be retained in private Config Entry options so
reconfiguration is not destructive, but they remain inert and are removed from
diagnostics. Explicitly removing a binding clears it from current options;
neither action claims erasure from backups. A later explicit purge/export policy
is separate.

## Ephemeral observation adapter

Add a small adapter such as `presence_observations.py`; it reads HA state only
on an authenticated Family Assistant view request. The first slice needs no
`state_changed` listener, polling task, scheduler hook, or retained cache.

The adapter first obtains the current Engine snapshot and calls
`presence.select_sources(state, actor, options)`. The pure helper returns only
source IDs whose module, binding epoch, enabled consent, and requesting actor's
self-or-parent projection authority are all current. A child or adult therefore
cannot cause even an in-process read of a sibling's source. The adapter calls
`hass.states.get` only for that bounded set. For each
source it copies exactly:

```text
{state: <string>, observed_at: last_reported or last_updated}
```

The snapshot, Config Entry options, source reads, and final pure projection are
performed synchronously without an `await` boundary. A later implementation
that introduces I/O must recheck actor, module, member, consent, source revision,
and entry generation after that await before returning anything. The adapter
checks the requesting HA user's
`permissions.check_entity(entity_id, POLICY_READ)` before each `hass.states.get`.
If permission is absent it does not read the state and supplies no observation;
the pure projection shows `unknown/unavailable`, including in a parent's shared
row. Subject consent and a Family Assistant parent role never override HA's
permission policy. The adapter
must not copy attributes. In particular, latitude, longitude, GPS accuracy,
address, source device, battery, zone name, friendly name, and entity ID never
enter a family projection. The Config Entry options snapshot/revision is passed
back to the pure projector, which rechecks it before returning data. Module,
member, binding, consent, or entry-generation drift produces no evidence.

Normalization is deliberately lossy:

- exact `home` with a fresh aware timestamp becomes `reported_home`;
- exact `not_home`, or another non-empty HA zone state, becomes
  `reported_away`; the actual zone string is discarded;
- missing, `unknown`, `unavailable`, non-string, malformed/future-dated, or
  older-than-configured evidence becomes `unknown`;
- a timestamp more than five seconds in the future is unknown;
- negation never turns unknown into home or away.

This is evidence from one configured source, not an occupancy fact. UI text
must use “reported” wording and show stale/unavailable honestly. An unavailable
source never preserves the last good value.

## Engine and projection contracts

Wire `presence` into `const.MODULES`, `CONFIGURABLE_MODULES`, `Engine.HANDLERS`,
`Engine.BUCKETS`, additive old-state preparation, dispatch, and replay scope.
Adding the bucket to `BUCKETS` covers new households; `setdefault`-style state
preparation covers old households without an incompatible schema-version bump.
Do not change the signature or privacy contract of `Engine.view`. The adapter
delegates to the pure domain function:

```text
presence.view(state, actor, options_snapshot, observations, now)
```

The pure function validates every untrusted option and observation field and
fails closed without raising on malformed HA evidence. It returns:

```text
{
  self: {
    member, member_revision, subscription_revision,
    enabled, can_edit,
    status,                 # reported_home | reported_away | unknown
    reason,                 # fresh | stale | unavailable | unconfigured | not_shared
    observed_at             # aware ISO timestamp or null
  } | null,
  shared: [
    {member, member_revision, status, reason, observed_at}
  ]
}
```

`self` exists for an active non-guest actor even when disabled, allowing a
current linked member to opt in. Its disabled state has `unknown/not_shared`
and no observation time. `shared` exists only for owners/parents and includes
only other members with a current enabled subscription and current binding;
unconsented members are omitted rather than represented by a status. Guests
receive `{self: null, shared: []}`. Rows contain no entity ID, raw HA state, zone,
coordinates, device identifiers, history, or actor/uploader metadata.

The authenticated WebSocket `family_assistant/view` handler calls a narrow
adapter such as `presence_projection(runtime, entry, actor_id, now)` and appends
its result after the normal `actor_for_ha` and `Engine.view` checks. Direct
`Engine.view`, which is used by conversation and Telegram, deliberately does
not include presence.
The assistant's explicit projection allowlist must also remain unchanged
([plans.py](../custom_components/family_assistant/assistant/plans.py)). Read
Family, diagnostics, entities, notification rendering, and group Telegram must
not add presence fields in this slice.

## Revocation and failure behavior

Revocation is effective on the next view and before any read:

- access disable: no source read and no shared row;
- module disable: no source read, action/replay denied, no projection;
- binding removal/change: old source is not read; current subscription projects
  unknown/unconfigured until a current binding exists;
- member edit, role change, deactivation, unlink, or entry/user change: old
  consent and binding are ineffective and any focused card draft is discarded;
- HA source removal/unavailability/staleness: unknown, never cached home/away.

Because collection is synchronous and local, there is no provider response to
recall. The final projector receives the same immutable state/options snapshots
used to choose sources; there is no event-loop interleaving in the adapter call.
Ordinary Store failure
leaves consent unchanged. Backup mode rejects access mutations through the
existing Engine gate; the read-only projection may remain available from the
already coherent state, consistent with other views.

The card must have separate source-configuration (owner Options) and personal
consent UI. Consent changes use a named review, exact member/subscription
revisions, explicit confirmation, and a frozen operation ID. A failed transport
retains only the exact payload for retry. Any uncommitted authority drift drops
the draft. A committed lost response may retry the exact operation through the
Engine journal, but it must never silently adopt a newer subscription or member
revision.

## Acceptance gates

Implementation is not complete until synthetic tests cover all of the following:

1. Domain validation: exact fields, strict booleans/revisions/ranges, self-only
   access, guest/inactive/unlinked denial, create/disable/re-enable tombstone
   lineage, revision overflow, batch rollback, Store failure, restart, concurrent
   operations, exact replay authority, and inert retention (not automatic
   pruning) after member deactivation.
2. Consent revocation: member edits and adult/child/parent role cycles never
   resurrect consent; disabling, module-off, and unlink deny replay and perform
   zero HA state reads.
3. Options: owner-only access, stale source/member revisions, duplicate member
   or entity, wrong domains, unregistered entities, malformed max age, backup
   gate, changed entry/user while a form is focused, and preservation of
   unrelated options.
4. Observation matrix: fresh home/not-home/named-zone, unknown, unavailable,
   missing, empty/whitespace/non-string states, stale, exactly-five-seconds and
   more-than-five-seconds future timestamps, naive/malformed timestamps,
   malformed state objects, and max-age boundaries. Assert `hass.states.get` is called only for the exact
   currently consented allowlist for which the requesting HA user has
   `POLICY_READ`, denied entities are not read and project unknown, and no
   attributes are copied.
5. Projection privacy: self, consenting adult, owner/parent, child, sibling,
   inactive member, guest, and separate household. Canary coordinates, zone
   names, entity IDs, tracker attributes, and source device IDs must be absent
   from serialized projections and browser DOM.
6. External isolation: the same canaries are absent from assistant messages and
   tool schemas, Telegram private/group rendering, outbox, audit results,
   diagnostics, Read Family entities, repairs, and logs. Viewing presence makes
   no task, routine, notification, network, alarm, or device write.
7. Real HA adapter acceptance with synthetic `person` and `device_tracker`
   entities: entity-registry validation, current HA user mapping, source changes,
   removal/unavailability, module toggle, options reload, Store reload, and
   multiple Config Entries. Reusing one HA entity in another Config Entry is
   allowed only after that entry's independent owner binding and subject consent;
   it grants no cross-household projection. No production entities or external
   network are used.
8. Browser acceptance in EN/RU/UK: reported/unknown wording, mobile layout,
   explicit consent review, frozen retry, focused-draft revocation, parent-only
   shared rows, and no raw location in text, attributes, screenshots, or errors.

Before implementation, product review must explicitly accept the self-consent
rule for children without linked HA accounts. Expanding that rule later requires
a distinct guardian-management provenance and revocation policy; it must not be
smuggled in as owner configuration authority.
