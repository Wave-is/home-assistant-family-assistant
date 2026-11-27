# Family Academy — Codex implementation and NAS handoff

## Status / stop conditions

This branch is a development candidate, NOT a production release. Do not merge,
publish, overwrite the live integration or enable the public endpoint/Court
until the following exact-commit gates pass. The owner requested an installable
home teacher and this is the starting code, not an assertion of full acceptance.
Read AGENTS.md, docs/vision.md, docs/academy.md, docs/implementation-status.md,
docs/release.md, docs/rollback.md and the private operations project's AGENTS.md.

Existing tested evidence: 120 focused isolated Python cases before final
course additions; 45 draft lessons, 194 answer formats, 90 language-specific
diagram entries checked, matching catalog blob. New test files
test_academy_courses.py and test_academy_mini_auth.py have not been run here.
No native HA, Telegram, final branch CI or NAS acceptance completed.
Do not mark missing gates passed. Treat review of all source modifications as
required, especially authentication, token expiry, identity change, provider
privacy, persistence, packaging and Court.
 
## Checkout and verify

In a clean working directory, not the running NAS integration:

```sh
git clone https://github.com/Wave-is/home-assistant-family-assistant.git
cd home-assistant-family-assistant
git switch codex/family-academy
git status --short
git rev-parse HEAD
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
python tools/check_public_tree.py
python tools/sync_locales.py --check
python -m compileall -q custom_components
npm ci
npm test
npx playwright install --with-deps chromium
npm run test:browser
```

The branch may have style/contract failures from the development iterations.
Fix them in branch commits, never by weakening tests. Run the same native HA
containers and upgrade/restore gates defined in .github/workflows/checks.yml;
match the NAS Core version and the supported matrix. Verify the new Academy
API, Mini App HTTP route, course card, Telegram manager/outbox and Court
against real HA, not only mocked WS. Review tools/build_release.py to ensure
JSON, HTML, CSS and JS are included; build an exact candidate archive only
after passing the release gates. Use a separate worktree and test household.
The existing build/upgrade scripts and version scheme are authoritative.

## Native acceptance matrix (must implement/run additional tests)

- HA: default-off upgrade, old household storage, enrollment/rebind/revoke,
  parents vs child vs sibling/guest, owner settings, full course CRUD,
  HA WebSocket identity guard, cancelled and failed Store saves, backup/reload.
- Telegram: no second poller; group commands and replies never leak content;
  private callback tokens, same update replay, stale question rejection;
  outbox sent/failed/uncertain/restart/dedup; bot replacement, DST, quiet hours.
  Ensure existing task/poll/conversation routes still function.
- Mini App: test genuine signed Telegram initData from a private bot; invalid
  signature, duplicate fields, expiry, replay across restart, wrong bot or
  household, stale enrollment/module/role, wrong Host/Origin, oversized body,
  unknown path, token expiry, retry after lost response, process restart and
  reopening app. Verify no raw answer key, provider secret, private household
  data or generic HA API exposed to child; inspect HTTP/logging/redaction.
- Browser: genuine Telegram Android/iOS/Desktop; mobile layouts, keyboard,
  accessible diagrams, no overflow, network failure/retry, resume, independent
  check no hint leak, parent selection and plan preview. Run outside LAN.
- Course: check every answer and diagram pedagogically, map exact Ukrainian
  school model program/textbook. Fixed bank is a draft revision pack. Extend
  parametrized independent questions beyond fractions, adaptive recovery,
  new-material teaching depth, algebra steps and geometry proofs. Record
  first independent score separately from assisted/repeated exercises.
- Provider: no external fallback from local tutor, no generic HA tools, output
  validation, provider changes/revocation, quota/timeout, topic-only YouTube,
  allowed channels and actual suitability, verify language/duration/captions.
  No video viewing counted as learning. RocketTTS needs actual API/voice
  contract and adapter; current browser speech synthesis is only a fallback.
