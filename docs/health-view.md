# Localized System Health card

This slice extracts the parent-only Health body into
`frontend/health-view.js`. It reads only the existing `health` mapping and the
existing parent projection `delivery_issues`; it does not request diagnostics,
provider data, notification content, recipient details, or new server fields.

The renderer exports `renderHealth(card, body)`. Runtime module keys and known
health codes receive fixed English, Russian, and Ukrainian labels. Unknown
module, status, and event keys use generic localized wording rather than
displaying internal strings. Counts are derived only from the projected rows;
the view bounds component detail to 50 and delivery detail to the server's
existing 100-row projection.

`countHealthAttention(health)` counts attention states for the overview without
treating `connected` or `network_connected` as problems. Healthy component rows
remain visible in the detailed Health card.

Only a current active owner or parent can see detail or controls. Other roles
receive one generic parent-only message, even if malformed client state contains
private rows. Delivery IDs, recipient IDs, operation keys, and raw unknown
values are never printed.

## Existing delivery operations

The view preserves the implemented notification review contract:

- uncertain and failed events may be retried with
  `notifications.retry {id, reason, confirmed: true}` after explicit duplicate
  consent;
- uncertain and failed events may be acknowledged with
  `notifications.resolve {id, reason}` without claiming delivery;
- an event awaiting a channel only shows the private-chat setup hint.

Commands still go through the shared card command path, so an uncertain response
can reuse the same operation ID for the same payload. Before opening or
submitting a review, the renderer rechecks the current household, actor role and
revision, and the exact projected event state. A detached or stale form cannot
send a command. Server authorization remains authoritative.

## Wiring

The shared card imports `renderHealth` and calls it from the Health dispatch;
the old renderer is removed. `reconcileHealthRefresh` forces a privacy refresh
when authority or the reviewed delivery projection changes, including while a
reason field is focused. `countHealthAttention` is also used by Today so healthy
connected components are not counted as failures. The helper does not register
a card resource or alter the Engine projection.

This is synthetic frontend acceptance, not evidence of a production migration,
live Telegram delivery, or a released HACS package.
