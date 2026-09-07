# Encrypted backup archive acceptance

Status: the archive create/decrypt/read slice passed the complete disposable
Home Assistant 2026.8.2 acceptance run. The real manager created a protected local
archive, rejected absent/wrong keys, and yielded exact Family Assistant Store
and media bytes that loaded through fresh application objects. Cleanup restored
the prior backup configuration and deleted only its generated archive via API.
This is not a full Home Assistant restore or legacy migration acceptance.

The lab now performs a real `hass.async_start()` after bootstrap: the backup
manager correctly waits for the started lifecycle before accepting work. The
reader consumes each decrypted tar member in order; enumerating all members
first would exhaust SecureTarFile's forward-only stream. A real streaming tar
regression and truncated-stream refusal cover that test-harness failure.

## Goal and boundary

The existing actual-HA smoke in `tests/ha_backup_smoke.py` proves that Family
Assistant freezes its Engine and media storage while Home Assistant's backup
callbacks run. It copies the Store and blob tree while frozen and loads those
copies through fresh `Store`, `Engine`, and `MediaStorage` objects. That is useful
coherency evidence, but it does not prove that Home Assistant placed those files
in an archive, protected the archive with the supplied password, or that the
archived bytes can be read back.

The smallest next slice will create one real Home Assistant Core/Container
backup in the existing disposable synthetic HA lab, then cryptographically open
and inspect its `homeassistant.tar.gz`. It will not invoke Home Assistant's
restore method, write `.HA_RESTORE`, call `homeassistant.restart`, start a second
container, contact a backup agent, or operate a real installation.

This is deliberately an **archive create/decrypt/read** acceptance, which is one
of the supported alternatives in the scope. Loading the archived Family
Assistant Store and media through fresh domain objects provides application-level
rehydration evidence, but is not described as a full Home Assistant restore.

No legacy importer currently exists in the public integration. The current
status explicitly leaves existing-home migration pending. This test must not
invent a legacy schema, read the private legacy project, or imply that encrypted
archive acceptance validates migration. A later migration gate needs a separate,
public, versioned legacy fixture and an implemented importer.

## Home Assistant 2026.8.2 contract used

The test uses the already configured real `BackupManager` returned by
`homeassistant.components.backup.async_get_manager(hass)` and its built-in local
agent `backup.local`.

The acceptance helper uses the manager's initiate form so it receives the exact
generated ID before waiting:

```python
created = await manager.async_initiate_backup(
    agent_ids=["backup.local"],
    include_addons=None,
    include_all_addons=False,
    include_database=False,
    include_folders=None,
    include_homeassistant=True,
    name="Family Assistant encrypted acceptance",
    password=synthetic_password,
    raise_task_error=True,
)
backup_id = created.backup_job_id
```

In HA Core 2026.8.2, `CoreBackupReaderWriter` generates one `backup_id`, returns
that same value as `NewBackup.backup_job_id`, and stores it in the archive's
`AgentBackup`. `BackupManager.async_create_backup` is itself only
`async_initiate_backup(..., raise_task_error=True)` followed by awaiting the
manager's finish task. The version-pinned smoke retains and boundedly awaits that
exact task so it learns the ID before failure cleanup without creating a second
job. Core calls all backup-platform pre callbacks, writes the HA config directory
below `data/` into `homeassistant.tar.gz`, and invokes post callbacks in
`finally`. The integration's existing callback assertions remain the authority
for freeze/release ordering.

There is an important local-agent condition: when `backup.local` is configured
with `protected: false`, `CoreBackupReaderWriter` deliberately replaces the
supplied password with `None`. Before creation, the smoke must capture the exact
current local-agent protection configuration, set only `backup.local.protected`
to `true` through the authenticated HA backup config API, and restore the exact
captured value in `finally`. It must not overwrite unrelated agents, schedules,
retention, names, passwords, or automatic-backup settings.

The password is a nonempty synthetic string created for this invocation. It stays
only in a local variable and the create/decrypt calls. It is never written to a
ConfigEntry, Family Assistant Store, fixture, command output, issue, diagnostic,
or document. The test must verify that it is absent from HA's persisted backup
configuration after both creation and rollback.

The generated path is resolved only through
`manager.local_backup_agents["backup.local"].get_backup_path(backup_id)`. The
test must verify that the resolved regular file is beneath the disposable HA
config backup directory before opening or deleting it. It must not guess a QNAP,
Supervisor, `/backup`, SMB, or production path.

## What counts as encrypted evidence

