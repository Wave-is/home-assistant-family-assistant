# Guided onboarding post-create handoff

Status: shared `config_flow.py` wiring and the post-create acceptance helper
passed on actual Home Assistant 2026.8.2. Core returned a live Options handoff
for the exact new entry; deduplication, manual-flow collision, strict sentinel
and no Options/Engine/modification-time changes were verified there. Races and
setup/authority failure injection are additionally covered by isolated unit
contracts, not all by the actual-HA helper. Manual Configure remains the
supported fallback if automatic handoff cannot safely finish.

## Core lifecycle used

The supported extension point is `ConfigFlow.async_on_create_entry(result)`.
In Core 2026.8.2, the config-entry manager first constructs the new entry,
awaits `async_add(entry)`, assigns that exact object to `result["result"]`, and
only then awaits `async_on_create_entry`. Core validates a returned
`next_flow` against the appropriate live flow manager. See the tagged Core
[finish-flow implementation](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/config_entries.py#L1681-L1708)
and its
[Options-flow test](https://github.com/home-assistant/core/blob/2026.8.2/tests/test_config_entries.py#L2152-L2261).

`async_add` itself awaits setup before returning. Therefore the hook does not
need, and must not add, a sleep loop, timer, state listener or progress task to
wait for this newly created entry. It performs one bounded readiness check
after Core's awaited setup. This is important because Core explicitly says
`async_wait_component` cannot wait for entries created after Home Assistant
has started. See
[`async_add`](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/config_entries.py#L2063-L2074)
and
[`async_wait_component`](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/config_entries.py#L2683-L2693).

If setup ended in `SETUP_RETRY`, `SETUP_ERROR`, another non-loaded state, or a
runtime identity mismatch, automatic handoff is simply omitted. The already
created entry and Core's normal retry/Repair behavior remain intact, and the
owner can open Configure after the entry loads.

## Minimal integration hook

Import `async_post_create_handoff` and `is_guided_handoff` from
`onboarding_handoff.py`. Add an `async_on_create_entry` override to
`FamilyConfigFlow`; do not pass an
Options flow through `async_create_entry(next_flow=...)`. Core permits Options
and subentry handoffs from `async_on_create_entry`, while ordinary
`ConfigFlow.async_create_entry` accepts only another config flow. The relevant
contract is in
[`ConfigFlow.async_on_create_entry`](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/config_entries.py#L3118-L3158).

The hook has the following exact sequence:

1. Preserve the original `ConfigFlowResult`. Only run for a user-source flow
   with a non-empty string `context["user_id"]` and a real
   `result["result"]` `ConfigEntry`.
2. Require
   `hass.config_entries.async_get_entry(entry.entry_id) is entry`, the entry's
   domain is Family Assistant, `entry.state is ConfigEntryState.LOADED`, and
   `entry.runtime_data is hass.data[DOMAIN]["entries"][entry.entry_id]`.
   Recheck the entry after awaiting the HA user lookup, require that user to
   remain active and an administrator, then resolve the same HA user through
   that runtime and require the current active household role to be `owner`.
   Pin the runtime object, actor ID and strict member revision for all later
   checks. HA administrator status alone is not enough.
3. Initialize an Options flow with the exact new `entry.entry_id`, standard
   context `{"source": SOURCE_USER, "user_id": original_user_id}`, and the
   strict in-memory sentinel
   `{"guided_onboarding_handoff": True}`. Do not look up an entry by title,
   domain order, the first entry, or a mutable household name.
4. `FamilyOptionsFlow.async_step_init` calls `is_guided_handoff(user_input)`;
   only exact equality with that one-key built-in dictionary calls
   `async_step_guided_onboarding`. `None` and every
   other input retain the existing normal Options menu. The sentinel is flow
   initialization data only; it is never copied into entry data, Options,
   Engine state, diagnostics or a FlowResult placeholder.
5. Require the initialized result to remain in progress at step
   `guided_onboarding`, then recheck the exact entry, runtime and current owner
   after all awaits. The runtime, actor and actor revision must equal the pinned
   scope; a same-ID membership replacement is not permission to rebase the
   reviewed handoff. Only then add
   `(FlowType.OPTIONS_FLOW, guided["flow_id"])` to `result["next_flow"]`.

The hook must not call setup or reload itself. It must not write an option,
Engine command, Store value, completion flag or onboarding cursor. Core's
Options manager updates Options only for a `CREATE_ENTRY` result; a menu does
not finish the flow and the existing `guided_finish` `ABORT` does not update
Options. See
[`OptionsFlowManager.async_finish_flow`](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/config_entries.py#L3628-L3654).

The intended shared wiring is intentionally small:

```python
async def async_on_create_entry(self, result):
    return await async_post_create_handoff(self.hass, result, self.context)


async def async_step_init(self, user_input=None):
    if is_guided_handoff(user_input):
        return await self.async_step_guided_onboarding()
    return self.async_show_menu(...)  # the existing menu, unchanged
```

The actual-HA runner should call
`verify_onboarding_handoff(hass, result, user)` immediately after the modules
step returns the create result and before opening any additional Options flow.

## Optional-failure and duplicate rules

The guide is subordinate to successful household creation. Expected handoff
failures—including a no-longer-current user, backup gate, translation failure,
an unloaded/replaced entry, an Options-flow collision or an unavailable flow
manager—return the original create result without `next_flow`. Log at most a
fixed message that contains no exception text, entry title, user/member ID,
provider value or secret. Do not catch `asyncio.CancelledError` as an ordinary
failure: clean up a flow created by this attempt and re-raise cancellation.
The entry has already been added, so cancellation cannot justify removing it.

Core calls `async_on_create_entry` only for a newly created entry, not for the
existing-entry replacement branch. Still make the hook retry-safe because test
harnesses, future Core behavior and cancellation can expose partial attempts:

- Serialize attempts on a private process-local `asyncio.Lock` keyed by the
  exact entry ID in the current HA instance. Weak values release the lock and
  key after the final active/waiting attempt ends. The lock is not persisted
  or shared across households, and remains shared across runtime replacement
  while an older attempt is active. A task cancelled while waiting
  has created no flow; a task cancelled during initialization cleans its own
  flow before releasing the lock. This prevents one concurrent invocation's
  before/after scan from claiming another invocation's flow, including a
  successor operating on a replacement runtime with the same entry ID.
- Before initialization, query Options flows for the exact `entry_id`,
  including uninitialized flows. If an unrelated Options flow already exists,
  skip automatic handoff rather than opening a competing transaction.
- Identify this hook's flows by exact handler, original `user_id`, user source
  and exact sentinel initialization data. Core's public
  `async_progress_by_handler` and `async_progress_by_init_data_type` callbacks
  are sufficient; do not inspect private flow-manager maps.
- If exactly one matching handoff flow is already live, reuse its validated
  flow ID. Never attach another user's or an unmarked manual Options flow.
- Snapshot matching flow IDs before `async_init`. On exception or cancellation,
  abort only matching IDs introduced by this invocation. Core flow removal also
  cancels a registered progress task, although this design starts none; see
  [data-entry-flow removal](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/data_entry_flow.py#L393-L430).

If initialization returns an abort or a completed result, there is no live
Options flow to reference, so return the original create result. Never set a
`next_flow` speculatively: Core validates the referenced ID and an invalid ID
would turn an optional-guide problem into an error response after the entry was
already created.

Closing the browser merely abandons the in-memory Options flow. No durable
cursor exists. If the entry is unloaded, removed, restored or the owner is
demoted while the menu is open, the existing `_entry_current`, runtime identity
and current-role checks fail closed on the next step. The landing page contains
only bounded readiness counts, never credentials or household identifiers.

## Actual Home Assistant 2026.8.2 acceptance

The list below is the full acceptance design. The actual helper currently
executes the ordinary new-entry handoff, duplicate reuse, manual-flow collision,
strict sentinel and read-only finish. Same-title identity selection, concurrent
cancellation, setup failures and mid-flight revocation are unit-tested; they
must not be represented as actual-Core fault-injection coverage yet.

Add one actual-HA helper that completes the real `user` and `modules` steps as
an authenticated admin and retains the exact returned `ConfigEntry` object.
The primary path must establish all of the following:

1. The create result is successful, the exact entry is `LOADED`, and its
   `next_flow` is `FlowType.OPTIONS_FLOW` whose live handler is exactly that
   entry ID and whose step is `guided_onboarding` for the same HA user.
2. With two deliberately same-titled Family Assistant entries, the handoff
   points to the newly returned entry, and readiness placeholders contain only
   its synthetic bounded counts.
3. Snapshot entry data/options, modification time, runtime identity, Engine
   state/audit/outbox and update-listener/reload calls after creation. Opening
   the landing menu and finishing it with `guided_finished` leave all snapshots
   unchanged.
4. A manual Options initialization with `data=None` still opens `init`; arbitrary
   dictionaries do not trigger the guide.
5. A second invocation of the handoff helper reuses the one marked flow and
   does not increase the in-progress count. Two simultaneous helper calls
   serialize and receive the same single flow. Cancelling the first while the
   second waits removes only the first flow; the successor may create its own.
   A concurrent unmarked Options flow causes the automatic handoff to be
   skipped, not attached or aborted.
6. Force setup to finish in `SETUP_RETRY` and separately make Options
   initialization/translation fail. In both cases the exact entry remains
   registered, no `next_flow` is returned, no marked orphan flow remains, and
   the Config Flow still returns its successful create result.
7. Gate Options initialization, then demote/remove the original owner or unload
   the exact entry, replace the runtime, or increment the owner's membership
   revision before releasing it. The final pinned-scope recheck removes only
   the new marked flow and returns the unchanged create result.
8. Cancel while Options initialization is gated. Cancellation propagates, the
   exact created entry is not deleted or modified, and the flow introduced by
   the cancelled attempt is gone.
9. Put canaries in every secret-bearing option and provider error object. None
   appears in the create result, guide FlowResult, captured fixed log message or
   flow context/init sentinel.

These assertions test the real ConfigFlowManager and OptionsFlowManager. A
mock that directly calls `async_step_guided_onboarding` does not establish the
post-create `next_flow`, exact-entry setup ordering, cleanup or duplicate-flow
contract.
