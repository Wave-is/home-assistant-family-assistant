# Online-school connectors: evidence, use cases and delivery plan

## Purpose and boundaries

Turn the existing School module into a useful read-only assistant for families
whose children attend different schools. A household can have multiple provider
connections; each reviewed binding links ONE source student to ONE current
Family Assistant child. No hard-coded family names, school credentials or IDs.
Keep existing manual timetables/homework intact and distinguish imported facts
from local completion/notes. No automatic school submissions, teacher messages,
grade edits, purchases, academic decisions, court penalties or device actions.

## Evidence from the initial provider audit

The authorized A+ STEAM portal at https://steam.respublika.school uses a normal
same-origin form login and read-only JSON endpoints behind a session. Findings
below are sanitized interface contracts, not copied household records:

- `GET /auth`, POST `/auth`: form `_token`, `email`, `password`, `login` (empty
  submit value). Parse CSRF from HTML; use an isolated per-connection cookie jar.
  Never log credentials, cookie/CSRF values or raw authentication responses.
  Successful login can redirect to the bare same-origin URL with an empty path;
  normalize that path to `/` without permitting external redirects.
- Authenticated HTML has `<app-header :header_data='JSON'>`. Only read
  `user.group`, `user.children` (ID-to-name map), or the authenticated student's
  own ID/name for identity discovery. The same object also includes address,
  contact, medical and canteen details: discard these immediately, do not store,
  expose, export or send them to any model.
- `/schedule/student/get/{student}/{week}` returns `week_days`, `lesson_numbers`,
  `week`, `prev_week`, `next_week`, and `student.user_id`. Days use `DD.MM.YYYY`;
  lessons may be ID-keyed objects. Fields include stable lesson ID, order, subject,
  classroom, teacher, group, cancellation/replacement and replacement metadata.
- `/daybook/get/{student}/{week}` returns seven day rows and arrays of lessons.
  Rows have date, start/end, subject/room/teacher, topic/homework (plain and HTML),
  work_time, homework_files, lesson_files, grades, cancellation/replacement.
  File collections can be `null` for lessons without files; this is empty, not
  a malformed reply. Other unexpected scalar/object shapes still fail closed.
  The day date is local `DD.MM.YYYY`; lesson.date can be UTC midnight equivalent
  on the PREVIOUS UTC date. Do not split that timestamp to infer the local date.
  The interface exposes actual homework text and subject topics. Lesson day is
  a preparation target, NOT proof of a separate teacher-declared submission date.
- JSON `prev_week.url` can omit the student segment. The real UI preserves the
  current student and uses `prev_week.num`. Never follow server-supplied cross-
  origin URLs or rebind to another child when navigating periods.
- `/studentparent/journal/get/{student}/{month}` exposes `month_num` (academic
  month index, NOT calendar month), `month_abs_num`, `month_title`, `dates`,
  `subjects`, `grades`, `absents`, `student`. The audited month was empty for
  grades and absences: empty is valid, not an error and never a zero grade.
  The shipped UI confirms nonempty `grades[day-or-period][subject_id]` lists of
  `{grade_value, comment, name}` and `absents[day][subject_id]` with comment.
  Preserve nonnumeric marks and period labels; no invented averages or scale.
- Shipped UI confirms file metadata `id`, `original_name`, `ext`, `size` and a
  download route. No actual attachment/grade rows were available in the sampled
  weeks; those parsers require synthetic tests plus later real-record acceptance.
- School announcements and canteen/messages menus exist. Their additional
  contracts and sharing semantics are not yet verified; do not claim automatic
  message import, attendance-at-the-gate, spending, file downloads or news sync.

## Prioritized user cases

| Case | Useful result | Safeguard |
| --- | --- | --- |
| Child: “What lessons tomorrow?” | Dated times, room, replacements/cancellations, source link | Selected child only; explicit freshness and timezone |
| Child: “What homework for tomorrow / Science?” | Exact assignment, topic, links and teacher estimate | Explain target lesson vs explicit deadline; no invented tasks |
| Evening preparation | One digest of next-day work, ordered by lesson/time | Opt-in, quiet hours, source freshness, one daily receipt |
| Long assignment | Earlier reminder based on teacher estimate or parent lead time | State estimate source; never infer a missed submission |
| Parent: “How is school this week?” | Per-child grades/changes and upcoming workload | Private parent view; no sibling disclosures to children |
| New or changed grade | Batched factual grade/comment update with source | First sync is baseline; no grade shaming or automatic punishment |
| Changed lesson / new homework | Explain old/new facts in a bounded digest | Hash-based dedup, correction-aware updates; no message per row |
| Multiple schools | Independent settings/health/source for each child | Separate cookies, bindings, revisions, retention and retry backoff |
| Portal unavailable | Last-known information visibly dated, retry later | Never erase good cache, claim “no homework”, or spam parents |
| Child marks preparation done | Local personal acknowledgement, not school submission | Keep source assignment intact; edited source can reopen review |

Start with factual deterministic answers; optional tutoring can use ONLY the
selected assignment after explicit configured consent. It must teach the child,
not submit work or expose private records through internet search/model prompts.

## Architecture / acceptance order

1. Provider-neutral bounded snapshot and per-child source binding, retained under
   `state.school.online`; credentials remain in Config Entry Options only.
