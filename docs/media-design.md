# Shared private media design

Status: image-only task-report and maintenance-fault backend/cards and bounded file recovery implemented.
Full backup/restore acceptance, retained-content policy, maintenance documents and
School image import are not yet release-ready. The sections below distinguish
the implemented first slice from the remaining shared-media design.

## Scope and existing boundaries

The product vision calls for task photo reports, maintenance fault photos and
documents, and a reviewed School timetable-photo import
([vision](vision.md)). Task creation accepts `report_type="photo"` and submission
now requires an available, privately verified media reference. Initial maintenance
fault creation and service-log commands still require `attachment_ids: []`;
an existing open fault now accepts a separately reviewed `fault_photo_attach`.
School supports reviewed calendar import but not timetable-image import
([tasks.py](../custom_components/family_assistant/domain/tasks.py),
[maintenance.py](../custom_components/family_assistant/domain/maintenance.py),
[school.py](../custom_components/family_assistant/domain/school.py)). The first
media slice must therefore add a shared transport and authorization primitive,
then integrate one existing object type at a time. It must not make the empty
maintenance fields or a made-up School import object appear functional.

The existing `Engine` is the authority for household commands: it resolves a
linked HA user to a family member, serializes writes, persists a copied state,
and records idempotent results. `Engine.view` is the only family projection
([engine.py](../custom_components/family_assistant/domain/engine.py)). Binary
content does not belong in that JSON state, a WebSocket command, an audit result,
or an outbox event. The HTTP adapter must use the same `entry_id -> Runtime ->
actor_for_ha` chain as the existing WebSocket adapter; HA administrator status
alone is never family permission
([websocket.py](../custom_components/family_assistant/websocket.py),
[runtime.py](../custom_components/family_assistant/runtime.py)).

## Accepted input

The complete shared service is designed for the four formats below. The first
implementation is deliberately narrower: one `task_report` or `maintenance_fault` attachment,
JPEG/PNG/WebP only. PDF remains rejected until the maintenance-document lane
has a bounded parser and its own acceptance tests.

- One authenticated upload is at most 10 MiB (`10 * 1024 * 1024` bytes).
- Current accepted content is JPEG, PNG or WebP only; PDF is a future lane.
  The server derives the MIME type from verified bytes; client `Content-Type` and filename are
  hints and are never persisted or reflected.
- SVG, HTML, XML, archives, executable formats, URLs, filesystem paths, and
  base64-in-JSON are rejected. The API accepts a request body, not a remote
  source parameter, so it cannot fetch `http:`, `file:`, UNC, or HA-local paths.
- Read at most 10 MiB plus one byte while streaming to a same-filesystem
  temporary file and computing SHA-256. Reject an empty body and excess length,
  including chunked requests that omit or lie about `Content-Length`.
- Verify an image with a bounded decoder as the claimed JPEG/PNG/WebP format and
  enforce a pixel/dimension limit to prevent decompression bombs. Verify a PDF
  signature and bounded complete structure with a maintained parser. PDF is
  always downloaded, never rendered inline by this integration. Polyglots,
  malformed/truncated files and multi-image surprises outside the documented
  policy are rejected where detected; no universal polyglot detection is claimed.
  A misleading permitted image MIME hint is replaced by the decoded MIME, never
  treated as authoritative. Original bytes and embedded EXIF metadata are retained.
- Use a cryptographically random media ID and a separate cryptographically
  random server filename. Neither contains an original name, member ID, object
  ID, purpose, MIME type, or digest. Do not content-deduplicate across households.

The implemented image lane allows at most five pending uploads per uploader,
20 pending per household, 250 MiB of verified plus reserved-byte budget and
10,000 metadata records. A reservation consumes the full 10 MiB budget until
verification or completed cleanup. At most two file operations/decoders run per
household; concurrent uploads for the same ID are rejected. Static images are
limited to 8192 pixels per dimension and 16 million pixels total.

## Metadata and state machine

Add a top-level `media` mapping to the Engine state. A record has this exact
private shape (timestamps omitted below only for readability):

