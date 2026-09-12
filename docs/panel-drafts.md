# Resumable control-center drafts

The control center retains one unfinished family/profile form per signed-in HA
user and household in the current browser tab. This closes the gap between the
server-persisted wizard step and unsaved form contents: a reload can now offer
the form back without applying settings or creating a member.

The scope is deliberately limited to the family name/language/time zone and
member name/role/language/aliases/HA account ID/birth date/avatar/active fields.
Those fields can contain personal data. Provider options, tokens, Telegram
identifiers, invitation codes, recognition text and module workspaces never enter
the draft serializer. A field allowlist is applied on write; the bounded, versioned
JSON schema is validated again on read. Invalid records, future timestamps and
records older than 24 hours since the last edit are rejected and removed when read.

`sessionStorage` keeps drafts across reloads in the same tab and origin. It is
browser-managed storage, not encryption or an authorization boundary. Browsers
may preserve it during session recovery or copy it when duplicating a tab; the
server's current owner and revision checks remain mandatory. There is no cloud
sync or cross-device resume. Explicit discard is appropriate on shared devices.
When this panel observes an account switch, it clears the previous user's draft
keys; permission loss/read-only mode clears the current household's draft. Every
resume requires a successful fresh authorized projection before showing contents.

Editing captures the supported form automatically. **Keep for later** returns to
the overview, where **Resume draft** and **Discard draft** are explicit actions.
Another profile/family editor cannot overwrite that retained draft. Other module
workspaces can still be used. Ordinary navigation from a dirty form retains its
existing discard confirmation. A storage failure leaves edits in memory and
does not pretend that keeping or removing the draft succeeded.

An existing member draft pins the member revision. A family draft pins the
settings revision; a wizard draft also pins the onboarding revision and step 1.
A mismatch or removed member opens a read-only review, with the original text
available and an explicit discard action. The draft is never rebased silently.
A late resume response cannot replace a newer navigation or form.

Before a supported draft is submitted, its stored state becomes `submitted`.
If that marker cannot be written, no network mutation is started. Verified
readback clears the draft. A failed request retains the existing in-memory frozen
payload and operation ID for exact retry. If the panel is reloaded or reconnected
after an attempted save, the stored draft is review-only: the user checks current
family data and discards it before a new edit. The browser does not persist or
invent replayable commands, and a potentially accepted new-member creation cannot
be repeated automatically with a fresh operation ID. This conservative recovery
also applies when the server may have rejected the original attempt.

Verification on the isolated public branch:

- `tests/frontend-panel.test.js`: 49 passing, including schema/privacy bounds,
  reload/resume, wizard step conflict, missing/stale member, owner revocation,
  same-user reconnect, account/household isolation, storage faults, exact retry
  identity and delayed-resume navigation.
- `tests/browser/panel.spec.js`: 11 Chromium scenarios passing, including Russian
  mobile wizard resumption, Ukrainian dark stale-profile review/discard and
  English uncertain-creation recovery. Russian/Ukrainian screenshots were visually
  inspected; mobile overflow assertions passed.
- `tests/test_panel_settings.py tests/test_family.py`: 37 passing against the
  actual domain engine, including a stale retained member revision after Store
  reload and a revoked owner's retained creation request. Python imports were
  verified against this worktree.
- Full JS pretest/main suites: 189 + 516 passing. Public-tree privacy scanner,
  Ruff and runtime import/packaging validation passed (296 runtime files; no
  release was created). AGY Gemini 3.8 Flash supplied the initial bounded
  read-only design review and a second schema/conflict review with no findings;
  an intervening broader review timed out and is not counted as verification.

No Python runtime, HA API contract, provider connection or device behavior changes.
Fresh browser tests use fictional data. They do not establish new actual-HA,
household, Telegram or hardware acceptance. Deployment and release remain separate.
