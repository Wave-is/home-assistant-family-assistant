# Family Academy — implementation contract

Status: proposed extension, stage 1 recorded; stage 2 started with isolated
rational validation. No HA runtime integration or release implied.
Scope: a local-first optional Family Assistant module, with the first course
covering revision of Ukrainian grades 6–7 mathematics taught in English.
This document complements the existing product vision; approval of a branch
does not authorize deployment, external providers, or publication.

## 1. Product goals

- A child can take a short scheduled interactive lesson, ask for help, and
  demonstrate knowledge independently, not just consume AI explanations.
- A parent can inspect skill evidence, choose a schedule, adjust the course,
  pause it, and see the next review date.
- The course functions without LLM, TTS, Internet, or Telegram.
- The initial scope includes grade 6 mathematics and grade 7 algebra and
  geometry. English is the default teaching language; Ukrainian is an optional
  explanation/glossary language. UI and administration follow EN/UK/RU project
  localization. Do not confuse English reading difficulty with math ability.
- All household data remain in HA storage; no household information, real
  student answers, credentials or private URLs enter the public repository.

## 2. Delivery surfaces

A single learning engine serves an authenticated Home Assistant Academy
card/panel and the existing private Telegram bot. **Telegram Mini App is
the primary target learner surface**, with responsive interactive HTML
lessons opening inside Telegram; HA remains the primary parent/admin surface
and a local learner fallback. Chat commands, buttons and voice complement
the lesson rather than replacing it. Use existing identity binding, command
router, scheduler, outbox and current role checks. Do not create a second
Telegram polling process.

For access away from home, the Mini App requires a trusted HTTPS origin
reachable by the child. Use a dedicated narrowly scoped Academy gateway,
not public HA administration or generic HA WebSocket/service access.
Validate Telegram initData on the server (signature, age, bot and current
private member binding); protect replay, issue short-lived scoped sessions,
check current enrollment/identity on every request, revoke stale sessions
and use strict origin and content security policies. Never put a bot token,
HA token or grading key in HTML. Serve reviewed first-party lesson assets
without a third-party script dependency. External gateway and provider
activation require explicit owner configuration and isolated end-to-end
security testing. Native HA learning remains usable locally without them.

The learner UI should preserve current lesson, visual state where useful,
and unsent-answer state across reconnects without retaining sensitive
history in browser storage. Server-acknowledged progress is canonical.
A disconnected or unavailable installation never counts as missed work.
Remote learning during travel must be verified from outside the home LAN;
the current HA card alone does not satisfy that acceptance gate.

## 3. Module boundaries

Required runtime stays in custom_components/family_assistant. Proposed paths
(to align with existing domain conventions before implementation):

- academy/ — pure curriculum, task templates, validators, skill evidence,
  review scheduling and lesson planning; no HA/network calls in pure functions.
- academy_api.py — authenticated boundary; reuse the current Engine/manager
  transactions and persistence conventions rather than creating a second
  identity system.
- frontend/ — namespaced Academy card, accessible touch/keyboard interactions,
  lesson visuals and parent view using existing registration machinery.
- telegram/ — bounded Academy commands/callbacks using the current bot;
  explicit learning-session scope; no generic command execution inside tutor.
- translations/ — EN/UK/RU localized settings and messages.
- tests/ — pure domain, role/API, scheduler, storage/reload, browser, upgrade.

Academy is disabled by default, independently configurable per household.
A disabled module must not emit reminders, invoke providers or mutate learning
state; existing data are retained and owner-controlled. Core content and
validators have no required external dependencies. Any future SymPy dependency
needs packaging review and bounded expression parsing; never eval user input.

## 4. Versioned curriculum and content

Course pack has stable course_id, curriculum_version, locale, source mapping,
license, skill IDs, prerequisites, lesson objects and task templates. A lesson
contains objective, concise theory, worked examples, visual specification,
misconception hints, optional facts, independent practice, transfer task and
exit check. A task has template_id/version, deterministic seed, parameters,
answer type, validator ID, expected answer (server only), hints, solution,
difficulty, skill IDs and locale text. No executable code from content packs.
No unreviewed model-generated task enters a scored assessment. The tutor may
ask adaptive unscored follow-up questions, grade explanations provisionally
against a reviewed rubric, and request a fresh validated independent task.

