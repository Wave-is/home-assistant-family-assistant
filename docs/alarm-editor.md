# Alarm schedule editor

The standalone alarm editor completes the existing `alarms.save` UI without
changing alarm execution, challenges, siren configuration, or test behavior.
It supports creation and strict revision-bound full editing of every schedule
field already accepted by `domain/alarms.py`.

## Contract

`frontend/alarm-editor.js` exports:

- `openAlarmEditor(card, alarm = null)`, which snapshots a create or edit draft;
- `renderAlarmEditor(card, body)`, which renders the active edit/review step and
  returns whether it rendered one;
- `reconcileAlarmEditorRefresh(card, previousData)`, which clears stale private
  draft state and requests a rerender;
- `ALARM_EDITOR_COPY`, with matching English, Russian, and Ukrainian keys.

The create request is exactly:

```text
alarms.save {
  member, name, time, days, timezone, enabled, exceptions,
  second_min, second_max, profile, recheck_grace, penalty
}
```

An edit adds only `id` and the currently displayed strict `revision`. The editor
validates the same visible bounds as the domain: a real `HH:MM`, an IANA time
zone, one or more unique weekdays 0–6, real ISO exception dates, second-check
limits 1–25 with minimum not greater than maximum, grace 0–300, integer penalty
-10–0, and `gentle|strict`. Names may be empty and are limited to 80 characters.

The review names the affected member and shows the complete schedule. Its
confirmation does not test a siren or claim that a physical alarm sounded. The
strict profile text refers only to a separately configured siren; this editor
does not choose an entity, volume, tone, or service.

Before submission, Back returns to the populated form and Cancel discards the
local review. Once a transport result is uncertain, both controls disappear:
only the exact frozen retry remains, so the UI cannot casually discard an
operation that the server may already have committed. Opening the editor and
entering review move focus to the first relevant control; validation uses a live
alert.

## Concurrency and privacy

Opening snapshots the current entry/generation, actor identity/role/revision,
alarms module, all eligible member identities/revisions, and all current alarm
IDs/revisions. Any change before review or first submission invalidates the
draft. The backend remains authoritative for role, active-member, overlap,
time-zone, and strict schedule revision checks.

On submission, the payload and operation ID are recursively frozen. A failed
transport retains them. If a refresh shows the exact committed schedule at the
next revision, retry remains available and sends the identical request so the
Engine can return its durable receipt. It never rebases to a newer revision.
Actor, role, member, module, entry, or card-generation revocation still clears
the pending UI. Detached controls cannot submit.

The current backend command does not accept a target `member_revision` field.
The editor therefore pins the displayed member epoch client-side, while the
domain rechecks that the target is still active when it executes. Adding an
atomic target-member epoch to `alarms.save` would require a separately versioned
backend contract; the editor must not invent that field.

All user values are written with `textContent` or form values. No schedule data
is inserted as HTML.

## FamilyCard integration

The shared card can integrate this module narrowly by resetting
`_alarmEditorDraft` on configuration/identity disposal, calling reconciliation
after a successful view refresh, routing the existing Add control and a new
per-schedule Edit control through `openAlarmEditor`, and giving
`renderAlarmEditor` precedence over the legacy creation form while a draft is
active. Existing enable/disable and explicitly confirmed `alarms.test` controls
remain separate and unchanged.

## Verification boundary

Node tests cover the full payload, locales, invalid values, immutable retry,
committed-response loss, stale authority/source/member pins, detached controls,
and HTML canaries. The browser fixture uses the real `FamilyCard.command` path
with a faithful synthetic projection/execute boundary. Browser scenarios do not
invoke `alarms.test`, Home Assistant services, or physical devices.