```text
{
  id, revision,
  uploader, uploader_revision,
  purpose,                         # server-supported enum
  mime_type, size_bytes, sha256,   # null until verified
  status,                          # reserved|available|attached|deleting|deleted
  scope,                           # server-derived object, never client authority
  blob_key,                        # random filename; never projected
  created_at, updated_at, expires_at
}
```

Implemented purposes are `task_report` and `maintenance_fault`; planned values
are `maintenance_service_log` and `school_timetable_import`. Unsupported values
fail closed. The implemented and planned scope shapes are:

```text
{kind: "uploader_private", member, member_revision, intended_target}
{kind: "task_report", task_id, report_generation, assignee, assignee_revision}
{kind: "maintenance_fault", fault_id}
{kind: "maintenance_service_log", log_id}
{kind: "school_timetable_import", import_id, member, member_revision}
```

The server constructs every scope and checks that the media ID is still present
in the named object's attachment slot. It must not rely only on a scope string
stored on the media record. A target's unrelated revision change does not break
an attachment; removal of the exact reference, target privacy loss, or subject
identity rebind does.

Use these transitions:

1. Add `media` as an Engine handler namespace, but not as a user-configurable
   module. Explicitly exempt only that namespace from the generic module lookup
   and give it its own replay authorization. The first action is
   `media.reserve` with exact payload
   `{purpose: "task_report", uploader_revision, task_id, task_revision}` and an
   ordinary operation ID. It checks the current linked active/non-guest member,
   exact uploader epoch, Tasks module, task revision/status/report type,
   existing task-submit permission and quotas. It creates `reserved` metadata
   with an `uploader_private` scope whose server-built `intended_target` pins
   that task and returns only `{id, revision, status}`. The authenticated `PUT`
   must supply that exact revision; knowledge of the random ID is never
   authority. Replay repeats all current actor/module/target checks before
   returning the frozen receipt.
2. An authenticated `PUT` streams bytes for that reservation. Immediately
   before accepting data and again before publishing success, resolve the same
   entry and HA user and require the exact active uploader epoch and current
   purpose/module permission. Write and `fsync` a private temporary file,
   validate it, then atomically publish an exclusive hard link at the random blob
   key and unlink the temporary name. Existing bytes are never overwritten.
3. The adapter calls `Engine.system_update` with the verified MIME, byte count,
   digest and reservation revision; the blob key comes only from the persisted
   reservation. Its synchronous callback is
   idempotent: an already-available record returns the same receipt only when
   every verified value matches. Only after Store persistence succeeds is
   status `available`. A lost HTTP response retries the same transition and
   never creates another blob. Filesystem work happens before this call, never
   inside the Engine lock.
4. The consuming domain action attaches an `available` record in the same
   Engine transaction as the target mutation. It rechecks the actor, uploader
   epoch, purpose, media revision, target revision/identity and target-specific
   permission, writes the media ID into the target, changes the server-derived
   scope and status to `attached`, and returns the existing consumer's opaque
   receipt. No generic `media.attach` action may bypass a consumer domain.
5. Deletion is two phase: persist `deleting`, unlink the known private blob
   idempotently, then persist a content-free `deleted` tombstone. A reconciler
   handles every crash boundary. It never follows symlinks and only touches a
   validated random basename inside this entry's resolved media directory.

The Engine currently rejects any schema version other than its single current
version and has no incompatible migration path. The additive first slice uses
the Engine's existing idempotent state preparation to add an empty `media` bucket
while preserving all known and unknown existing keys, and test old-state load
and restart. It need not force a schema-version change merely for this additive
bucket. Any later incompatible record change or HA `Store` version transition
requires a separately designed migration rather than silent rebasing
([const.py](../custom_components/family_assistant/const.py),
[engine.py](../custom_components/family_assistant/domain/engine.py)).

## Consumer contracts

### Task reports