Initial curriculum inventory (provisional, to map to the school's selected
MОН model program and current textbook edition before full course acceptance):

Grade 6:
- divisibility, primes, factorization, GCD/LCM;
- fractions: equivalence, comparison, addition/subtraction, multiplication,
  division, mixed numbers and word problems; decimal revision and conversions;
- ratios, proportions, direct/inverse proportionality, scale, percentages;
- circles, circumference, area, charts;
- signed/rational numbers, number line, absolute value, all four operations;
- expressions, distributive law, linear equations, coordinate plane.

Grade 7 algebra:
- linear equations and word problems, natural-number powers;
- monomials, polynomials, operations and factorization;
- identities / formulas for abbreviated multiplication;
- functions, linear functions, graphs and interpretation;
- systems of two linear equations (graphical, substitution, elimination).

Grade 7 geometry:
- points, lines, segments, rays, angle measurement and constructions;
- adjacent/vertical angles, perpendicular/parallel lines and angle relations;
- triangles, congruence, isosceles triangles, median/bisector/altitude;
- angle sum, right triangles, triangle inequalities;
- circle, tangents, straightedge/compass constructions as applicable to the
  selected model program.

Prerequisites form a directed acyclic graph (validate missing nodes, cycles,
  duplicate IDs). Geometry and algebra can be interleaved. Exact skill coverage,
  ordering and source references are reviewed separately; no copying textbook
  text or illustrations without permission. Create original examples and SVGs.
Target for full course, not the first increment: roughly 60–80 granular skills,
600–1000 reviewed parameterized exercise templates and 15–20 interaction types;
revise targets with actual curriculum mapping rather than inflate counts.

## 5. Evidence and mathematics checking

Validators return correct / incorrect / invalid / needs_review, feedback code
and normalized answer where appropriate. Invalid input does not count as a
wrong mathematical answer. Use exact Fraction arithmetic for rational numbers.
Accept equivalent fractions, decimals and signed values when the task permits;
  enforce reduced form only when asked. Unit handling is explicit, not guessed.
Limit input length, numeric digits, exponent, nesting and computational cost.
Algebra validators must check the relevant domain, preserve excluded values,
and reject unsafe tokens. Transformation checking distinguishes equivalence of
expressions and equality of solution sets; extraneous roots are not accepted.
Geometry numeric tasks use explicit exact values or documented tolerance.
Construction tasks check constraints, not resemblance to one image.
Open proofs and explanations are provisional rubric assessments, not automatic
  verified facts; ambiguous cases go to manual review.

A scored assessment never asks an LLM whether a deterministic answer is right.
The tutor can explain a verified error or choose a hint, not mutate a grade.
Keep first independent attempt separately from attempts with hints or solutions.
Diagnostic answers record evidence but are not punitive. Do not label a skill
mastered from a single correct multiple-choice response.

## 6. Learning state and scheduling

Store versioned records scoped by household and member identity revision:
- enrollment: course/version, locale, policy, status, schedule and exceptions;
- session: stable ID, lesson/assessment mode, task versions/seeds, position,
  timestamps and current state (planned/active/paused/completed/cancelled);
- attempt: session/task ID, request ID, submitted answer, result, hint depth,
  independent flag, validator version and timestamp;
- skill evidence: status unknown/learning/practicing/provisional/retained/
  review_due, links to evidence, last independent success and next review;
- reminder intent and delivery result using existing outbox conventions.

Task solutions and expected answers never appear in child API projections before
submission/authorized reveal. Parent views expose summary and evidence for the
authorized child; ordinary adult and guest have no access by default. An
identity change invalidates old sessions, links and queued messages; explicit
parent rebind is required. No automatic XP or family reward on replay.

Initial mastery policy (configurable and subject to pilot):
- unknown is distinct from zero; diagnostic samples select prerequisite probes;
- provisional after at least three independent correct non-duplicate items,
  covering two task forms and at least one transfer task;
- retained only after an additional independent success at least one day later;
- a missed review means due, not failed; contradictory evidence reopens practice;
- assisted successes can be celebrated but do not satisfy independent mastery.
- review intervals default 1, 3, 7, 14, 30 days; shorten after an independent
  error, increase after success, and cap overdue workload. Use deterministic
  scheduler inputs and version the policy.

