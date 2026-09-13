# Optional task reviewer reminders

Parents and owners can set `review_minutes` on `tasks.create` or `tasks.revise`:
an integer from 0 to 10080 (one week). Zero disables it. Omission preserves the
previous value on edit and leaves the existing record shape unchanged on create.
Existing tasks and new tasks without this field remain off. Children and adults
cannot set or change it, including setting zero. Personal reminders reject the
field because they have no parent-review workflow.

The Tasks card exposes the interval in the creation form's advanced settings and
the task editor's deadline settings, with EN/RU/UK labels. Multi-person creation
shows it in the confirmation preview and copies it into each independent task.
Submitted work must first be returned for changes before its policy can be edited,
matching the existing task editor and domain lifecycle. Recurring-series template
configuration and Telegram natural-language review-policy parsing are not added;
an individual editable occurrence can use the normal task editor.

Submission persists a separate review deadline at the submission time plus the
chosen minutes, even when the child task has no due date. This window never changes
the child's due date or applies points. Submitted tasks remain exempt from child
deadline escalation and penalties. It schedules one overdue-review notification,
not a repeating cadence: the first clock pass at or after the review deadline
queues a durable `task_review_overdue` event for parents' private channels. Quiet
hours, retry backoff, partial fanout and uncertain sends use the existing outbox.
Restart or downtime produces one catch-up reminder, with no replay of missed slots.
An already submitted legacy record is not retroactively scheduled.

Each opted-in submission has a monotonic review generation and the exact submission
operation ID. The deadline also records the submission time, attachment generation
and IDs, task source, assignee revision, and active owner/parent membership revisions.
Public task reads and command receipts expose only the review due time and status;
they never contain this internal snapshot or its attachment IDs and source lineage.
The scheduler and send-time task scope both check this snapshot. Requesting changes,
completion, cancellation, archival, changed identities/reviewer membership, changed
source/report, or disabling Tasks revokes the pending reminder. Disabling and then
re-enabling Tasks before a clock pass cannot revive an old reminder. A fresh
submission receives a new generation, even with an identical timestamp.

Parent notifications resolve only to currently enrolled parent/owner private chats;
they never fall back to the family group or a child. A member rename or other
revision change conservatively revokes the old reviewer window; a fresh report can
start a new window. Changes in a source module's configuration do not revoke an
already materialized ordinary task: the task's own source/identity must change.

Verification uses `tests/test_task_review_deadlines.py` through real Engine commands,
persist/restart snapshots, the notification worker and Telegram target resolution,
including a verified synthetic photo attachment. `tests/frontend-task-review.test.js`
uses actual task-card controls and asserts their canonical payloads. Run both with
the existing task event, delivery, photo, creation, item and multi-person suites.
These checks do not claim real household delivery or live Home Assistant acceptance.

The bounded September 13 implementation check passed **336 Python tests** across
review reminders, task deadlines/delivery/media/editing/multi-create/series,
personal-task security, member revisions and the notification worker. **49 Node
tests** passed across review controls and the existing creation, item and multi-
person forms. Ruff lint/format and diff whitespace checks passed on the changed
Python scope. Release-wide and native-HA checks remain separate gates.

Subsequent combined acceptance: the native HA2026.9.2 command-completion case
verified creation, submission, persisted replay/reload and reminder revocation.
Eleven actual Chromium synthetic scenarios passed localized mobile create/edit,
default omission, bounds, private/personal/child controls and frozen single/batch
retries. These are browser/backend evidence, not live household message delivery.
