# Product URL watch safety contract

This increment hardens the existing URL-watch path. It does not replace the
Shopping card's observed purchase prices with scraped prices. Those are separate
records: Telegram `/watch`, `/watchlist` and the `price_watch` commands address
product URLs; the Shopping card records what a family actually paid.

## Upgrade and explicit review

All saved watches and their existing history are retained. Older watches without
an approving parent/member revision are **paused for review**, not automatically
assigned to the member whose ID happens to be `owner`. A change to that approving
member's revision, role or active state requires review again. This intentionally
includes identity/profile edits; it does not silently transfer consent.

In the Family panel, open Capabilities → Price history → Product URL watches. A parent
or owner can review the URL, check the explicit external-fetch consent box and
press **Save URL and allow fetching**. Saving an unchanged URL is an intentional
reapproval. The controls and explanations are available in English, Russian and
Ukrainian. Children, other adults, guests, disabled modules and migration-shadow
views have no approval form. An owner still controls the module switch.

The form sends the exact watch revision and approving member revision. Failed
saves retain the original URL, revisions and operation ID for an exact retry;
verified readback is required before showing success. Detached/stale forms do not
submit. This is a small review/edit surface, not a complete new watch-creation UI;
creation/removal remain available through the existing Telegram/API path.

Old URL userinfo is retained in Store for recovery but redacted from shared
family projections, including automatically derived names and history URLs.
Old arbitrary transport exception messages project as a stable unavailable code.
No provider error text or credentials are newly recorded.

## Deliberately narrower public transport

The worker reuses the article fetcher's URL validation, immutable DNS resolver,
socket peer checks and streamed response reader. This code reuse does not require
the conversation module or a model/search provider to be enabled.

- Only public **HTTPS on port 443** is supported. HTTP, credentials in URLs,
  fragments, custom ports, ambiguous/local hosts and non-public/translated IP
  addresses are rejected. Existing unsupported URLs remain saved; edit them to a
  supported public URL. No private endpoint is tried as a fallback.
- Each of at most three redirects is revalidated and pinned independently.
  Automatic redirect following is disabled. Mixed public/private DNS answers
  fail closed; DNS failures never authorize a second unrestricted resolution.
- DNS, redirects and the request share a ten-second total deadline. The shared
  reader caps the streamed body at **512 KiB**, before decoding/parsing. It does
  not decompress responses, use ambient proxies, persist cookies, send stored
  credentials or fetch embedded resources. HTTPS certificate checks remain on.
- Oversize pages report `response_too_large`; unsupported content/compression,
  invalid pages/URLs, timeouts and unavailable endpoints have stable codes.
  Sites requiring authentication, anti-bot interaction, compression or larger
  pages are not supported in this bounded implementation. No bypass is attempted.

Only bounded JSON-LD Product/ProductGroup offers and the existing availability
fallback are parsed. Prices must be finite, nonnegative, supported decimal text;
arbitrary characters are never stripped to invent a price. A literal zero offer
is valid. Price-drop comparisons use exact decimals and the same nonempty
observed currency. Different/unknown currencies do not create a price-drop
notification; no currency conversion is performed. Malformed JSON/offer types
produce a stable failed observation, not an exception that aborts other watches.

## Observation and lifecycle fences

The approved watch carries a durable policy generation and approving actor epoch.
Every request captures the exact URL, policy, watch revision and module epoch.
These are checked before and during transport, after transport, and inside the
atomic Store transaction. Module disable/re-enable cannot revive an earlier
request. Unrelated task changes do not invalidate a watch observation.

The worker writes through a guarded system observation transaction, not an
impersonated `owner` command. A failed Store write publishes neither observation
nor notification. Reapplying an already committed observation's old scope cannot
append history twice. The existing explicit parent `price_watch.record` command
remains a parent-authorized manual ingestion interface, not an external oracle.

Changing a URL preserves and attributes the old history, clears the current
product baseline, and never compares two different products. Reapproving a
previously revoked/legacy watch also establishes a fresh baseline without a
retroactive drop/availability alert. The existing last-30-observations history
limit is unchanged.

An enabled runtime owns one tracked background task and one real HA coroutine
timer. Start is idempotent; stop cancels/drains the task and rejects queued old
callbacks. Disabled modules own no worker/timer and make no merchant requests.
Unrelated/no-op Options saves retain the same worker and do not trigger an
immediate merchant fetch. Runtime replacement, unload, backup pause and shadow
isolation are checked; unload drains this worker before closing its Store writer.

## Truthful, revocable parent notices

Price/availability notices pin the exact approved source, module epoch, parent
recipient epochs/chat bindings, and successful observation sequence/time. The
dispatcher rechecks them after claiming and immediately before transport, without
fetching the merchant again. Removal, URL/policy/actor/recipient changes, module
disable, the next observation (including failure or a rebound), a future-dated
observation, or age of **60 minutes** makes an unsent old notice superseded.
Unstamped legacy notices are also superseded, not retrospectively authorized.

This intentionally favors fresh evidence over delayed catch-up: a quiet-hours or
offline notice can expire or be superseded even if the next price is unchanged.
There is no next-day replay of stale prices, no bulk backlog notification, and no
claim that all historical drops will be delivered. Current-parent private target
resolution and the standard uncertain-delivery policy still apply. A send with an
uncertain result is not blindly repeated. A request already handed to the
transport cannot be recalled.

## Verification scope

`tests/test_price_watch_hardening.py` uses the real Engine/Store/dispatcher and
synthetic transport to cover URL/policy/member/module/runtime revocation, stop,
backup, Store failure/replay, legacy review/history, redaction, decimal/currency
validation, redirect/DNS/size/deadline checks and dated-notice supersession.
Existing price/parser tests remain in the gate. The reused transport's own tests
exercise actual synthetic loopback TLS, pinned sockets and bounded streaming.

`tests/frontend-panel.test.js` and `tests/browser/price-watch.spec.js` exercise
the real panel controls, translations, explicit consent, role restrictions,
mobile layout, stale forms, exact retries and verified readback. The browser
fixture uses fictional records and the standard control-audit adapter.

`tests/ha_price_watch_smoke.py`, runnable as `ha_smoke.py --case price-watch`,
uses actual HA setup, authenticated WebSocket commands, General Options,
Store/reload and real shortened interval/HassJob dispatch, with only merchant
transport replaced. It counts repeated timer work, verifies the loop thread,
disable/re-enable, no-op Options retention, approving-member revocation and stop.
The initial and no-op-worker versions passed isolated HA2026.9.2; the final dated
notice/UI source requires the integration writer's final native/combined gates.
The branch's focused gate passed 221 Python tests, 98 panel Node tests and five
Chromium cases, with Ruff and the public-tree privacy check passing. This is not
a claim of a full combined-suite or released-build acceptance. The requested
bounded AGY review timed out without findings and is not counted as review evidence.
These tests do not establish merchant-specific compatibility or delivery to a
real household. No production watches, credentials or scores are changed here.