Default proposed plan: 20 min, Mon–Fri, 12 weeks as a revision target; parent
chooses actual local time and days. Initial two or three sessions diagnose both
grades; plan adapts to gaps, not fixed week numbers. Typical 20 min: 3 min due
review, 4 min explanation/example, 8 min interactive practice, 3 min transfer,
2 min exit ticket. A child can pause, resume and skip optional tasks. Friday
offers a mixed low-stakes independent check. No late-work debt pileup.
Reminders are opt-in and private, at most one per recipient/session/window;
respect quiet hours, household timezone, DST, holidays, school conflicts,
disable/revocation, and expiration. No old reminder backlog on restart.

## 7. Tutor, voice and visuals

Start with deterministic curated explanations and progressive hints. Optional
LLM receives only the current objective, verified task, permitted hint level,
and minimal learning context; no household history, school credentials, device
access, unrestricted external search or general HA tools. Educational video
search is a separately scoped broker with topic-only queries (see section 11). Validate typed outputs and fail
back to curated content if unavailable, malformed or inconsistent. In learning
mode prefer a guiding question to giving the answer; a child may explicitly
reveal the solution, marking practice as assisted. Independent assessment mode
uses fixed task wording and no answer-revealing tutor until submission.

Voice is an optional explicitly configured provider: TTS(text, locale, voice)
and ASR(audio, locale) with bounded input/output, timeout and local-first policy.
RocketTTS is a candidate only; confirm actual endpoint/API and license before
implementation. Existing configured providers may be reused without granting
generic tools. Voice playback should be controllable; transcript visible and
correctable before grading. No background microphone or automatic recordings.
Do not retain raw recordings by default. No external child data transfer
without separate informed parent configuration.

Visuals: original responsive SVG/Canvas, KaTeX or equivalent packaged locally,
fraction bars, number line, ratio slider, equation balance, coordinate graphs,
angle and triangle drag controls, construction tools, matching/order/fill,
free input and step-by-step work. Each interactive visual has keyboard and
text alternatives. No generated illustration is trusted as an exact diagram.
Use restrained teen-friendly graphics, reduced-motion option, readable contrast
and low-bandwidth fallback. Never load third-party scripts/CDNs by default.

## 8. Motivation and parent experience

XP, levels, optional quests and progress map celebrate effort, corrections and
knowledge. XP is separate from skill evidence. No negative points for errors,
streak penalties, public rankings, compulsory rewards or device restrictions.
Any link to existing family Rewards is separately opt-in, capped and
idempotent. An optional family Tasks/Court bridge tracks explicitly assigned
attendance/completion commitments separately from academic performance.
Never penalize mistakes, low scores, requests for help or learning speed.
See section 11 for the missed-commitment review contract.

Parent dashboard shows last session, independent accuracy with denominators,
skills with evidence and uncertainty, due reviews, trend by skill and next
plan. Weekly digest goes only to subscribed authorized personal chats. No
grades/answers to family groups. Support child-friendly summary, feedback,
data export and owner-controlled retention/deletion, including deletion of
derived data. No telemetry.

## 9. Implementation and acceptance matrix

A1 specification is recorded; source mapping and review remain open. A2 and
A4 have a partial fractions-only domain implementation and focused tests;
A3/A5 are not complete. A5 now has an optional household adapter and first
card; native HA and full-repository acceptance remain pending.

| Stage | Deliverable | Acceptance gate |
|---|---|---|
| A1 | Design, source map, implementation conventions | Contract reviewed, scope/version decided, no runtime change |
| A2 | Pure math core, exercise schema, first templates | Exact arithmetic tests, invalid/hostile input bounded, deterministic generation, no dependencies or HA required |
| A3 | Grade 6–7 course pack | Reviewed source coverage, original EN lessons + UK glossary, prerequisites valid, each template checked for parameter ranges and answers |
| A4 | Enrollment, evidence, diagnostic and adaptive planner | Synthetic scenario tests, no guessed mastery, assisted/independent distinction, repeat/resume, deterministic review and plan |
| A5 | HA integration and learner/parent UI | Default off, current role authorization, versioned Store, native HA restart, frontend keyboard/mobile and browser end-to-end |
| A6 | Private Telegram and scheduler | No second poller, exact callback/recipient scope, dedup, quiet hours/DST, revocation, no group disclosure |
| A7 | Tutor and voice adapters | Explicit opt-in, bounded no-tools model, fallbacks, no grade override, no audio retention by default |
| A8 | Motivation, reporting, optional Tasks/Court bridge | Idempotent rewards, protected reports, separate reviewed attendance commitments |
| A5b | Telegram Mini App learner surface and scoped gateway (prioritized) | Verified initData/expiry/revocation, server grading, remote/mobile E2E, no HA admin exposure |
| A9 | Release and pilot | Exact-commit CI, privacy/package, unit/frontend/HA/upgrade gates, rollback, explicit owner consent for live test, child feedback and independent progress check |

