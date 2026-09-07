# Packaged application-upgrade acceptance

This gate checks that a reviewed baseline Family Assistant artifact and a
candidate artifact can run, in separate Home Assistant processes, against the
same synthetic HA configuration. It is deliberately narrower than a Home
Assistant backup restore or a migration of a real household.

The baseline must be identified by its exact source commit. Before the first
release this may be an earlier reviewed development artifact, not a previously
shipped version. The result reports both runtime ZIP SHA-256 hashes; it does not
claim that either version was published.

CI currently pins baseline commit
`7930f7e8825de158a2d3facc590f44e40d78a4b5` (`0.1.0-alpha.3`), a published
test prerelease. The `application-upgrade` job runs the candidate against
that exact baseline in the network-disabled HA 2026.8.2 image. Advancing the
baseline is a reviewed release decision, not an automatic replacement with the
latest branch.

## Boundary

`tests/ha_upgrade_acceptance.py` has two phases. `prepare` must run with an
extracted, reviewed baseline artifact installed at
`<config>/custom_components/family_assistant`. It creates one household through
the real config flow, creates a child through the real Options flow, reviews a
synthetic siren binding through the real alarm-device Options flow, and writes a
task, a seven-point court entry and a disabled alarm schedule through the real
Engine and HA `Store` adapter. It also stores disabled Telegram-bot and model
provider placeholders in Config Entry Options through Core's supported
`async_update_entry` API. Disabled placeholders never inspect a URL, start a
poller or call a device.

After Home Assistant stops, `prepare` writes a new sidecar contract containing
only synthetic data: the baseline version, exact Config Entry and user IDs,
Config Entry data and Options, domain record IDs, replay inputs, and selected
durable records. It never copies a database, media directory, token, real entity
ID or production configuration.

`verify` must run in a second process after the candidate artifact replaces the
baseline integration directory while HA is stopped. It requires a different,
explicit candidate version. It boots the same config directory and verifies:

- exactly one Family Assistant Config Entry retains the captured `entry_id`,
  data, Options and active admin owner;
- the candidate reaches `LOADED` and its runtime reads the retained integration
  Store;
- the exact child, task/checklist, court/points record and disabled alarm
  schedule retain their IDs and values;
- a fresh HA `Store.async_load()` agrees with the runtime snapshot;
- the same synthetic siren unique ID resolves to the retained entity ID and is
  never called;
- disabled bot/model placeholders survive while Telegram, assistant, network
  and recipe clients remain inactive;
- the three baseline operation IDs return their persisted receipts exactly and
  do not mutate state.

The alarm is disabled, and the synthetic siren asserts that configuration did
not actuate it. The test has no provider listener, Telegram delivery, physical
device, external URL call or automatic points mutation.

## Required orchestration

`tools/run_upgrade_acceptance.py` is the outer orchestrator. Run it inside the
pinned Home Assistant container, with container networking disabled and the
baseline and candidate repository exports mounted read-only at two explicit
absolute paths:

```text
python /candidate/tools/run_upgrade_acceptance.py \
  --baseline /baseline --candidate /candidate --timeout-seconds 300
```

The orchestrator rejects relative or reparse-point repository roots, validates
each runtime with the same in-memory release builder, and refuses equal manifest
versions. It creates a marker-owned temporary directory and installs only the
validated `custom_components/family_assistant/` archive bytes. It never imports
the integration in its parent process and never reads or edits `.storage`
itself.

The baseline `prepare` helper runs as a bounded child process. Only after its
normal zero exit does the orchestrator remove the integration directory inside
its verified synthetic config, install the candidate bytes, and run `verify` in
a second child process against the same config and contract. A timeout or
non-zero exit is a fixed failure and cannot start the next phase. Child output
is discarded rather than buffered or copied into error messages.

The temporary config and contract remain together through both phases. Final
cleanup is limited to the exact system-temporary directory carrying the
orchestrator's random ownership marker; source mounts are never written or
removed. The inner helper opens the contract with exclusive creation, never
searches entries by title, and never deletes HA data. The surrounding release
runner remains responsible for supplying exact reviewed exports, a read-only
mount for each, the pinned HA Core image, `--network none`, and an overall job
timeout.

The lifecycle follows Home Assistant Core 2026.8.2's supported config-entry and
storage APIs: Core loads Config Entries from `core.config_entries`,
`async_update_entry` schedules persistence and notifies update listeners, and
HA shutdown flushes managed Stores. The second fresh process—not an in-process
reload—is the evidence that those writes were durable. See the pinned Core
sources for [Config Entries](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/config_entries.py),
[bootstrap](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/bootstrap.py),
and [`Store`](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/helpers/storage.py).

## What this does not prove

This gate does not restore a full HA backup, exercise an older HA Core image,
certify a production schema or secret migration, contact configured providers,
ring a siren, preserve recorder history, validate private media bytes, or modify
a live installation. Schema-changing releases need an additional fixture made
by the relevant actually shipped version and explicit assertions for the
documented migration; widening this helper's equality checks is not a substitute
for that review.
