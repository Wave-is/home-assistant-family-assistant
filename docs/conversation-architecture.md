# Conversation boundary and verification

The deterministic router remains the first path. Unrecognized addressed Telegram
messages are saved before advancing the update offset; a separate worker performs
inference. The worker rechecks the original Telegram identity, role and group,
and a five-minute expiry. It cannot stall polling or alarm callbacks. A request
that cannot be persisted does not advance. Replies use the durable outbox.

The [Ollama chat API](https://docs.ollama.com/api/chat) is used without streaming,
with [structured JSON output](https://docs.ollama.com/capabilities/structured-outputs).
Output is independently validated, including unknown keys, finite values, action
allowlists and sizes. Ollama's response format is not treated as authorization.
The configured fallback is independent and failures have a short cooldown. The
[model listing endpoint](https://docs.ollama.com/api/tags) is checked during setup.

Planning requests contain only the current input, receipt-backed object references,
a role-filtered data projection, language and current time. Raw quoted text is
withheld from the planner. When an ordinary reply needs it, a separate terminal
answer-only pass receives the current message and bounded quote, without the
family database or command schema. An injected command from that pass is rejected.
They do not include HA/TG identities, credentials, audit logs or wake-up nonces.
Quotes, task titles and external snippets are explicitly untrusted. The system
never supplies a developer-owned server, account or bot.

Model mutations are simulated on a copy through the same authorized domain
handlers, then stored as expiring proposals. Confirmation belongs to the original
actor/role and revalidates record revisions in one transaction. Date expressions
must originate in the current request and are interpreted by the deterministic
calendar. Family settings, identities, arbitrary HA services, alarm answers and
physical device tests are absent from the model's command allowlist.

Wire plans use `kind: commands` with an `operations` array, converted to the
unchanged internal `commands` format before validation/persistence. Every response
kind has its own exact schema branch. New alarm days use a literal source phrase;
the per-request grammar offers recognized phrases and the server computes Monday=0
indices. Clock-only edits may retain an existing schedule's days, but model-supplied
numeric days cannot create or change a schedule. Calendar/UI domain commands remain
unchanged. The model sees the actual shopping `purchased` field, not an invented
`purchased_quantity` property.

The [SearXNG JSON search API](https://docs.searxng.org/dev/search_api.html) receives
only a query grounded in the current message, never model-invented family context.
Result links are checked for literal and DNS-resolved internal addresses. Snippets
are terminal read-only evidence: the synthesis response cannot execute commands.
This search path does not fetch articles. Separate off-default, explicitly
reviewed [article reading](articles.md) pins DNS at connection time, rechecks
redirects and enforces content-size limits without sending family context.

The [standard HA conversation entity](https://developers.home-assistant.io/docs/core/entity/conversation/)
resolves `Context.user_id` for every turn. It uses actor/session-bound object
receipts instead of treating arbitrary chat history as trusted references.
Anonymous voice satellites do not inherit owner authority. The registered
[HA LLM API](https://developers.home-assistant.io/docs/core/llm/) offers only
`ReadFamily` and `PrepareFamilyPlan`: the latter cannot confirm its own proposal.
HA 2026.8.2 does not supply the original user prompt in LLMContext, so a tool's
`request` is explicitly untrusted and cannot silently authorize a mutation.
Every tool call independently validates its schema and current HA identity.
Delegating the family's bot to another HA conversation agent is still pending.

Explicit `/learn source | canonical` rules are private to the teaching actor.
They map an exact normalized phrase to a supported command, never Python,
regular expressions or model-generated actions. Authorization is checked both
while teaching on a non-mutating copy and on every use. Dates and reply targets
are resolved anew; fixed record IDs and absolute dates are not reusable rules.
Ordinary model confirmations do not silently create learned phrases. The
authenticated dashboard conversation card uses the same router and proposal
boundary, with actor/session-bound references and no invented owner identity.

Verified: malformed/oversized responses, auth failures, redirects, timeouts,
fallback/cooldown, private DNS results, search prompt injection, child role denial,
proposal expiry/concurrent edits, storage faults, original identity revocation,
and nonblocking ping. Real HA smoke uses real Config/Options Flow, conversation
entity, Store, Telegram manager and callbacks with synthetic transport providers.
No live family data or real bot/provider is used by CI. Real-model language-quality
evaluation and production acceptance are still required before stable release.
An opt-in [synthetic-only live evaluator](model-evaluation.md) exercises the
real model adapter, plan envelope, deadline materialization and domain guards.