### Verification checkpoint: rational validator

Implemented `academy/rational.py` and `tests/test_academy_rational.py`.
35 focused cases passed in an isolated Python 3.13.5 scratch tree without HA.
The GitHub blob hashes of both files match the locally tested files. Full
repository pytest, Ruff, CI, HA integration and packaging have not been run
for this increment. The parser accepts signed integers, decimal dot/comma,
and numerator/positive-denominator fractions; limits each digit component to
12 and total input to 80 characters. Mixed-number syntax, units, algebra,
generation and skill evidence remain pending. No runtime registration yet.

### Verification checkpoint: Fraction Lab (stage A2, first A3/A5 preview)

Added four versioned deterministic templates (read a fraction bar, equivalent
fractions, addition, fraction of a quantity), three levels, and a seven-task
lesson plan (four practice and three fresh exit questions). Learner task
projection excludes answer keys, solutions and hints. Exact rational grading
reuses the existing validator. The finite seed space can repeat parameters
across sessions; cross-session deduplication is not implemented.

The offline preview uses original responsive fraction bars, sliders, English
explanations, Ukrainian glossary, two hints per practice item, and an exit
check without hints or feedback until completion. The demo intentionally embeds
keys and has no persistence, account or trusted assessment; do not ship it as
the authenticated learner surface. Build from the repository root:

```sh
python -m tools.build_academy_preview /tmp/fractions.html --seed 19 --level 2
python -m pytest -q tests/test_academy_fractions.py
# Optional smoke test (requires Python Playwright and Chromium):
python -m tools.check_academy_preview /tmp/fractions.html --chromium /usr/bin/chromium
```

Evidence: 25 focused pytest cases passed in an isolated Python 3.13.5 scratch
tree, exercising 6,012 template/level/seed combinations and 300 lesson plans.
Two Chromium smoke scenarios (390px and 1024px) passed with the generated HTML
injected using set_content because file:// navigation was blocked by the
environment; HTTP requests were blocked. Checked keyboard slider interaction,
invalid input, assisted practice, hidden exit hints, deferred feedback, result
counts and restart. The five new source blob hashes match the tested files.
Full repository pytest, Ruff, CI, HA compatibility, package/release and actual
file navigation remain unverified. No live setup or private data touched.
Fractions subtraction, multiplication, division, mixed numbers, source mapping,
persistent session/evidence, provider and HA/Telegram integration remain open.

### Verification checkpoint: adaptive fractions domain (A2/A4 partial)

Implemented `academy/fraction_extensions.py`, `academy/adaptive.py` and
`tests/test_academy_adaptive.py`. The four original v1 templates and the
standalone HTML preview are unchanged. Eleven additional deterministic
templates cover subtraction, multiplication, division, mixed/improper numbers,
and transfer problems; the existing part-of-whole template remains available
but is not a separate tracked skill in this increment. The adaptive planner
uses 14 templates in six skills. Mixed-number form is explicitly graded,
with exact rational comparison and bounded input.

The pure per-binding engine has a versioned JSON event journal, deterministic
planning with prerequisite gates, pause/resume, hint/reveal tracking, exact
request replay and stale-task rejection. Independent answers affect skill
evidence; assisted answers do not establish mastery. Equivalent operands
and numeric duplicates are excluded across sessions. Provisional mastery
requires three unique independent correct items, two forms and a transfer
task. A fresh correct review on or after the next local calendar day confirms
retention. Review intervals are 1, 3, 7, 14, 30 days; independent errors reset
the streak, reduce level and schedule next-day review. Unknown accuracy is
null, not zero. The planner caps work at two due reviews and three focus
questions per session; this is not a daily session cap or actual clock-based
scheduling. Valid wrong practice answers advance with an explanation rather
than permitting retry within the same item.

