# Encrypted restore acceptance

The integration stores private data in HA's own configuration, outside its
updatable runtime. A successful archive read alone does not prove that an entire
configuration can boot after restoration.

`tools/run_restore_acceptance.py` builds the exact runtime ZIP and runs four
separate Python processes in an owned temporary configuration:

1. Prepare a fictional household through HA flows and supported domain commands,
   including an attached private PNG, disabled alarm and synthetic credentials.
2. Use the real HA backup manager to create a protected local backup, reject a
   wrong key without side effects, modify data after the snapshot, and request a
   correct restore through the real manager/default Core restart service.
3. Damage a synthetic blob after HA has stopped, then invoke HA's native startup
   restore implementation. Verify exact archived Store and configuration bytes,
   removal of the post-backup sentinel and one-time instruction consumption.
4. Bootstrap a fresh Core from restored YAML; verify Config Entry/Options, original
   owner and pre-backup token over HTTP, complete domain state, blob integrity and
   private HTTP authorization, frontend delivery, inactive transports/alarms, and
   exact operation replay without duplicate effects.

The key never enters command-line arguments, output or the fixture contract. HA
itself puts it in its temporary restart instruction; native restoration consumes
that instruction. All other synthetic state, tokens and archives are removed with
the exact owned temporary directory, on success or a settled child failure.
The runner refuses arbitrary config paths and symlinks. Its error output is fixed
codes, not child logs. No production backups, mounts, devices or accounts are used.

Run only in a disposable network-disabled HA 2026.8.2 container, with this public
repository mounted read-only at `/work`:

```sh
python /work/tools/run_restore_acceptance.py --source /work --timeout-seconds 300
```

The `encrypted-restore` CI job supplies that isolation. Local runner unit tests
mock child processes to test ownership, ordering, timeout settlement and cleanup;
they do **not** constitute restore acceptance. The actual four-phase container
test passed on 2026-09-07 for alpha.6's `6550342426...` runtime artifact.

The pinned [Core backup manager](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/components/backup/manager.py)
and [startup restore implementation](https://github.com/home-assistant/core/blob/2026.8.2/homeassistant/backup_restore.py)
are the exercised implementations, not replacements. This verifies Core/Container
configuration restoration. It does not verify HAOS/Supervisor add-ons, database
history, the user's private installation or legacy migration/cutover.