2. An isolated A+ provider session: CSRF login, allowlisted discovery, same-origin
   read-only reads, pinned student validation, bounded periods/body size, finite
   timeouts, logout/401/419 handling, 429 backoff and cancellation/close.
3. Source synchronization updates a private cache transactionally, preserving
   manual school data. Stale member/binding/configuration epochs cannot publish.
   Initial sync establishes a silent baseline; errors retain the previous cache.
4. Owner setup with multiple connections and explicit discovered-child mapping;
   no raw JSON configuration or secret in projections/browser storage.
5. Parent/self-only dashboard and deterministic bot queries, then separately
   enabled bounded private preparation/change digests. No family-group grade dump.
6. Adversarial tests: two schools/children, revoked binding, stale auth, blank
   response vs empty data, malicious HTML/link, redirects to other origins,
   source student mismatch, simultaneous sync, backup/reload, notification replay.
7. Real provider read-only smoke with private credentials and counts-only report;
   fictional public fixtures; normal privacy/package/unit/browser/HA gates.

Implementation and private-provider acceptance must be reported separately.
This branch is independent of the household control-center improvements on
`codex/home-assistant-next`; shared changes merge only after review and tests.

## Implemented development slice (2026-09-13)

- Up to eight independently reviewed Respublika student connections, with native
  owner-only Options account/discovered-student steps in English, Russian and
  Ukrainian. Other provider adapters are not implemented yet.
- A read-only poll every 15 minutes; one-hour authentication backoff, bounded
  request/pass timeouts, no overlapping pass. Backup, unload, module switches,
  account revisions and child revocation fence pending results and delivery.
- Three diary weeks plus current journal. Private normalized cache, six-hour
  freshness warning, bounded change history, no raw profile/medical/canteen data.
  Poll failures retain the cache. A reviewed account-generation change clears
  it intentionally: the same numeric student ID may exist in another school.
- The School card shows source/last success/coverage, today/tomorrow homework,
  topic/teacher estimate, cancellation/replacement, literal marks and absences.
  External links require a click; attachment metadata is visible, not downloaded.
- Deterministic private bot `/school [child]`, `/homework [child]`, `/grades
  [child]`, with today/tomorrow and selected natural RU/UK/EN queries. A parent
  with multiple connected children must choose one. Group queries redirect to a
  private chat. Imported facts and quoted school replies do not enter the LLM.
- Explicitly enabled private next-day preparation digests and batched change/new
  mark notices, durable deduplication, quiet hours and dispatch-time source/
  recipient checks. Old marks are not announced on initial import. No school
  posting, automatic punishment or claim that local completion is submission.
- Local homework acknowledgement has a guarded domain command and existing
  status display, but no new dashboard write button yet.

The primary agent's separate read-only real-account smoke passed both the
provider and actual domain normalizer. Only counts/schema evidence was retained
outside this repository. It confirmed three weeks of lessons, actual assignment
text and links; that account's sampled journal and attachments were empty.
Nonempty grades/absence/file parsing therefore has synthetic contract coverage,
not claimed real-record acceptance. No production HA deployment, real bot
notification or school write was performed by these tests.

Verification before the first development-branch checkpoint: 5,221 Python
tests passed, five skipped, 23 subtests passed. The full browser suite passed
261 scenarios; a subsequent link-label-only improvement passed its focused
eight-browser rerun. Primary inspection confirmed readable mobile layout.
Ruff/format, translation generation, privacy and runtime import/ZIP checks pass.
The new isolated `ha_online_school_smoke.py` is wired into CI; its actual HA
result must be recorded separately rather than inferred from unit tests.

Still open: authenticated HA lifecycle acceptance of this new connector; real
nonempty journal/attachment records; subject-specific/long-work preparation;
explicit tutoring consent; additional providers; longer historical journal
retention, announcement contracts and attachment downloads. These are separate
requirements, not implied by a green basic connector smoke test.

## Initial implementation contract

Provider `RespublikaClient(base_url, username, password)` owns an isolated
aiohttp session (never the HA shared cookie jar). `await discover()` returns only
`[{id: str, name: str}]`; `await fetch(student_id, timezone, now)` returns the
normalized snapshot below; `await close()` always retires its session. Transport
factory injection is test-only. GET routes have optional student/week/month
segments in the portal's shipped Ziggy table: omit only the period, never the
selected student. Initial fetch is the default diary, its adjacent bounded
weeks and the current journal; follow period numbers, not untrusted URL strings.

Snapshot fields (all strings plain text, bounded; no raw HTML/cookies/credentials):

```text
student_id, student_name, timezone, source_url,
coverage_start (ISO date), coverage_end (ISO date),
lessons[]: id,date,start,end,subject,room,teacher,topic,homework,
           estimated_minutes (int|null),cancelled (bool),replacement (bool),
           links[] (HTTPS URL),attachments[] ({id,name,ext,size})
grades[]: id,date (ISO date|null),period,subject,value,comment,kind
absences[]: id,date (ISO date|null),period,subject,comment
```

Store `school.online` contains `sources`, each with stable ID, revision, member,
member_revision, label, timezone, enabled, configuration generation, last attempt,
last success, status, normalized snapshot and bounded change history. Credentials
are NEVER in this bucket. Owner/parent can read selected children; a child can
read only its own currently authorized sources. Disabling/rebinding a source
does not turn previous child's cache into new child's data. Imported records
never overwrite `school.timetables`, homework tasks or local preparation state.
