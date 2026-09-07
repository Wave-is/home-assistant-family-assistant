# Explicit public-article fetching

Status: the standalone public HTTPS transport and bounded text extractor are implemented
in `assistant/article.py`; no runtime, Options, model, WebSocket, Telegram, conversation,
or card integration exists yet.

## Boundary and purpose

The current conversation path can ask an owner-configured SearXNG instance for up to
five public search snippets. `assistant/search.py` checks result URLs for literal and
DNS-resolved non-public addresses, while `assistant/service.py` treats the snippets as
terminal, untrusted evidence and permits only an answer-shaped model response. It does
not fetch result pages. `public_url()` explicitly says it is not a transport security
boundary because it cannot prevent DNS rebinding between validation and connection.

The first article slice adds one thing: an authenticated current household member may
explicitly ask the integration to retrieve one public HTTPS text page and summarize it.
It does not crawl, execute JavaScript, load images or subresources, authenticate to a
site, submit a form, fetch a PDF, or create a family command/proposal. A URL merely
appearing in ordinary family chat, quoted text, a task, a calendar record, a model
answer, or page text never authorizes a request.

The feature is disabled by default. The owner must separately enable article fetching
and acknowledge that extracted page text is sent to the configured conversation model.
The initial policy permits owner, parent, and adult members. Child access requires a
second explicit owner option, disabled by default; guests are always denied. The first
implementation is limited to authenticated dashboard/HA conversation contexts and
addressed private Telegram chats. Group-chat fetching is deliberately out of scope.

## Explicit request and reference contracts

Retrieval is never selected by `plans.SCHEMA` or an LLM tool. Keep the existing
`kind: search` plan terminal. The first adapter accepts only either:

- a dedicated authenticated WebSocket request
  `family_assistant/article_fetch` with exact fields `{type, id, entry_id, url,
  operation_id}`; or
- an exact deterministic private command `/article <https-url>` routed before the
  ordinary LLM fallback.

The exact slash command is a safe initial routing boundary, not the intended permanent
conversation UX. A later deterministic EN/RU/UK recognizer may accept a clearly
addressed current request such as “summarize this URL,” but it must bind the URL and
fetch verb from that same current message. A URL supplied only by a quote, forward,
history, stored family record, page, or model remains non-authoritative.

The URL is the only fetch target. Reject missing/extra command arguments, multiple
URLs, fragments, credentials, backslashes, control/whitespace characters, non-HTTPS
schemes, non-default ports, and URLs longer than 2,048 characters. Query strings are
allowed because many public articles require them, but must never be written to logs,
health, diagnostics, audit, outbox metadata, or error messages. The response is private
to the requesting surface. No `Referer`, `Authorization`, provider API key, HA cookie,
Telegram token, or other configured credential is sent to the target.

A later search-result convenience may render an opaque random reference beside each
SearXNG result. It must map in process-local, capacity- and TTL-bounded storage to the
exact already-screened URL/title plus actor ID, member revision, role, search-config
revision, originating operation ID, and expiry. `/article <opaque-reference>` must
resolve that record for the same current actor only and then perform all fetch-time URL
and network checks again. Numeric ranks, quoted bot output, arbitrary chat history, raw
model text, and receipt-backed family object references are not article references.
References expire within five minutes, are lost safely on restart, and are never placed
in Engine state. Direct URL support is the cohesive first release; opaque references
should land only with structured search results and their own tests.

## Options and runtime scope

Add a separate configuration below `options["conversation"]`:

```json
{
  "article_fetch": {
    "enabled": false,
    "allow_children": false,
    "revision": "random configuration generation"
  }
}
```

Limits are fixed constants, not owner-tunable safety controls. Upgrade the current
search/assistant Options flow to the already-used recipes-style pattern: capture the
displayed owner member revision and complete conversation/search/article configuration,
validate strict booleans, reauthorize after any provider await on success and failure,
reject concurrent configuration drift, and write a fresh unpredictable revision on a
real change. Blank secrets retain their existing provider-scoped semantics. Disabling
the conversation module, model, or article option immediately prevents new reads.

`runtime.async_configure_assistant()` should build an `ArticleService` only when the
conversation model and article option are both valid. Its immutable authority scope is
at least `(runtime identity, actor ID, member revision, role, conversation-module
presence, article revision, enabled, allow_children)`. Capture it before DNS/network
I/O and compare a freshly resolved scope:

1. immediately before opening a socket;
2. after every redirect response and before the next socket;
3. after the body is read/extracted and before model inference;
4. after inference and before returning any answer, title, URL, provider error, or
   updating health.