- Dashboard: actual progress vs dated plan, week counts, review dates, current
  knowledge evidence; expand actual active time/analytics, complete
  EN/UK/RU UI localization, and unify adaptive evidence where appropriate.
- Court: explicit prospective commitment, default off, grace days, parent
  review, sent notice and identity epoch, unavailable server/network or
  excused absence never penalized; caps, repeated review, rescheduling/rebind,
  reversal/appeal and no academic-score punishment. Add explicit tests before
  enabling this option.
- Privacy: implement/verify retention and owner-controlled deletion, bounded
  journal growth, migration and diagnostics/public-tree scans. Never commit
  live family data, Telegram token, key, domain or device identifiers.

## Isolated installation, then owner-authorized pilot

1. Identify actual NAS topology (HA OS, container or VM), config directory,
   installed version, existing private operations instructions and backup
   mechanism. Do not assume the paths, hostnames or credentials.
2. Back up HA configuration and canonical Family Assistant Store; record
   current package version and verify a restore in a separate test instance.
3. Install exact checked candidate in test HA via the repository release
   process. Do not run two polling instances against the production bot.
   Use a separate synthetic household and test bot or explicitly stop the
   original poller during authorized channel testing.
4. Family Assistant → Modules → Academy: enable module, enroll a synthetic
   learner, select a course/topic/date range, preview dates, explicitly approve
   draft material and assign. Keep provider/remote/Court settings disabled.
5. Add card if needed:
 
```yaml
type: custom:family-assistant-academy-course-card
language: en
```

For the earlier fractions adaptive card:
```yaml
type: custom:family-assistant-academy-card
language: en
```

6. Bind the test Telegram account with the existing enrollment flow. Check
   /academy and private reminders/reports; enable a plan and test resume.
7. Only after security acceptance, configure an owner-approved dedicated HTTPS
   origin in Academy settings and a TLS reverse proxy. On that origin route
   ONLY the exact path family /api/family_assistant/academy/mini/ to the private
   HA upstream. All other paths must return 404. No generic /api, /auth,
   /api/websocket, HA frontend or Supervisor routes. Preserve original Host,
   HTTPS scheme through the approved proxy configuration; trust only the
   actual proxy IP in HA. Limit body size, requests and connection timeouts,
   do not log request bodies, query secrets or session headers. No public port
   forwarding of HA itself. Example sketch (adapt to actual proxy and TLS):
```nginx
location ^~ /api/family_assistant/academy/mini/ {
    client_max_body_size 16k;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_pass http://HA_PRIVATE_UPSTREAM;
}
location / { return 404; }
```
   Verify the app loads only at approved host. Telegram initData is exchanged
   once; after HA restart reopen the Mini App to obtain a new signed launch.
   Persisted progress is read from Store. No raw Telegram or HA credentials
   in browser or reverse-proxy URL.
8. Optional local Ollama tutor: configure direct local IP provider in existing
   Family Assistant AI settings, owner enables Academy tutor separately.
   If unreachable, use deterministic lesson explanation. Optional YouTube
   Data API key and reviewed channel IDs are configured only by owner; restrict
   key and quotas. No child-specific searches. Verify external data consent.
9. Test outside the home network, including a synthetic week of lessons and
   report. Only after all gates and explicit approval, perform a backed-up
   production pilot; leave Academy Court opt-in off until separately approved.
10. Rollback: turn off Academy/remote proxy immediately if unsafe; restore
    checked baseline integration and verified Store backup per docs/rollback.md.
    Never silently discard newer learning records; export/reconcile as needed.
    Preserve working legacy family bot and configuration.

## Codex assignment

Complete the missing acceptance gates and any features described above;
fix issues, update docs/implementation-status.md with exact test evidence,
commit changes to codex/family-academy. Produce an exact-version candidate ZIP
and a deployment report containing commit SHA, test commands/results, changes,
remaining limitations, NAS install/rollback plan and a go/no-go decision.
Do not publish a release or modify production without owner authorization.