The outer file is a tar container with a readable `backup.json`; direct outer-tar
readability is expected and must not be treated as an encryption failure. The
metadata field `protected: true`, the manager's agent status, file extensions,
and non-plaintext-looking bytes are also insufficient on their own.

Acceptance requires all of the following:

1. `homeassistant.components.backup.util.read_backup(path)` reports the expected
   backup ID, `homeassistant_included=True`, `database_included=False`, and
   `protected=True`.
2. `validate_password(path, None)` and validation with a distinct wrong password
   return false. Neither attempt yields Store or media bytes.
3. `validate_password(path, synthetic_password)` returns true.
4. The outer archive is opened as an ordinary tar only to obtain the exact
   regular member `homeassistant.tar.gz`. That stream is opened with
   `securetar.SecureTarFile(fileobj=..., gzip=True,
   password=synthetic_password)` and the expected files are read fully.
5. Opening or reading that same inner stream with the wrong password raises the
   supported securetar password/read failure. The test should prefer HA's stable
   `validate_password` boolean for its public assertion and avoid binding to an
   undocumented cipher or exception message.

The test does not assert a particular cipher, KDF, salt layout, magic prefix, or
securetar implementation detail. HA 2026.8.2 selects securetar version 3 when it
creates the archive; cryptographic implementation details belong to that pinned
HA dependency and may evolve.

## Exact archived-data proof

Immediately before backup creation, collect only synthetic-lab evidence:

- the current Engine snapshot;
- exact bytes and SHA-256 of
  `.storage/family_assistant.<entry_id>` after persistence has settled;
- the complete regular-file relative-path, byte-count, and SHA-256 manifest under
  `family_assistant_data/<sha256(entry_id)>`;
- the existing expected attached-media records and their `blob_key`, size, MIME,
  revision, and content digest.

After creation and post-callback release, read from the encrypted inner tar by
exact canonical member names:

```text
data/.storage/family_assistant.<entry_id>
data/family_assistant_data/<entry_hash>/<blob_key>
```

Do not call `extractall`. Accept canonical directory entries beneath the exact
media prefix because normal HA archives contain them, but never include them in
the file manifest. For every selected non-directory member, require a regular
file, reject traversal, links, devices, duplicate names and file/directory path
collisions, read it fully, and compare its exact length and digest. Enumerate the
entire Family Assistant media prefix and require its regular-file manifest to
equal the pre-backup manifest, so a missing blob, extra temporary file, or
exclusion cannot be masked by checking only one attachment.

The archived Store bytes must equal the settled source Store bytes. Parse the HA
Store envelope and require its `data` to equal the frozen Engine snapshot. Then
write only those already decrypted Family Assistant Store/media bytes into a new
temporary HA config directory and reuse the existing `_restored_copy_reads`
pattern: `Store.async_load()` must return the same state, and `MediaStorage.get`
under the existing synthetic owner authorization must return every expected
attachment with the exact revision, length, and SHA-256.

The source paths may be used only to build the before-manifest. All after-values
must come from the encrypted archive stream or the isolated directory populated
from it. This prevents the common false positive of re-reading the live tree.

## Transaction and cleanup plan

Run this only inside the already isolated HA compatibility lab and only when the
manager is idle. Record:

- the exact backup config needed to restore the local-agent protection setting;
- the set of known local backup IDs and regular files before the test;
- Family Assistant Engine state, Store digest, media manifest, and backup gate;
- the generated backup ID once returned.

Use nested `try/finally` cleanup. On every success, assertion failure, timeout, or
cancellation:

1. Boundedly await the exact manager finish task. A timeout cancels and settles
   that asyncio task (and its awaited backup task) before cleanup; HA's own
   `finally` path still invokes post callbacks and returns the manager to idle.
2. If Family Assistant still owns a backup coordinator, use its supported post or
   generation-bound recovery path. Never pop the marker or clear tokens directly.
3. Delete only the recorded generated ID through
   `manager.async_delete_backup(backup_id, agent_ids=["backup.local"])` and require
   an empty error mapping.
4. Do not directly unlink a candidate. The initiated Core job exposes its exact
   ID before work starts, so cleanup uses only the local agent's supported delete
   operation after the manager task has settled.
5. Restore only the captured `backup.local.protected` setting through the HA API
   and verify unrelated backup config is byte-for-byte/structurally unchanged.
6. Verify the manager is idle, the generated ID/path is gone, no Family Assistant
   backup coordinator or recovery Repair remains, and ordinary Engine/media I/O
   works again.