`apply_and_save` stages state, awaits an injected atomic save callback and
returns the new state only on successful save; the caller must hold a
per-binding lock, provide trusted local dates and authorize the current member
revision. JSON reload rebuilds sessions and evidence from the journal. This
is not yet a registered HA Store adapter, durable live household installation,
authenticated endpoint or Telegram command. The journal is private and
contains submitted answers; do not expose it or parent projections to
learners. Replay depends on stable v1 rules; future policy/template changes
require a versioned replay implementation/migration. The finite template
pool and 20,000-event bound can eventually require fresh content or journal
compaction; no automatic eviction, cancellation, enrollment management or
data deletion is implemented in this increment.

Verification: 87 focused pytest cases passed in Python 3.13.5 isolated
scratch tree (35 existing rational cases, 25 existing Fraction Lab cases,
27 adaptive/extended cases). The extension tests exercise 5,418
template/level/seed combinations, including max seed. Scenarios cover
provisional and retained mastery, all review intervals, per-session review
cap, wrong review, assistance, invalid answer, delayed assessment feedback,
stale actions, identity revision, file roundtrip, async save failure and
idempotent replay. The three new source blobs match the locally tested files.
Command: `python -m pytest -q tests/test_academy*.py` (isolated scratch tree).
Full repository tests, Ruff, exact-commit CI, native HA, browser, packaging
and upgrade tests have not run for this increment. Full diagnostic baseline,
curriculum/source mapping, persistent HA adapter, frontend, actual scheduling,
role authorization and Telegram remain open.

### Verification checkpoint: Academy household adapter and card (A5 partial)

Academy is now registered as an optional, default-off household module in
Config Flow/Options, control center and the localized module labels. The
existing owner-controlled settings transaction enables it; a separate
parent/owner action explicitly enrolls each active child. The card type is
`custom:family-assistant-academy-card`. It is registered by the existing
frontend resource and can also be opened from Modules → Academy → daily use.
For an individual dashboard add the card in YAML, optionally setting
`entry_id` and `language: en` (or `uk`, `ru`).

The authenticated `family_assistant/academy` WebSocket endpoint accepts read,
enroll, start, answer, hint, reveal, pause and resume. It captures the existing
HA command scope and checks it before mutation, under the canonical Engine
transaction and after persistence. Child commands never accept a target
member ID; sibling, ordinary adult and guest access is denied. Parents can
select active child summaries, enroll, pause enrollment and explicitly rebind
a changed member revision, but cannot submit answers as the child. A fresh
enrollment epoch rejects stale actions. Rebinding starts a separate journal
and retains the old journal privately; disabling a module or enrollment
retains progress. Existing sessions resume after re-enabling the same member
revision. Enrollment conflicts are resolved by read-back, not by silently
repeating a stale edit.

The private `academy` bucket is added lazily to the existing household Store
via `Engine.system_update`, using its lock, backup barrier and persist-before-
publish behavior. No separate database, browser storage, scheduler, external
provider, or new HA entity is required. Day is derived server-side from the
household timezone. Lost learner responses retry the same operation ID and
original date, including after midnight. The child projection hides the
knowledge map during an active assessment and the report until completion;
no journal, raw answer keys or pending assessment solutions are returned.
Parent summaries and the card do not expose old-revision journals.

The integrated card has a visual fraction-bar exercise, text submission,
practice hints/reveal, pause/resume, progress, parent enrollment selection
and skill summaries. EN/UK/RU control labels are available; prompts, skill
labels and solution explanations remain English in this first slice.
The card is separate from the offline preview and does not contain the
preview answer keys. It rechecks access on refresh and fences responses
after configuration/user changes. This is an initial integrated practice
interface, not the full interactive theory course or a Telegram Mini App.

