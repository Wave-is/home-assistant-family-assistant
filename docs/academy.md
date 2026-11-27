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
card/panel (child and parent views) and the existing private Telegram bot.
Use existing identity binding, command router, scheduler, outbox and current
role checks. Do not create a second Telegram polling process. The card is the
first full interactive surface. Telegram starts/resumes lessons, handles
simple exercises and sends opt-in private reminders. Do not depend on a
Telegram group, Telegram, or an external HTTPS endpoint for core learning.

An optional later Telegram Mini App reuses the same learner UI/API only after
a distinct security review: a trusted HTTPS origin reachable by the client,
server validation of Telegram initData signature and age, replay protection,
short-lived scoped sessions, current personal-chat member binding and
revocation. Never expose HA admin, access tokens, or the entire HA API to make
the Mini App work. Browser/HA access remains usable without it.

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
No unreviewed model-generated task enters a scored assessment.

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
access, external search or general HA tools. Validate typed outputs and fail
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
idempotent; do not use Tasks/Court penalties for learning.

Parent dashboard shows last session, independent accuracy with denominators,
skills with evidence and uncertainty, due reviews, trend by skill and next
plan. Weekly digest goes only to subscribed authorized personal chats. No
grades/answers to family groups. Support child-friendly summary, feedback,
data export and owner-controlled retention/deletion, including deletion of
derived data. No telemetry.

## 9. Implementation and acceptance matrix

A1 specification is recorded; source mapping and review remain open. A2 and
A4 have a partial fractions-only domain implementation and focused tests;
A3/A5 are not complete. Production acceptance gates remain pending.

| Stage | Deliverable | Acceptance gate |
|---|---|---|
| A1 | Design, source map, implementation conventions | Contract reviewed, scope/version decided, no runtime change |
| A2 | Pure math core, exercise schema, first templates | Exact arithmetic tests, invalid/hostile input bounded, deterministic generation, no dependencies or HA required |
| A3 | Grade 6–7 course pack | Reviewed source coverage, original EN lessons + UK glossary, prerequisites valid, each template checked for parameter ranges and answers |
| A4 | Enrollment, evidence, diagnostic and adaptive planner | Synthetic scenario tests, no guessed mastery, assisted/independent distinction, repeat/resume, deterministic review and plan |
| A5 | HA integration and learner/parent UI | Default off, current role authorization, versioned Store, native HA restart, frontend keyboard/mobile and browser end-to-end |
| A6 | Private Telegram and scheduler | No second poller, exact callback/recipient scope, dedup, quiet hours/DST, revocation, no group disclosure |
| A7 | Tutor and voice adapters | Explicit opt-in, bounded no-tools model, fallbacks, no grade override, no audio retention by default |
| A8 | Motivation, reporting, optional Mini App | Idempotent rewards, protected reports, verified Mini App authentication if enabled |
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

First vertical slice: one synthetic child, fraction diagnostic and interactive
fraction lesson, independent exit check, stored evidence, parent summary and
review due next day. Test on an isolated HA installation before expanding the
live household. Do not claim full course or production readiness for this slice.

## 10. Initial decisions requiring review before live activation

Actual school curriculum/textbook edition, child's English reading level,
actual days/time and maximum daily workload; existing HA version and private
bot installation; optional RocketTTS endpoint and supported locales; whether
remote Mini App access is necessary; consent for providers, data retention and
family rewards. The defaults above are proposed and can be changed without
hard-coding household data. Until then work uses synthetic fixtures only.

References within project: [vision](vision.md), [school](school.md),
[implementation status](implementation-status.md), [release](release.md),
[rollback](rollback.md). Existing online school records are not automatically
imported into tutor context.
