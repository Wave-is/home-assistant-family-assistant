# Shared shopping assignments — bounded implementation

Current coordinating checkpoint: merged into the rc.7 candidate. Standalone
Python completed 6308 passes; combined acceptance passed 6440 Python, 793 Node
and 433 Chromium checks. Root's actual isolated HA2026.9.2 verified assignment,
filters, metadata preservation, another member's partial purchase, stale buyer
rejection and Store/reload/replay. The exact rc6→rc7 upgrade also passed.
These results supersede the earlier branch-local pending gates below. Exact-
commit CI, release and household operation remain separate steps.

Development branch: `codex/shopping-assignments`, based on rc.6 source
`5c189ba8f992dedf3ad5f30838adb63f403026d0`. This is not a release or household
deployment. Native HA, combined release CI and production acceptance belong to
the coordinating integration branch.

## Shared meaning / Общий список / Спільний список

- EN: Buyer means responsible buyer, not exclusive permission. The default list,
  notes and history stay shared. Any currently authorized family member may help
  mark an approved purchase. Assignment does not order goods or notify a shop.
- RU: Покупатель — ответственный за позицию, а не единственный исполнитель.
  Список, заметки и история остаются общими. Другой участник семьи может помочь
  и отметить одобренную покупку. Заказ в магазине не оформляется.
- UK: Покупець — відповідальний за позицію, а не єдиний виконавець. Список,
  примітки й історія залишаються спільними. Інший учасник родини може допомогти
  та відмітити схвалену покупку. Замовлення в магазині не оформлюється.

No private scope, hidden inventory, new approval policy, notification campaign,
automatic punishment, recurrence change or data migration is introduced.

## Commands

All names below are fictional examples; the recipient must resolve to an active
configured non-guest member. Existing aliases and conservative name inflections
remain supported. Quantities use the existing RU/UK/EN shopping quantity grammar.

| Action | RU | UK | EN |
| --- | --- | --- | --- |
| New assigned purchase | `поручи Саше купить 2 кг яблок` | `доручи Саші купити 2 кг яблук` | `ask Sasha to buy 2 kg apples` |
| Change buyer on existing item | `назначь покупателя S000001 Саша` | `зміни покупця S000001 Саша` | `change buyer S000001 to Sasha` |
| Clear buyer | `сними покупателя S000001` | `прибери покупця S000001` | `unassign buyer S000001` |
| Assigned to self | `мои покупки` | `мої покупки` | `my shopping` |
| Filter by buyer | `покупки Саша` | `покупки Саша` | `shopping for Sasha` |

Channel-independent slash forms: `/shopping` (whole family), `/shopping mine`,
`/shopping MEMBER`, `/assignbuy S000001 | MEMBER`, `/unassignbuy S000001`.
Filters are presentation only, not access restrictions; non-guests can still
read the shared family list. The card also offers Family list / Assigned to me /
No assigned buyer / named buyer, including its archive. Source or member changes
discard old filter controls. Existing buyer selection and named save review are
used for reassignment; the shared-data and helping-purchase wording is explicit.

Ordinary `buy ITEM` stays an unassigned shared item. Product wording such as
`buy food for birds` is not interpreted as a buyer assignment. Explicit task
wording (`assign Sasha task buy bread`, `/task Sasha | buy bread`) stays an
ordinary task. Assignment creation makes one S-record and no T-record.

## Persistence and permission contracts

Creation reuses `shopping.add`; reassignment/unassignment reuses full
`shopping.edit` with the current item revision and unchanged required metadata.
It never clones the item, resets purchased quantity, changes approval status,
or overwrites barcode/recurrence/merge provenance. The existing edit event names
the buyer field; purchase history names the actual helping actor.

The optional strict `buyer_revision` command field checks the chosen member
inside the Engine transaction. It is emitted by new Telegram/model/card
assignment requests, not stored on items or used as a visibility/purchase rule.
Old unpinned callers remain compatible. Clearing buyer sends null without a pin.
Existing pending/approved edit, child-proposal and guest restrictions remain.

Telegram freezes the complete interpretation before execution. Response-loss,
Store retry and restart reuse the original operation ID and payload; a reassign
retry cannot restore its old buyer after a later successful unassignment. A
changed payload for the same operation is rejected. An intervening purchase or
edit conflicts with an uncommitted stale item revision.

Transport deduplication does **not** mean identical text in a fresh Telegram
update is the same request. New requests retain existing add semantics. Use the
S-ID to change an existing purchase and the existing reviewed merge to resolve
duplicates. Automatic semantic duplicate detection, new-request disambiguation
continuations and concurrent name-based uniqueness are not implemented here.

## Independently proven name repair

The existing parent-only name-repair path now also proves one explicit purchase
assignment creation. A unique bounded one-edit correction must reproduce the
entire strict `shopping.add` payload: product, quantity, unit and buyer. The
command and actor-private spelling rule commit atomically; actual actor/member
revisions and the shopping module are checked again on execution/replay. No
member account or enrollment is changed. A learned spelling can then be reused
offline, subject to the existing active-rule and identity checks.

Changed product/quantity/extra fields or an unproved target require the existing
explicit proposal review; ambiguous/unknown names can be clarified. A model
cannot substitute task creation for explicit purchase-assignment wording.
The existing short-stem, multiword-typo, mixed-script and ambiguous-candidate
limits remain. Automatic name repair for S-ID buyer edits is not added; use an
exact configured name/alias or clarify. This is not general conversational memory
or arbitrary/multi-purchase prose parsing.

## Verification checkpoint

Actual parser/Engine/assistant regressions and synthetic TelegramManager tests
cover shared helping purchases, one-record replay, revisions, complete edit
preservation and strict name repair. Full Python reached **6307 passed, six skips,
23 subtests** with one public-tree assertion failing solely on a generated local
browser report. Moving that ignored report into the excluded test-results folder
made the public-tree scanner pass; no runtime change was required. The optional
clean-tree repeat was still running at this frozen checkpoint. The coordinating
branch must record its final combined full-suite evidence before release.

Focused Chromium passed **22 scenarios** on local synthetic fixtures: seven new
assignment/filter cases, three existing metadata-editor cases and twelve school
cases. These include RU/UK/EN controls, committed-response-loss retry, child
helping purchase and stale-generation/member/actor filter handlers. A separate
test-only fix now derives the exact approved local fixture origin from Playwright
configuration without relaxing external navigation blocking. The preceding full
Chromium run passed 429 of 433 scenarios; its four failures were precisely those
hardcoded-origin school tests, subsequently passed in the focused run. This is
not a claim of a clean final combined full-browser run.

All **189 Node pretests** and **602 main tests excluding source inventory** passed.
The two source-inventory assertions remain intentionally pending the coordinating
branch's final combined instrumented Chromium run and inventory regeneration.
Whole-tree Ruff, formatting, locale synchronization and public-tree privacy
checks passed. Native HA/reload acceptance, exact-commit CI and release gates
remain the coordinating branch's responsibility; no native acceptance is inferred
from synthetic Engine restart coverage.

AGY Gemini 3.8 Flash High completed a sandboxed, read-only public-code review.
Its full-edit hydration, module-specific repair replay and product-purpose
preposition concerns were checked against the actual code and covered with
regressions. Its example `buy ITEM for NAME` is intentionally not supported.
No real family data, bot, school portal or HA installation was accessed.

Rollback of a mistaken assignment is a fresh reviewed buyer edit/unassignment
using the item's current revision. This does not undo a recorded purchase;
existing lifecycle/merge/history contracts still apply. Do not edit Store files.