Verification: 105 focused Python cases passed in the isolated Python 3.13.5
scratch tree (87 previous Academy tests and 18 new household-boundary
tests); two Chromium scenarios at 390px and 1024px passed against a
synthetic WebSocket adapter. The browser test caught a disabled retry button;
it was corrected and both scenarios rerun. Verified role boundaries,
explicit enrollment, revocation, identity revision, local day, JSON
roundtrip, hidden active evidence, stale actions, replay, fraction bar,
hint, pause/resume, lost response retry, report and revoked-access display.
The five new locally checked source blobs were verified against the Git
tree. Run `python -m pytest -q tests/test_academy*.py` in the full repository
and `python -m tools.check_academy_card --chromium /usr/bin/chromium` for
the standalone card smoke test. A separate canonical Engine/Store contract
test is included for full-repository verification; it was not executed in
the scratch tree. The HA API file passed Python compilation, but native HA
WebSocket registration, live Store/backup/reload, full repository tests,
Ruff, exact-commit CI, panel integration and upgrade/packaging acceptance
remain unverified. No release or NAS changes made. Large-journal replay
performance, data deletion/retention policy, full localization, full grade
6–7 course, notifications and tutor/voice remain open.

### A6 checkpoint — Telegram transport and schedule

Private `/academy`, `/academy_start`, `/academy_answer TOKEN ANSWER`,
`/academy_schedule ID mon,tue,... HH:MM`, `/academy_skip ID YYYY-MM-DD`,
and `/academy_reports ID fri HH:MM` (or ID off) use the existing bot,
guarded Engine transaction and durable outbox. Inline hint/reveal/pause/resume
buttons and reply-to-message answers bind to the current task token. Group
commands are consumed without lesson data; ordinary model context does not
receive Academy quote text. Enrollment and current identity are rechecked
during delivery. Schedule reminders use household local time, expire after
30 minutes, skip DST gaps, and deduplicate by local day/ISO week; missed
windows do not create a backlog. The current weekly report is a seven-day
summary of completed missions and independent answers, not a full analytics
dashboard. Reminders/reports are opt-in and quiet-hour handling uses the
existing outbox. Delivery uncertain after transport begins is not retried
blindly by the existing Notifications engine.

Evidence: 120 focused Python cases passed in the isolated Python 3.13.5
scratch tree (105 previous + 15 Telegram cases); the two new domain/test blob
hashes match GitHub. Native manager/Engine/outbox wiring was added by
source inspection and is not yet executed with HA. Full CI, lint,
transport/restart smoke and exact native tests remain required. The text
interface is fallback, not the primary Mini App. No NAS deployment.

First vertical slice: one synthetic child, fraction diagnostic and interactive
fraction lesson, independent exit check, stored evidence, parent summary and
review due next day. Test on an isolated HA installation before expanding the
live household. Do not claim full course or production readiness for this slice.

## 10. Initial decisions requiring review before live activation

Actual school curriculum/textbook edition, child's English reading level,
actual days/time and maximum daily workload; existing HA version and private
bot installation; optional RocketTTS endpoint and supported locales; remote Mini App hostname/gateway configuration; consent for providers, video
sources, data retention, and any family Tasks/Court policy. The defaults above are proposed and can be changed without
hard-coding household data. Until then work uses synthetic fixtures only.

References within project: [vision](vision.md), [school](school.md),
[implementation status](implementation-status.md), [release](release.md),
[rollback](rollback.md). Existing online school records are not automatically
imported into tutor context.


## 11. Product clarification: living courses, travel, recovery and accountability

Owner direction: select a study program and have the teacher guide the child
through it inside Telegram. Interactive HTML lessons, adaptive agent questions
and parent reporting are central, not optional polish. Two primary goals:
continue a portion of the school curriculum independently during a month away
from home; refresh previously learned material when it has been forgotten.

### Course modes and planning

- Curriculum continuation: choose grade, subject, reviewed curriculum/version,
  start and end topics, date range and available days/minutes. New concepts
  require actual explanations, worked examples and practice, not just testing.
  Produce a feasible plan for a selected portion of the curriculum; do not
  promise a whole school year in one month. Report unmet objectives honestly.
- Knowledge recovery: diagnostic baseline, prerequisite-aware skill map,
  adaptive practice, transfer tasks and delayed independent rechecks.
- On-demand AI tutor: select a topic or ask a question; guide the learner back
  to a verified course skill and offer a short comprehension check.