Extend `tasks.submit` only when `report_type == "photo"` to require the exact
field `media: {id, revision}` and forbid report text. The first slice accepts
exactly one attachment.
Text and `none` reports keep their existing payloads. Store media IDs in a new
`report_media` list rather than putting an ID in the text `report` field, and
advance a durable `report_generation` for each accepted submission. When
the existing reassignment/change workflow moves a report to `previous_reports`,
move its media IDs with it. A current assignee can attach only their own
epoch-bound available upload. A privileged actor may attach their own upload
where the existing task-submit authorization permits and may review it because
the current task projection permits that. An ordinary child remains limited to
their own current assignment epoch. School homework remains a private task, so
its existing `task_access.may_view` and identity guard also apply
([task_access.py](../custom_components/family_assistant/domain/task_access.py),
[school_work.py](../custom_components/family_assistant/domain/school_work.py)).

Content authorization must find the exact media ID in the current authorized
task projection. A child cannot retrieve a prior assignee's media because
`previous_reports` is already removed from their private projection. Parents
can retrieve retained reports. Generic task notifications keep only the current
task/member stamps; no media ID, name, digest, path, or bytes enter `Context.notify`
([context.py](../custom_components/family_assistant/domain/context.py),
[task_events.py](../custom_components/family_assistant/domain/task_events.py)).

### Maintenance

Recurring maintenance services can now require a photo report: the generated
private task uses exactly the Tasks upload/review contract. Editing an unrelated
service field preserves its existing report type. This does not attach a photo
to the initial fault or to a manual service log.

Those are later lanes, not part of the task-report slice. Replace the
deliberate empty-list validator only after maintenance media is available.
`maintenance.fault_report` may attach `maintenance_fault` uploads owned by the
current reporter epoch, while preserving all current asset/reportability and
reporter-revision checks. `maintenance.service_log` may attach
`maintenance_service_log` uploads only for a currently authorized parent and
the exact reviewed asset/log command. The IDs are committed atomically with the
fault or immutable service log. Asset notes, warranty data, fault details and
documents stay governed by the existing parent/related-member projection;
being the uploader is not a permanent bypass after attachment
([maintenance.py](../custom_components/family_assistant/domain/maintenance.py)).

### School import

This is also outside the first slice. Do not enable
`school_timetable_import` reservations until a real School import
record, projection and actions exist. That later workflow should be:

```text
parent upload -> explicit local parse or provider-consent command
              -> private candidate -> parent edits/reviews
              -> normal timetable_save with current child/timetable revisions
```

An upload never invokes OCR, an LLM, Telegram, task creation, a routine, or a
device. An external OCR/provider call needs an explicit per-operation consent
screen naming the provider and exactly which file is sent; enabling an assistant
or recipe provider is not consent. Parsed text is untrusted input and cannot
write a timetable directly. The accepted write must use the existing full
replacement/versioned School contract.

## Content endpoint and projection

Register authenticated, non-static HTTP views for
`PUT /api/family_assistant/media/{entry_id}/{media_id}` and
`GET /api/family_assistant/media/{entry_id}/{media_id}`. Both require exactly one
`X-Family-Media-Revision` header containing a strict positive decimal revision.
PUT uses the original reservation revision, including an exact-body retry after
finalization; GET uses the current available/attached revision. Never
place blobs below the existing `/family_assistant/frontend` static route. Every
request performs all of the following immediately before opening a blob:

1. resolve the exact Config Entry runtime;
2. map the authenticated HA user through `Engine.actor_for_ha` (no HA-admin
   shortcut);
3. read a fresh Engine snapshot/projection;
4. validate active role and member revision, required module, metadata shape,
   `attached`/permitted `available` status, and exact live target reference;
5. open only the metadata's validated random basename from the resolved
   entry-private directory, then verify size and SHA-256 before serving;
6. recheck identity/scope before committing response headers. If authority
   changed while a file was being verified, return a generic denial and no body.