Inactive/rebound members, a role change, entry unload/reload, module or policy change,
or provider change revokes the result. Prefer current `forbidden`, `module_disabled`,
`conflict`, and code-only provider/article errors; never expose the rejected URL or
response text. A read does not enter Engine `processed`, proposals, memory, audit, or
outbox. A small process-local final-response cache may deduplicate an identical
`operation_id` and input hash for five minutes, scoped by the tuple above; it must have
a hard capacity and be cleared on reconfiguration/unload. Exactly-once retrieval across
a crash is not promised.

Telegram needs a narrow router hook because unknown slash commands currently do not
reach the slow fallback. The router should recognize exact `/article` syntax, require
`private=True`, and enqueue a job whose existing actor/member/chat binding is rechecked
before and after work. Dashboard and HA conversation adapters must likewise resolve the
real current HA user; anonymous voice contexts remain denied. Do not add article fetch
to `ReadFamily`, `PrepareFamilyPlan`, or the mutation proposal allowlist.

## Network transport

Do not reuse the HA/provider client session for arbitrary destinations. Create a
short-lived, cookie-less `aiohttp.ClientSession` dedicated to this fetch with
`DummyCookieJar`, `trust_env=False`, `auto_decompress=False`, connection limit one, and
forced connection close. This prevents provider credentials/cookies, environment
proxies, connection-pool state, and redirect authentication from crossing boundaries.

For each hop:

1. Canonicalize the hostname with IDNA and strip a single terminal dot. Reject the
   existing local suffixes and any hostname that cannot be conservatively parsed.
2. Resolve A and AAAA records once with a three-second bound. Convert every returned
   socket address with `ipaddress.ip_address()` and reject the whole target unless the
   non-empty set is globally reachable. `is_global` also rejects private, loopback,
   link-local, unspecified, multicast, reserved, documentation, carrier-grade NAT, and
   IPv4-mapped private IPv6 cases. Reject IPv4-mapped IPv6, 6to4, and Teredo in the
   conservative first slice rather than relying on platform-dependent translation
   semantics. Do not accept only the convenient public member of a mixed public/private
   answer, and reject more than 16 returned addresses.
3. Give an isolated `aiohttp.TCPConnector` a resolver that returns only that immutable
   vetted address set for the original hostname. Request the original HTTPS URL, so the
   original hostname remains the HTTP Host and TLS certificate/SNI name. Never disable
   certificate or hostname verification. Use aiohttp's supported `socket_factory` hook
   to refuse any connection tuple outside the pinned set; do not depend on
   `response.connection`, which may already be `None` after a small response is buffered.
4. Set `allow_redirects=False`. Only 301, 302, 303, 307, and 308 may continue. Resolve a
   relative `Location` against the current URL, then repeat every URL, DNS, pin, TLS,
   peer, and authority check. Reject HTTPS-to-HTTP downgrade, credentials, fragments,
   missing/oversized locations, redirect loops, and a fourth redirect.