- Course selection and parent plan preview are distinct from activation.
  Enrollments pin curriculum and policy versions. Plan dates, exceptions,
  travel pauses, catch-up choices, duration and actual attendance are separate
  from mastery. Propose changes when pace differs from plan; parents can review
  and adjust, without accumulating punitive backlog.

Recommended starting plans (configurable): recovery 15–25 min, continuation
30–45 min, on-demand flexible. A session has due review, explanation, optional
video, visual lab, guided practice, agent follow-ups and independent exit
check; fit total duration to the configured limit instead of forcing all
components every day. Provide break/shorten/resume and a non-video fallback.

### Live tutor and video discovery

The tutor orchestrates reviewed lesson blocks and can rephrase, ask why,
identify misconceptions, adjust language and difficulty, provide progressive
hints, and request extra evidence. It receives only scoped learning context;
the deterministic math engine is authoritative for objective answers.
Open explanations/proofs use a reviewed rubric, confidence/needs-review and
support parent review. Agent-generated follow-ups are unscored unless
instantiated and checked against an approved validator/template; never let
the model overwrite objective evidence, invoke family controls, or invent
mastery. English is the initial instruction language; Ukrainian support and
Russian fallback are configurable independently of the UI language.

Video discovery: separate topic-only search broker (e.g. YouTube Data API
when configured), rank Ukrainian/English first with Russian fallback, prefer
age-appropriate teacher channels, exact curriculum topic, language, duration,
captions and pedagogical quality. Store candidate IDs/metadata, review state
and fallback text. Explicitly approved trusted sources or parent-reviewed
items are eligible for child display; no automatic arbitrary links or
algorithmic feed, no search queries containing names, school account data,
grades or answers. Respect provider quota, unavailable/blocked videos,
copyright, embedding restrictions and parent opt-in. Use official links or
permitted embeds only, no downloading/rehosting. Do not treat video playback
or time spent as mastery; every video segment has original comprehension
questions, interactive practice and an independent transfer check. The
system still functions without YouTube.

### Parent dashboard and family accountability

Show course/grade/subject, planned vs completed objectives, calendar with
excused/missed/paused/completed states, independent accuracy with denominators,
skill evidence and delayed retention, mistakes and misconceptions, actual
time, next lesson, plan risk and weekly trend. Separate participation,
academic evidence and family points. Weekly summaries use authorized private
recipients only. Never publish a child's educational data to group chat.

Optional Tasks/Court integration: parents may explicitly assign a learning
commitment (e.g. complete a scheduled session by a stated deadline), with
visible terms, grace period, permitted skip/reschedule and a clear points
policy. Default off; no retroactive commitments or automatic negative points
for weak academic results. Missing a commitment is a separate evidence state,
not a knowledge score. If module/bot/network is unavailable, notification
delivery is uncertain, child is excused, or evidence is incomplete, mark
unverified/excused and do not propose a sanction. A missed commitment may
generate a parent-review proposal through existing authorized Tasks/Court
workflow; apply only a confirmed decision, with existing appeal/reversal,
caps and a stable obligation ID that prevents duplicates after restart,
replay or rescheduling. No general tutor access to Court/Tasks mutations.
No live policy enabled or points posted by this document.

### Revised implementation order and pilot

1. Finish the durable Telegram notification/schedule/reply integration and
   verify against native Engine/Store and the existing outbox.
2. Add course catalog, dated plans and full lesson state, then implement the
   reusable HTML learner surface and scoped Telegram Mini App gateway.
3. Deliver a complete end-to-end pilot for fractions: course selection,
   visual lesson inside Telegram, validated questions, adaptive tutor,
   reconnect/resume, private report and parent dashboard; exercise from
   outside the LAN on a test household.
4. Expand validated grade 6–7 curriculum, bilingual support, video broker,
   voice and varied interactive labs. Verify no-provider fallbacks.
5. Add full parent analytics and separately opt-in attendance/Court workflow;
   test outages, excused absences, duplicate/reversal behavior and access
   revocation before a household pilot.

These are revised requirements and proposed defaults, not implemented
features or a release. As of the preceding committed A5 checkpoint, the
Telegram Mini App, video discovery, course catalog, live tutor, complete
curriculum and Tasks/Court bridge are not implemented. No external services,
real student data, or live NAS configuration changed.