Serve a successful response with the verified `Content-Type`, exact
`Content-Length`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store,
private`, `Pragma: no-cache`, `Cross-Origin-Resource-Policy: same-origin`, and
`Content-Disposition: attachment` using a fixed ASCII filename and verified
image extension, without the media ID. Do not emit user filenames, ETags,
digests, local paths, directory listings, redirects, or inline PDF disposition.
Use the same generic not-found/forbidden surface for inaccessible IDs to avoid
an existence oracle. Disable ranges initially unless their authorization and
integrity semantics are separately tested.

`Engine.view` should not expose a global media library. A consumer may project
only `{id, revision, purpose, mime_type, size_bytes, status}` beside an attachment
that the actor can already see. Hide `sha256`, uploader identity/epoch,
`blob_key` and deletion timestamps. Receipts remain opaque.
The existing assistant projection already allowlists scalar task fields and
excludes private tasks; keep all media fields out of it
([plans.py](../custom_components/family_assistant/assistant/plans.py)). Telegram
text and outbox rendering must not add upload/download links or media identifiers.
Diagnostics remain counts-only and may add at most aggregate object/byte counts,
never names, MIME-linked target data, hashes, paths, IDs, URLs or content
([runtime.py](../custom_components/family_assistant/runtime.py)).

## Smallest implementation sequence

1. Add a pure `domain/media.py` for exact-shape validation, reserve/replay
   authorization, idempotent finalization, consumer-scoped attachment and read
   authorization. Add the empty bucket through the state-preparation utility,
   route only `media.reserve`, and keep media out of `Engine.view` except through
   consumers.
2. Add an integration-owned blob store and authenticated HTTP views. Give
   `Runtime` one media manager, initialize it only after state load, and drain it
   on unload. Filesystem methods receive validated media records; they never
   decide family permission or mutate Engine snapshots directly.
3. Integrate the single-photo `tasks.submit` path and its task projection. Keep
   text/none behavior byte-for-byte compatible and leave maintenance/School
   validators closed.
4. Add the card upload/review flow only after backend tests pass. Freeze the
   reservation, media and task revisions plus operation IDs; a failed or lost
   response retries those exact values. A refresh that changes entry, actor,
   epoch, role, module, task or media status disables the stale draft.
5. Run pure domain tests, filesystem fault/restart tests, real authenticated HA
   HTTP/WebSocket tests, frontend tests, browser privacy/revocation tests,
   diagnostics/LLM/Telegram canaries, packaging checks and release-archive
   inspection before enabling the feature.

## Retention, recovery, and release hygiene

Current code implements reserved (one hour) and available (24 hours) expiry,
two-phase deletion with content-free tombstones, exclusive immutable blob
publication, exact-body retry after Store failure, and drained unload. A bounded
scanner also recovers stale temporary files and unreferenced blobs. It handles
the crash between exclusive hard-link publication and temporary-name removal
only after proving that both names reference the same regular file in this
entry's private directory. Unknown names, symlinks and unusual hard links are
retained and flagged, never guessed at. A malformed ownership inventory prevents
orphan deletion while independent valid expiry can still proceed.

Each pass inspects at most 256 directory entries, attempts at most 100 expiry
transitions and verifies at most 16 available/attached blobs. The scan cursor
continues across passes. Temporary names have a one-hour grace; unreferenced
opaque blobs have a 24-hour grace. Upload publication and collection cannot run
concurrently. Fresh identity is rechecked immediately before a scoped unlink.
Missing/corrupt retained bytes produce a code-only health error without deleting
the report or its history. Skipped/busy collection does not clear an existing
health error. No explicit retained-report purge, tombstone capacity reclamation
or complete entry deletion exists yet.

The Home Assistant [backup platform](https://developers.home-assistant.io/docs/core/platform/backup/)
drains active media I/O, then freezes each loaded Engine before backup. Entry
setup/unload and Options commits are gated while the coordinator exists.
Views remain readable; new commands and media requests return bounded errors.
Post-backup unwinds only its own leases, including partial acquisition failures
and cancellation. These hooks do not create an archive or schedule a backup.
Include Home Assistant configuration in the backup: both its Store and
`family_assistant_data` must travel together, not the HACS code alone. Actual
encrypted archive creation and a complete HAOS/container restore remain distinct
release gates, even when synthetic copy/reload checks pass.

- `reserved` and staged-but-unpublished blobs expire quickly (recommended one
  hour); unattached `available` uploads expire after 24 hours. Expiry is based
  on persisted UTC deadlines, is bounded per sweep, and rechecks status before
  deletion.
- Attached content remains while an authorized retained object references it.
  Archiving a task is not deletion because task history is intentionally
  retained. A later user-visible retention policy must define when archived
  reports, faults, logs and imports are purged; do not silently infer it now.
- Reconciliation starts after state load and runs periodically. It removes old
  owned `.upload-…` files, completes `deleting`, flags missing/corrupt bytes
  without rewriting retained metadata, and deletes valid opaque orphan
  files not referenced by this entry after a grace period. It never guesses a
  link from a filename and never crosses household directories.
- Store failure after exclusive blob publication leaves a recoverable reservation
  plus blob, retained for exact retry or expiry; Store success
  before unlink leaves a recoverable `deleting` record. A process crash at every
  transition and a lost HTTP response must converge without duplicate metadata,
  leaked temporary content, or a reference to another blob.
- Unload cancels/drains media tasks and closes open files before Runtime removal.
  Backup/restore behavior and complete entry deletion cleanup must be tested in
  the target HA version before release. HACS upgrade/uninstall must not treat
  integration-owned data as code or publish it.
- Public fixtures contain only generated tiny synthetic files. CI must inspect
  the release archive and reject blobs, upload directories, original filenames,
  tokens, paths, canary content, or other household data. Logs and exceptions
  contain bounded codes, never body samples or metadata values.

## Adversarial acceptance matrix

The feature is not ready until tests cover:

- unlinked HA admin, guest, sibling, unrelated adult, other household, inactive
  member, changed member epoch, disabled consumer module, stale media/target
  revision, wrong purpose and malformed scope;
- authorization revoked before upload, during verification, after attach, and
  immediately before download response; no bytes or informative provider/parser
  error cross the revoked boundary;
- missing/null/bool/float/string/out-of-range revisions, unknown/extra fields,
  reused operation ID with changed payload, concurrent double attach, and replay
  after role/module/identity change;
- exactly 10 MiB versus 10 MiB plus one, chunked oversize, zero bytes, misleading
  MIME/extension, JPEG/PNG/WebP/PDF polyglots, SVG/HTML/ZIP, decompression bombs,
  malformed PDF, traversal names, encoded separators, absolute/UNC paths,
  symlinks and a blob key belonging to another entry;
- Store failure before/after reservation/finalization/attachment/deletion,
  filesystem write/rename/fsync/unlink failure, restart at each boundary, lost
  successful response and bounded orphan sweeps;
- a reassigned private task, School homework child epoch change, maintenance
  reporter/assignee epoch change, retired asset, archived object, removed media
  reference, and one actor who remains authorized while another loses access;
- headers and forced download for all formats, no cache reuse after revocation,
  no hash/path/body in outbox, audit, processed result, LLM prompt, Telegram,
  entities, diagnostics or frontend error messages, and no media ID outside its
  opaque authorized command receipt/audit or authorized object projection; no
  cross-entry hash or timing existence oracle;
- upload alone causes no OCR/provider call, Telegram send, task/routine/device
  action, shopping/stock change or penalty; a reviewed School import can only
  call the normal versioned timetable save after explicit provider consent.

## Implementation gates

Additive state preparation, bounded isolated image decoding, quotas, authenticated
streaming upload and private GET are tested. GET buffers at most one 10 MiB image
per operation so size/hash verification and authority checks finish before any
response body is returned. The actual HA container tests use Pillow 12.3.0 from
its normal interpreter environment; the isolated helper fails closed when that
dependency or POSIX process limits are unavailable. Nonstandard Core dependency
paths require separate acceptance. Full capacity/backup/delete semantics
remain release gates. A bounded PDF parser/structure policy is an
additional gate before maintenance documents; the School import object's actual
domain contract and explicit provider-consent UX are additional gates before
School import. These are security and recovery requirements, not optional UI
polish.