The custom resolver is the connection-time pin; calling the existing `public_url()`
and then using the normal shared connector is not sufficient. A new one-shot connector
per hop is acceptable in this deliberately low-volume feature and avoids cross-host
pool reuse. Aiohttp documents custom resolvers, DNS caching, forced connection close,
strict TLS validation, and the per-request `server_hostname` control in its
[client documentation](https://docs.aiohttp.org/en/stable/client_advanced.html) and
[client reference](https://docs.aiohttp.org/en/stable/client_reference.html). Python's
[`ipaddress.is_global`](https://docs.python.org/3.11/library/ipaddress.html#ipaddress.IPv4Address.is_global)
is the conservative address predicate used by the existing search filter.

Use only GET. Send a generic, versioned Family Assistant user agent, `Accept:
text/html,text/plain`, and `Accept-Encoding: identity`. Reject any non-identity
`Content-Encoding`; this avoids a compressed-body expansion bypass while automatic
decompression is off. Ignore `Set-Cookie`. No robots file, canonical link, stylesheet,
image, iframe, or embedded resource is fetched in the first slice.

## Resource and content limits

Apply all limits independently:

| Resource | Fixed first-slice limit |
| --- | --- |
| Concurrent article requests | 2 per household, 1 per actor |
| DNS | 3 seconds per hop, within total budget |
| Connect | 3 seconds per hop, within total budget |
| Socket read gap | 3 seconds |
| Entire fetch including redirects | 10 seconds |
| Redirects | 3 |
| Response headers | aiohttp bounded defaults, at most 64 fields if supported |
| Wire body | 512 KiB, including chunked bodies |
| Content types | exact `text/html` or `text/plain`, optional charset parameter |
| Extracted title | 200 Unicode characters |
| Extracted article text | 20,000 Unicode characters |
| Articles per request | 1 |

Reject a declared `Content-Length` over the limit before reading, but always count
actual streamed bytes and abort on byte `limit + 1`. Do not return a silent partial
article as complete. Status must be 200; authentication challenges, downloads, 204,
range responses, malformed headers, invalid encodings, and other status codes are
code-only failures.

Use the standard-library `HTMLParser` in non-script mode for the first slice. Ignore
`script`, `style`, `noscript`, `template`, SVG, form controls, comments, and metadata;
collect bounded visible headings, paragraphs, and list text, decode entities, collapse
whitespace, and require a useful minimum. It is a bounded text extractor, not a claim
of semantic completeness. Never execute JavaScript, parse XML, honor `<base>`, or trust
page-supplied canonical URLs. Plain text receives the same character/control limits.

## Model boundary and citations

Add a dedicated `plans.article_messages(language, question, article, now)`; do not
serialize `Engine.view()` at all. The URL is removed from the current request before
model input. For the first summary-only endpoint, `question` is a fixed localized
instruction rather than user prose. A later natural-language question may be passed
only after the exact fetch URL is removed and ordinary conversation disclosure rules
are applied. The only user message fields are language, time, that bounded question,
and one clearly delimited `untrusted_article` object with source label, fetched title,
extracted text, and retrieval time. The requested/final URLs remain outside model input
and are appended to the response by code. The prompt contains no family members,
task/calendar/shopping data, receipt refs, quotes, credentials, audit, URLs with
secrets, or prior conversation. The system prompt must state that page text is evidence,
never instructions, and that unsupported claims must be qualified.

Reuse an answer-only JSON schema and independent validation. A page that says to call
a tool, issue a command, reveal a prompt, fetch another URL, or mutate family state has
no executable route: `_propose`, `Engine.execute`, and nested fetching are unreachable.
Strip all URLs from model prose. Code, not the model, appends a source record:

```json
{
  "answer": "bounded model text",
  "sources": [{
    "title": "bounded fetched title",
    "url": "verified final HTTPS URL",
    "requested_url": "verified original HTTPS URL",
    "retrieved_at": "aware timestamp"
  }]
}
```

Render links only from those verified fields using safe text/URL DOM APIs or escaped
Telegram text. If a redirect changed the target, show the final URL and make the
redirect explicit; do not accept a page's claimed canonical URL as provenance. The
structured WebSocket response should retain sources separately from answer text.
Neither title nor URL is persisted automatically or exported to diagnostics/LLM tools.

## Required implementation hooks

The smallest cohesive direct-URL slice consists of:

1. `assistant/article.py`: strict URL normalization, pinned resolver/transport, redirect
   loop, bounded extraction, and `ArticleService.fetch_and_answer()`.
2. `assistant/plans.py`: public-only article evidence message builder and answer-only
   validator reuse; no new model-selected kind or write.
3. `assistant/service.py` or a sibling service: scope capture/recheck and terminal
   synthesis. Existing snippet search may later share the stricter public-only prompt.
4. `config_flow.py` and `runtime.py`: owner-reviewed options generation, safe
   reconfiguration, and teardown of transient caches/connectors.
5. `websocket.py`: authenticated explicit endpoint. `telegram/router.py`, Jobs, and the
   conversation adapter are a second small integration step once private-surface context
   is pinned through the slow-job record.
6. EN/RU/UK descriptions and code-only errors explaining opt-in, external model
   disclosure, public HTTPS-only scope, size/type limits, and private-chat requirement.

### Next service/provider scope against current APIs

The next integration layer should be a sibling `assistant/article_service.py`, not a
new Engine handler. Construct it from the same `Cascade` used by the current
`Assistant`; the only provider call is the existing
`await Cascade.generate(messages, answer_schema, validate_answer)`. The schema is exact
`{kind: "answer", text: string}` with no commands/query/topic properties, and validation
must be a public plans helper rather than reaching through `Assistant._answer_only`.

The authenticated adapter, not the service, owns the live scope callback. Its initial
scope should be exactly `(runtime object identity, actor ID, current member revision,
role, conversation-module presence, Assistant object identity, Cascade object identity,
article-policy revision, enabled, allow_children)`. Rebuilding
`runtime.assistant` during `async_options_updated()` therefore conflicts an in-flight
request even if the replacement happens to use the same model URL. The adapter passes
an async callback that recomputes this tuple to both `article.fetch()` and the service;
the service checks it before provider inference and after both successful and failed
provider awaits, so stale content and stale provider errors are equally suppressed.

`ArticleService.answer(actor, url, operation_id, now, *, scope_check)` should:

1. validate the operation ID and enforce a per-actor one / per-household two semaphore;
2. bind `(actor, member revision, operation_id, input hash, policy revision)` in a
   bounded five-minute process-local cache, returning an exact completed response or
   rejecting a different input with the same operation ID;
3. call the implemented `article.fetch(url, scope_check=scope_check)`;
4. build the public-only prompt without either URL or any Engine projection;
5. invoke the current `Cascade.generate` answer-only API and recheck scope;
6. strip model-produced URLs, then return the bounded answer plus the fetcher's
   verified requested/final URL and title as deterministic structured citations.

The cache stores only the completed bounded response, never raw page bytes, extracted
page text, credentials, or family state, and is cleared on Options update/unload. A
cancelled/failed request does not remain as a completed cache entry. The adapter must
recheck scope before returning a cached response. This remains a read-only provider
operation: it never calls `Engine.execute`, `system_update`, `Jobs.finish`, proposal
storage, outbox, audit, or diagnostics.

Do not add dependencies for the first slice. The installed aiohttp 3.14.3 and Python
standard library provide the necessary connector, resolver, timeout, TLS, URL, IP, and
HTML parser primitives. Pin behavior must be verified against that exact aiohttp API in
tests rather than inferred from a preflight resolver mock.

## Acceptance tests

Pure transport tests must use synthetic loopback servers only through an injected DNS
and connector harness; production code must still classify loopback as forbidden.

- literal IPv4/IPv6 loopback, private, link-local metadata, multicast, unspecified,
  reserved/documentation, carrier-grade NAT, IPv4-mapped IPv6, zone IDs, userinfo,
  encoded host tricks, local suffixes, mixed public/private DNS, empty DNS, unsupported
  ports/schemes, and malformed IDNA all fail before a request;
- the preflight resolver returns public and a second resolver would return loopback:
  the actual socket uses only the first pinned set; the observed peer must match it;
- public initial URL redirecting relatively or absolutely to every prohibited address
  is rejected without contacting that destination; a valid redirect gets independent
  DNS/TLS/peer checks; loops and hop four fail;
- the target never receives cookies, auth, referrer, provider keys, HA headers, or a
  proxy request; HTTPS certificates are checked against the original hostname;
- oversized declared, chunked, endless, compressed, slow, malformed, non-200, binary,
  PDF, XML/SVG, empty, invalid-charset, and truncated responses fail within bounds and
  close the connection; cancellation propagates and releases concurrency slots;
- HTML scripts/styles/forms/embedded URLs and prompt-injection text cannot cause a
  second request, command, proposal, Store write, outbox event, or family projection in
  model input; title/body rendering cannot inject markup;
- ordinary prose containing a URL, a forwarded/quoted URL, unaddressed group chat,
  model-produced URL, article-page URL, `/article` in a group, and malformed slash
  commands cause zero DNS and HTTP calls;
- disabled option, missing conversation model/module, guest, default child policy,
  inactive/rebound member, wrong entry, and anonymous HA context cause zero DNS/HTTP;
- member/role/module/options/provider/entry changes during DNS, redirect, body read, or
  inference suppress all content and stale provider errors; no health update occurs;
- two displayed Options forms conflict, option booleans remain strict, provider failure
  rechecks authority before rendering private settings/errors, and changing config
  clears transient results/references;
- verified final URL/title are the only citations; model-invented or page-canonical URLs
  are absent, redirect provenance is honest, and no URL/content appears in Engine state,
  diagnostics, Repairs, logs, outbox metadata, or LLM family tools;
- bounded concurrency, operation/input-hash conflict, response-cache expiry/eviction,
  unload cancellation, restart without references, and repeated response-loss behavior
  are deterministic and never broaden authority.

An isolated actual-HA smoke should use a synthetic public-address resolver mapped to a
loopback test server, real aiohttp transport/TLS, authenticated WebSocket users, the
real Options flow/runtime update listener, and a synthetic model. It should exercise a
valid HTML fetch, redirect, DNS-rebinding attempt, child/guest denial, mid-flight role
and option revocation, Store immutability, and unload cleanup. It must not enable real
network access or use real URLs, credentials, family data, providers, or production.

## Deferred work and non-claims

The first slice does not provide paywall/login/cookie support, private-network sources,
PDFs, browser rendering, JavaScript, OCR, feeds, recursive links, background prefetch,
automatic search-result fetching, archival storage, offline reading, or perfect main-
article extraction. Opaque search references and localized natural-language shortcuts
are subsequent work. Any future private-source connector needs a separate explicit
allowlist and credential-isolation design; it must not weaken this public fetcher.