Never delete all backups, use a glob, clear known-backup metadata directly, edit
`.storage/backup`, or assume an archive name. No automatic retention policy should
run against pre-existing lab backups; if the manager version cannot prevent that,
use a fresh isolated HA config instead of weakening cleanup assertions.

## Acceptance cases

- Real manager creation reaches a completed state and the Family Assistant backup
  platform is registered; pre/post runs exactly once and no recovery Repair is
  created.
- Local-agent protection is explicitly true for the create call. The returned
  archive and manager details both say protected, but the test continues to the
  cryptographic checks rather than trusting those flags.
- Empty/no password and a distinct wrong password cannot validate or reveal an
  inner member; the correct in-memory password validates and reads it.
- The exact archived Store equals the frozen Store and loads through a fresh
  `Store`/`Engine`; processed receipts, privacy state, tombstones, task reports,
  media links, revisions, and member epochs are preserved without replaying an
  action.
- The encrypted media prefix exactly matches the source prefix. Every attached
  JPEG/PNG/WebP expected by `ha_media_smoke` is readable through fresh
  `MediaStorage` with identical bytes and digest.
- Removing one expected member from a copied/corrupted candidate archive, using a
  wrong password, truncating ciphertext, or changing an expected digest makes the
  acceptance fail closed. Corruption tests operate only on a copy of the generated
  archive.
- A generated archive whose metadata says protected but whose inner HA tar opens
  without a password fails acceptance.
- Exclusion of either the Family Assistant Store or any private media blob fails;
  checking only `EXCLUDE_FROM_BACKUP` patterns is not sufficient evidence.
- Failure during create still runs HA post callbacks. If post release itself
  fails, the existing generation-bound Repair contract remains authoritative and
  the archive test does not force-clear it.
- Concurrent backup, restore, upload, or manager-busy state is rejected before
  mutation. The test never retries by inventing a second backup ID.
- Cleanup removes only the generated synthetic archive and known-backup entry,
  restores the exact prior local protection flag, and leaves pre-existing lab
  backups/config untouched.
- The synthetic password and decrypted Store/media content are absent from test
  output, logs asserted by the helper, diagnostics, artifacts, screenshots, and
  repository files.

## Explicitly unproven after this slice

This slice does not prove Supervisor/HAOS backup encryption, remote-agent upload,
cloud retention, encrypted archive portability across HA versions, database or
add-on restore, a real Core restart, full HA config restoration, disaster recovery
on another host, backup-key custody, or private legacy migration. It also cannot
paper over a Core/Supervisor encryption regression: cryptographic read/no-password
checks must fail the run even if HA reports the archive as protected.

The helper's hard timeout settles Home Assistant's asyncio backup tasks. Python
cannot forcibly stop a filesystem operation already executing inside Core's
executor thread; therefore a deliberately hung kernel/filesystem call is not a
recoverable in-process test condition. The disposable lab process boundary is
the final containment for that HA Core limitation, and successful acceptance
additionally requires both manager task slots to be empty before any archive is
read or the helper returns.

A later full-restore gate requires an independently disposable second HA process
or container whose entire config root can be destroyed and recreated. That gate
must receive only this synthetic archive/key, start with networking/providers and
device actions disabled, execute the versioned HA restore startup path, and verify
the restored integration through authenticated APIs. It needs separate explicit
lab orchestration approval and is not part of this first implementation.

## Primary references

- [HA Core 2026.8.2 BackupManager and CoreBackupReaderWriter](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/backup/manager.py#L983-L1252)
  define synchronous completion of `async_create_backup`, agent upload/cleanup,
  known-backup tracking, and manager state.
- [HA Core 2026.8.2 Core archive creation](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/backup/manager.py#L1606-L1841)
  defines local-agent protection behavior, pre/post callbacks, the outer securetar,
  inner `homeassistant.tar.gz`, config-root `data/` prefix, and exclusion filtering.
- [HA Core 2026.8.2 backup utilities](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/backup/util.py#L70-L195)
  define `read_backup`, `validate_password`, and streaming password validation.
- [HA Core 2026.8.2 backup tests](https://github.com/home-assistant/core/blob/2026.8.2/tests/components/backup/test_manager.py#L644-L658)
  demonstrate reading `homeassistant.tar.gz` through `SecureTarFile` with the
  supplied password.
- [HA backup-agent developer announcement](https://developers.home-assistant.io/blog/2025/02/17/backup-agents/)
  distinguishes backup-platform pre/post callbacks from backup agents.
