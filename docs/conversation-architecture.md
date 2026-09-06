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

Model requests contain only the current input, bounded quoted text, receipt-backed
object references, a role-filtered data projection, language and current time.
They do not include HA/TG identities, credentials, audit logs or wake-up nonces.
Quotes, task titles and external snippets are explicitly untrusted. The system
never supplies a developer-owned server, account or bot.

Model mutations are simulated on a copy through the same authorized domain
handlers, then stored as expiring proposals. Confirmation belongs to the original
actor/role and revalidates record revisions in one transaction. Date expressions
must originate in the current request and are interpreted by the deterministic
calendar. Family settings, identities, arbitrary HA services, alarm answers and
physical device tests are absent from the model's command allowlist.

The [SearXNG JSON search API](https://docs.searxng.org/dev/search_api.html) receives
only a query grounded in the current message, never model-invented family context.
Result links are checked for literal and DNS-resolved internal addresses. Snippets
are terminal read-only evidence: the synthesis response cannot execute commands.
This version does not fetch articles; a later fetcher must validate and pin DNS
addresses at connection time, recheck redirects and enforce content-size limits.

The [standard HA conversation entity](https://developers.home-assistant.io/docs/core/entity/conversation/)
resolves `Context.user_id` for every turn. It uses actor/session-bound object
receipts instead of treating arbitrary chat history as trusted references.
Anonymous voice satellites do not inherit owner authority. Delegating to another
HA conversation agent and publishing a bounded HA LLM API remain separate gates.

Verified: malformed/oversized responses, auth failures, redirects, timeouts,
fallback/cooldown, private DNS results, search prompt injection, child role denial,
proposal expiry/concurrent edits, storage faults, original identity revocation,
and nonblocking ping. Real HA smoke uses real Config/Options Flow, conversation
entity, Store, Telegram manager and callbacks with synthetic transport providers.
No live family data or real bot/provider is used by CI. Real-model language-quality
evaluation and production acceptance are still required before release.
