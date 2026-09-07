# Backup freeze recovery

Status: implemented recovery contract. The backup platform quiesces Store and
media during a normal backup and exposes a generation-bound Home Assistant
Repair when an exceptional lease release cannot finish.

## Current boundary and failure mode

`backup.async_pre_backup` installs one process-local coordinator before waiting
for entry setup/unload, snapshots loaded runtimes deterministically, pauses media,
and then freezes each Engine. `async_post_backup` releases those exact leases in
reverse order. A failed release deliberately leaves its acquired flag and the
global coordinator in `hass.data`; it never clears an unknown token or starts a
replacement generation.

This is safer than forced thaw, but it can leave the affected Engine or media
store unavailable, block another backup and hold entry lifecycle work waiting on
`coordinator.released`. Calling `async_post_backup` again is already an exact
in-process retry, but Home Assistant has no user-facing way to do that. The
current unwind is also not time-bounded. A cooperative release which never
returns can therefore hold the callback and coordinator lock indefinitely.

Successfully released leases are marked individually and are not called again.
If another lease fails, those runtimes may already be writable after the Core
post-backup callback. That is not an active-backup thaw: Core invokes platform
post callbacks after its snapshot work. Recovery must nevertheless keep the
coordinator marker until every remaining lease has released, so entry lifecycle
and a new backup generation cannot cross the partial state.

No recovery operation may pop `hass.data[DOMAIN]["backup"]`, replace Engine
state, edit `.storage`, stop media, unload an entry, mint a new lease, or accept a
client-selected runtime/token. Process restart creates new runtime objects with
no old process-local lease; the integration should then remove or leave inactive
any stale non-persistent issue, not pretend that it replayed the old tokens.

## Coordinator state

Extend the process-local coordinator, without persisting it, with an explicit
phase:

```text
acquiring -> frozen -> releasing -> released
                    \-> recovery_required -> releasing ...
acquiring -> releasing -> recovery_required|released   # failed pre cleanup
```

Only `recovery_required` is eligible for a user retry. `frozen` means the Home
Assistant backup callback has not requested post-processing and must never be
released by a Repair. `releasing` prevents two post/recovery attempts from
operating concurrently. The existing coordinator lock serializes phase changes
and per-lease flags.

Keep the existing process-local `generation` object as the authoritative identity.
A repair flow captures both the coordinator object and its generation when the
flow is created. On display, confirmation, and after every await it must require:

```text
data["backup"] is captured_coordinator
captured_coordinator.generation is captured_generation
captured_coordinator.phase == "recovery_required"
```

Mismatch is a code-only `stale_recovery` abort with zero release calls. The
generation is never supplied by the browser and is never stored in Engine state,
ConfigEntry options, audit, diagnostics, logs, issue data, or translation
placeholders.

## Repairs surface and authority

On an unwind failure, create one domain-scoped, fixable Repairs issue with a
stable ID such as `backup_recovery`, `IssueSeverity.ERROR`, and
`is_persistent=False`. ERROR is appropriate because integration I/O is currently
broken; Home Assistant reserves CRITICAL for a true panic. The issue and its
translations say only that a backup freeze could not be released and that retry
will release the existing generation. They contain no entry ID, household name,
member, path, filename, token, exception text, or lease-specific data.

The issue must be created only after an unwind attempt has finished and the phase
has become `recovery_required`. Creating it is best-effort visibility and must
not clear the coordinator if issue registration itself fails. Delete it only
after all leases are released and the coordinator is removed. Ignoring an issue
does not alter the safety gate.

Implement the confirmation as the integration's `repairs.py` platform. Home
Assistant 2026.8.2 protects both creation and continuation of Repairs flows with
`require_admin(permission=POLICY_EDIT)`. The flow still performs the process-local
generation checks because administrator status is not concurrency authority.
Do not add an ordinary WebSocket command, service, card button, or URL for this
operation.

A current Home Assistant administrator is sufficient. Requiring every household
owner would not add data authorization: retry reads no household projection and
performs no domain mutation; it only finishes leases created by the HA-wide backup
platform. Such a rule would make recovery impossible when an owner is inactive,
unlinked, or belongs to another loaded household. Conversely, HA administrator
status must not grant any family command or media read as a side effect.

Home Assistant's issue list and issue-data WebSocket paths are not the repair
authorization boundary, so issue data must be treated as broadly observable.
The admin check is on the Repairs flow HTTP endpoints. This is another reason not
to put a recovery nonce or household identifier in the issue.

## Retry and failure semantics

The confirmed Repair calls one internal helper equivalent to the existing unwind:

1. Acquire the captured coordinator lock and recheck identity, generation and
   `recovery_required`.
2. Set `releasing` and attempt only flags still marked acquired, in reverse
   runtime order and Engine-before-media order.
3. A successful exact release clears only that flag. Engine and MediaStorage
   release methods remain idempotent for their own token, so an ambiguous
   cancellation can be retried without clearing a newer lease.
4. Continue trying later leases after an ordinary failure; return only fixed
   status/codes and retain all failed flags.
5. If any flag remains, restore `recovery_required`, keep the coordinator and
   Repair, and finish the flow with `backup_unavailable` so another explicit
   retry is possible.
6. Only when no flag remains: clear leases, transition to `released`, remove the
   coordinator only if it is still current, set `released`, delete the Repair,
   and complete the flow.

