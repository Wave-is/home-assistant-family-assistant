# Task-report photo retention

Attached task-report photos are retained with the task and its parent-visible
report history. Completing, cancelling, archiving, reassigning, or retiring a
source object does not silently delete them.

## Explicit purge contract

Only the current active household owner can purge one reviewed attachment. The
command is `tasks.report_media_purge` with the exact payload:

```text
id, revision, report_generation, media_id, media_revision, reason, confirmed=true
```

The task, report generation, attachment reference, and media revision must all
still be exact. The Tasks module must be enabled. Current and historical report
slots are supported, including archived tasks. A stale review never selects a
newer photo by implication.

The Engine transaction removes the attachment reference, leaves a content-free
`report_media_purged_at` marker in that same report slot, advances the task, and
moves the attached media record to `deleting`. It does not change task status,
report text, review notes, checklist, deadlines, penalties, or notifications.
The reason confirms deliberate intent and is covered by operation
idempotency; it is not copied into the retained report or media tombstone.

After that Store commit the photo is no longer readable. The media collector
unlinks the opaque entry-private blob and then persists a minimal `deleted`
tombstone. A crash or Store/unlink failure resumes from the last persisted
phase. A missing blob is an idempotent unlink success. Attached media is never
selected by the ordinary expiry collector without this explicit transaction.

## Bounded tombstones and capacity

The household accepts at most 10,000 non-deleted media records and 1,000 recent
deleted tombstones. Either relevant ceiling applies backpressure rather than
discarding retained photos. Each collector pass forgets at most 100 tombstones
whose persisted `deleted_at` is at least 24 hours old, ordered by deletion time
and opaque ID. Reaping contains no filesystem operation because the blob was
already removed before the tombstone was created.

The processed-operation journal remains authoritative and is not pruned by this
slice. Therefore replaying the original `media.reserve` operation after its
tombstone was reaped reaches the saved operation first, fails current media
authorization, and cannot create a replacement record or blob. A changed body
with the old operation ID remains an idempotency conflict. Defining bounded
retention for the global processed journal is separate future work; it must not
be replaced with another unbounded deleted-ID set.

`media.health_stats(state, now)` exposes counts and capacity state only:
non-deleted records, tombstones, reapable tombstones, pending/deleting counts,
verified/reserved byte budget, and `ok|near_limit|blocked`. It exposes no media
IDs, blob keys, hashes, paths, names, reasons, or report content. Storage damage
and scan health remain adapter-owned signals.

`blocked` means a new upload cannot be reserved for the household: a record or
tombstone ceiling, 20 pending uploads, or insufficient room for another 10 MiB
reservation within the 250 MiB byte budget. Deleting blobs keep occupying budget
until cleanup finishes. An individual member's five-pending limit does not mark
the entire household blocked; other eligible members can still upload. No quota
is increased and no retained content is removed to clear this indication.

The Tasks card exposes a separate owner-only retained-photo removal review, for
current and historical reports. A reason and explicit irreversible-removal checkbox
are required; submitting a normal task report never triggers purge. The reviewed
task revision, report generation, media revision and operation ID remain frozen for
an exact retry after a lost response. A changed uncommitted source or authority
discards the review. Counts-only capacity is included in safe diagnostics.

Removal affects the live private media store. Earlier Home Assistant backups may
still contain the photo; no automatic backup deletion or secure-storage erasure is
claimed.
