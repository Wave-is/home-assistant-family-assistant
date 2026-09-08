# Optional technical reports

This is an owner-controlled diagnostic aid, not automatic code repair or a
reproducer for misunderstood natural-language commands. It is off by default.
No developer receives telemetry, messages or access to your home.

1. Open **Configure → Developer diagnostics** as the household owner.
2. Review the consent text and enable collection if wanted. Only subsequently
   queued Telegram model jobs are eligible. Successes, cancelled/stale jobs and
   deterministic commands are not collected. Dashboard/Assist, polling and
   delivery errors are outside this first collector.
3. In the **Health card**, choose **Review technical report**. The complete JSON
   is visible. Choose **Download reviewed JSON** only after checking it. The
   server checks your current identity and consent generation again; if the
   report changed, review a new copy instead of exporting unseen changes.
4. You decide whether to send the downloaded file to a developer. Sharing and
   GitHub issue creation are not automatic. Do not add private exports or logs.

The report contains the installed public version, fixed technical error codes,
whether a job had a quote/reference (booleans only), and bounded aggregate counts.
It excludes message/quote/answer text, names, member/device/chat/operation IDs,
timestamps, provider URLs/settings, hashes of private values and arbitrary health
details. Unknown error codes become `other`. Counts saturate at 999999; a bounded
overflow/saturation flag indicates incompleteness. Schema 1 currently has 36
possible aggregate identities, with a defensive storage ceiling of 64.

Disabling collection preserves existing counts and invalidates eligibility of
already-running jobs, even after re-enabling. Toggling is owner-only and uses an
exact generation-bound command: a lost response can retry the same committed
operation but cannot override a later opt-out. A damaged diagnostic record is
not overwritten; capture skips it so ordinary bot completion can continue.
Data lives in the integration's private HA Store, not its HACS code directory.

## Developer handoff and honest limits

A report narrows a technical investigation. For example, `provider_timeout`
with a quote does not establish that quote parsing is wrong, that a model is
unavailable now, or that every quoted message fails. Do not invent a semantic
test from these counters. Ask for a separately consented, fictionalized minimal
reproducer when necessary.

The development process is: inspect an opted-in report → reproduce using
synthetic inputs → add a failing regression test → review a minimal fix → run
privacy, unit, frontend and actual-HA checks → publish the exact tested release.
Household installation and migration remain separate, authorized operations.
The integration never launches a shell/cloud agent, sends household credentials,
downloads patches or installs LLM-generated code. An automated developer-side
patch proposal queue and semantic-feedback workflow remain future work.