Apply a bounded timeout to each owned release and an overall 60-second recovery
attempt. The concrete Engine and MediaStorage release methods must stay
cancellation-safe: cancellation before their state change leaves the token
active; after their state change, repeating the same token is harmless. A timeout
must be allowed to settle/cancel its owned coroutine before another attempt; it
must not detach an unknown background release and then retry concurrently. Python
cannot impose a real bound on arbitrary cancellation-hostile code, so this claim
is limited to these owned release implementations and must be tested as such.

External cancellation is propagated only after the owned release attempt has
settled. It never removes the marker merely to satisfy cancellation. The Repair
shows a fixed error and remains actionable. Logs and diagnostics may record only
phase plus aggregate remaining Engine/media lease counts and the fixed
`backup_unavailable` code; caught exception strings and tracebacks may contain
private filesystem details and must not be interpolated.

Core gathers all platform pre and post callbacks and turns any returned exception
into a backup-manager failure. A pre-cleanup failure therefore becomes recoverable
only after this platform's pre callback is ready to return its fixed error; a
post-cleanup failure is recoverable only after Core has invoked post processing.
The Repair must never infer Core completion from elapsed time or Backup Manager UI
state.

## Acceptance cases

- Normal pre/post creates no Repair and preserves the existing deterministic
  pause/freeze and reverse release ordering.
- Engine or media release raises: every other release is attempted, successful
  flags stay cleared, failed flags remain, coordinator and lifecycle gate remain,
  and one content-free ERROR Repair appears.
- A release hangs cooperatively: the attempt terminates within the configured
  bound, no detached release remains, the gate stays closed, and retry is offered.
- Failure while unwinding a partial pre acquisition follows the same recovery
  path and Core receives only `backup_unavailable`; no snapshot is claimed.
- A Repair opened for generation A becomes stale after A is recovered. Submitting
  it while generation B is acquiring/frozen/recovering invokes no B release and
  aborts `stale_recovery`.
- Two admin confirmations race: one owns the coordinator lock; the other either
  retries remaining flags after a failure or observes the resolved/stale
  generation. No release runs concurrently or twice against a newer token.
- A Repair confirmation during `acquiring`, `frozen`, or an ordinary active HA
  backup cannot thaw any lease, even for an administrator.
- A non-admin can observe only the generic issue permitted by Core, cannot start
  or continue its fix flow, and learns no generation, entry, household, member,
  path, or failure component.
- A current HA admin not linked to any family may retry release but gains no
  Engine view, command, media bytes, options change, or audit entry.
- Failed retry leaves affected HTTP/domain gates unchanged. Successful retry sets
  `coordinator.released`, lets waiting unload/setup continue normally, removes the
  Repair, and permits a later fresh backup generation.
- Cancellation before, during and after each release boundary preserves the exact
  acquired flags; a same-generation retry succeeds, while stale and wrong tokens
  never clear a lease.
- Process restart has no old in-memory tokens or active coordinator. Startup does
  not fabricate a release, mutate Store/media, or surface an actionable stale
  Repair.
- Repairs, safe diagnostics, logs, audit, model context, Telegram and family views
  contain no private recovery data. Counts-only diagnostics do not become a
  recovery command.

Do not unit-test a made-up public command before implementation. The implementation
slice should extend the existing backup-platform tests with real Engine and
MediaStorage leases, then add an actual-HA test using the registered issue and the
real admin-protected Repairs flow. It must not create a real backup archive.

## Implementation acceptance checkpoint

The generation-bound recovery path is implemented with per-lease ten-second
limits inside a sixty-second unwind budget. Failed engine/media release keeps
only the exact outstanding lease flags; later leases are still attempted.
Internal cancellation and repeated caller cancellation do not silently clear
ownership. A content-free, nonpersistent Repair is available only after a failed
unwind; it cannot release an active backup or a different generation.

Opening a Repair is not confirmation: HA passes initialization metadata, which
the flow explicitly ignores before displaying its confirmation form. The first
actual-HA run caught this distinction; a regression now verifies zero release
calls while opening dialogs or making non-admin requests. Two failed admin
confirmations retain the same gate; a later success releases only the remaining
lease, and a stale second dialog aborts. EN/RU/UK fix-flow strings are present.

Root acceptance of the exact staged export passed the complete actual HA suite,
2092 Python tests (three host skips, 23 subtests), Ruff/format, locale parity and
public-tree privacy checks. This is recovery-after-release-failure evidence, not
encrypted archive or full-restore acceptance.

## Primary Home Assistant references

- [Repairs developer documentation](https://developers.home-assistant.io/docs/core/platform/repairs/)
  defines issue creation, severity, fix flows, persistence and deletion.
- [Repair-issue quality rule](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/repair-issues/)
  requires issues to be actionable rather than informational.
- [Home Assistant 2026.8.2 Repairs WebSocket/HTTP source](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/repairs/websocket_api.py#L101-L150)
  shows that fix-flow endpoints require administrator edit permission, while
  issue listing/data are separate read paths.
- [Home Assistant 2026.8.2 issue registry source](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/helpers/issue_registry.py#L318-L397)
  defines `async_create_issue` and `async_delete_issue`, including non-persistent
  issue behavior.
- [Home Assistant 2026.8.2 backup manager source](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/backup/manager.py#L1654-L1778)
  shows pre before archive generation, post in `finally` after generation or its
  failure, plus callback error propagation.
