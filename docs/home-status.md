# Optional home status and energy readings

Development on `codex/household-status`, based on `5be3d80`. This increment is
not part of rc.7 and does not claim household or physical-device acceptance.
It replaces seven configuration declarations with explicit new bindings, not
an automatic import of old private configuration. Controls and forecasts remain
out of scope; the development declaration inventory is 17 replaced, nine missing
and three requiring explicit review.

## Setup and use

The module is disabled by default. The current family owner opens **Configure →
Network & Integrations → Home status**. No YAML, provider, history permission,
device command or background observer is required.

1. Add named groups if needed. Choose a short permanent key such as `room` or
   `utilities`: lowercase Latin letters, digits and underscores, beginning with
   a letter, at most 40 characters. A group's key cannot change in place.
2. Add one explicitly selected, registered HA entity per source. Choose an energy
   metric, named group or activity section; give it a label and visible roles.
   Activity requires explicitly selected HA states. The selector translates
   their labels while retaining the protocol value in parentheses.
3. Review and confirm each change. Saving finishes the native Options flow;
   reopen Configure to add another source. The same screens edit/remove existing
   sources. Move/remove a group's sources before removing that group.
4. Enable **Home status** in household/module settings. Add the namespaced
   `custom:family-assistant-home-status-card`, or open the module's daily view.
5. The card reads on opening and on **Read current status**. Ordinary idle family
   refreshes check only opaque access metadata, never source states. Access,
   identity or configuration changes clear previously displayed readings.

No-op confirmation preserves the exact Options object content, source order and
configuration revision. Cancelling changes no mappings. Other provider, school,
presence and family settings are preserved.

Private Telegram commands are `/home`, `/energy`, `/active` and `/status room`
(replace `room` with your configured group key, also shown in the card). Exact
English/Russian/Ukrainian home, energy and activity phrases are supported; there
is no guessed group matching. Group-chat requests return only an instruction to
use the private chat. Recognized malformed or unavailable commands never fall
through to a language-model repair.

Кратко: настройте группы и источники в **Настроить → Сеть и интеграции →
Состояние дома**, подтвердите привязки и отдельно включите модуль. Карточка
читает показания при открытии и по кнопке; команда `/status room` использует
ваш постоянный ключ. Состояние реле или режим отопления не доказывает работу
нагрузки. Время записи HA не является подтверждённым временем измерения.

Коротко: налаштуйте групи й джерела в **Налаштувати → Мережа та інтеграції →
Стан дому**, підтвердьте прив'язки й окремо увімкніть модуль. Картка читає
показники під час відкриття та за кнопкою; `/status room` використовує ваш
постійний ключ. Стан реле чи режим опалення не доводить роботу навантаження.
Час запису HA не є підтвердженим часом вимірювання.

## Factual and privacy contract

The seven formerly missing mappings are implemented as named status groups,
explicit activity mappings and five optional energy slots: battery SOC,
battery/load/PV/grid power. This is not generic household control or forecasting.

- At most 32 groups and 64 sources; report-age setting 30–86400 integer
  seconds, default 300. Each source pins both entity ID and entity-registry
  identity. Recreating an entity under the same ID does not adopt it silently.
- Owner/parent visibility is the default. Adult/child access needs explicit role
  grants; group and source roles both apply. Guests are excluded. Every read also
  requires the requesting person's active linked HA account and current entity
  `POLICY_READ`, checked before `states.get`. A Telegram-only family member cannot
  borrow the owner's HA permission. Denied rows, labels and counts are omitted.
- Energy accepts finite `%` SOC in 0–100 and compatible `W`/`kW` power, normalized
  to W. kWh is not power. Signed battery/grid values do not infer direction or
  electricity-grid availability. No inverter/voltage/brand heuristics apply.
- Groups permit bounded numeric sensor units (`%`, W/kW, Wh/kWh, V, A, °C/°F,
  hPa, bar, lx, ppm, Hz), finite unitless readings without a device class, or
  known enum states from the supported domains. The 32-group limit applies to
  both configuration and card rendering; sources remain bounded at 64 total.
- Group-only weather conditions and camera states use the documented closed
  [weather](https://www.home-assistant.io/integrations/weather/) and
  [camera](https://www.home-assistant.io/integrations/camera/) enums. No weather
  forecast service, stream, snapshot, camera operation or event listener is invoked.
- An [event entity](https://www.home-assistant.io/integrations/event/) releases
  only its validated last-event timestamp, never event payload/type or media.
  A sensor explicitly classified by HA as `timestamp` may report a future
  planned date. Both require strict timezone-aware ISO input and return UTC;
  a future *event* timestamp is invalid. These values are distinct from the
  HA report timestamp and do not establish physical occurrence or future truth.
  Freshness/restoration/ACL rules below still apply before any typed value.
- Arbitrary text sensors, attributes, media titles, images and URLs are excluded.
  An old free-text forecast-winner/schedule sensor is not silently imported as
  safe text. Configuring a source is still an explicit owner's action.
- Activity is only an exact match against the owner's selected states of
  switch/light/input_boolean/binary_sensor/media_player/climate. Relay on,
  climate heat mode or media idle is never proof of physical operation. A binary
  sensor has no automatic appliance interpretation.
- Unknown, unavailable, missing, restored, invalid numeric/unit/state, missing
  or future timestamp and stale-report states expose a bounded reason and null
  value, never fabricated zero or off. `last_reported` is used when available;
  only older state objects lacking that field fall back to `last_updated`.
  `ha_reported_at`, `freshness_basis` and age describe HA's report, not measured
  time. A cached card reports age **at the last explicit read**.

## API, replay and lifecycle

`family_assistant/home_status` accepts `entry_id`, optional `section`
(`home`, `energy`, `active`, `group`) and a `group_id` only for `group`. It never
accepts entity IDs, templates, services or actions. The response contains bounded
rows, `generated_at`, revision, max age and an opaque `access_marker`, not entity
IDs or raw attributes. The ordinary authenticated family view adds only
`home_status_access`, a hash of current configuration/actor/permitted registry
lineage. Computing it does not read HA states. Neither projection is added to
Engine's view or assistant tools/prompts.

There is no module scheduler, listener, coordinator, HA sensor entity, history
query, device effect, alert, proactive digest or external provider. ConfigEntry
Options retain mappings; Engine/Store retain no source values. Card values stay
in the current element's memory, never browser storage.

Telegram queues a private descriptor containing only section/group key and a
configuration/settings-epoch marker, plus the existing actor/bot/chat fence and
five-minute expiry. No labels or readings are retained in the outbox. The real
HA adapter resolves current user permissions and registry/configuration again
after its auth await, reads permitted values only at send time, and checks the
current private destination. Module/actor/options/entry revocation cancels stale
descriptors. ACL withdrawal omits the revoked source without reading it; a wholly
denied selection produces only the generic no-readable-sources response.

The existing update/outbox receipts prevent duplicate replay. Pending descriptors
survive Store reload but cannot outlive their expiry or revive an old settings
epoch. A Telegram transport timeout remains uncertain and is not blindly retried.
Private bot reply quotes are excluded from automatic LLM context; manually
pasted new user text remains ordinary user input. An already sent message or
in-flight transport cannot be recalled.

## Verification checkpoint

- Focused Python compatibility: **395 passed, one platform skip in 22.32s**;
  normalization/projection, actual Options delegates, real Engine/TelegramManager/
  Notifications, existing panel/presence/Telegram and public/release contracts.
- Actual FamilyCard/base/panel/registry Node subset: **130 passed in 5.99s**,
  including ten new manual-read/interval/error/identity/localization cases.
- Real Chromium: **10 passed in 15.4s**, including 390px EN/RU/UK screenshots,
  translated protocol-state labels, friendly `/status` group keys, explicit
  refresh, the real idle interval, access-marker withdrawal, late responses,
  text-only rendering and no browser storage. Ukrainian mobile screenshot was
  visually inspected. These synthetic WS fixtures verify presentation, not HA ACL.
  Specs use relative URLs and are discovered by the default unified runner;
  the independent config serves the same repository on port 8337.
- Native helper `tests/ha_home_status_smoke.py`, selected by
  `tests/ha_smoke.py --case home-status`: the integration writer independently
  reported **actual isolated HA 2026.9.2 PASS, exit 0**, on 13 September 2026,
  from its exact copy/hash-checked native-ready candidate. Native default/no-op/
  save/cancel Options, registry identity and role/ACL, metadata-only family view,
  units/stale/recreate, private late delivery/replay/revocation and real Store
  reload passed. Entities and Telegram transport were synthetic. Later changes
  were labels, error/test registration, evidence and declaration disposition;
  focused tests cover those, not a claimed second native run.
- Ruff, matching locale generation, public-tree privacy, declaration inventory
  validation and whitespace checks passed. The inventory check did not access
  old private source. No frontend/runtime inventory regeneration was performed.
- AGY models were discovered; a bounded sandboxed public-only read-only review
  identified existing dispatch/auth boundaries. A subsequent timed-out review
  supplied no accepted findings. Independent root review identified the idle
  timer/no-op gaps; both received explicit regressions and fixes.

Reproduction commands (from the public repository):

```text
python -m pytest tests/test_home_status.py tests/test_home_status_options.py tests/test_home_status_telegram.py tests/test_ha_options_menu.py tests/test_panel_settings.py tests/test_panel_readiness.py tests/test_presence_options.py tests/test_presence_observations.py tests/test_presence_delivery.py tests/test_notifications.py tests/test_telegram.py tests/test_telegram_command_scope.py tests/test_telegram_polls.py tests/test_public_contract.py tests/test_release_package.py tests/test_legacy_settings_inventory.py -q --tb=short
node --test tests/frontend-home-status.test.js tests/frontend-card-registry.test.js tests/frontend.test.js tests/frontend-panel.test.js
npx playwright test --config tests/playwright.home-status.config.js --workers=2 --reporter=line
```

New Node tests are also registered in the default `npm test` lifecycle. Full
combined Python/browser/inventory, upgrade and release gates belong to the
integration writer after merging independent increments. No production
installation, credentials or private legacy sources were accessed for this
implementation. Already transmitted Telegram text cannot be recalled; manual
readings are snapshots, not guaranteed live physical measurements.

## Typed groups follow-up — development after rc.8

The typed group and 32-group display changes passed 137 focused Python tests,
125 public/settings tests (one platform skip), 13 Node and 13 Chromium cases.
`ha_home_status_typed_smoke.py`, invoked by the actual home-status HA fixture,
passed isolated HA2026.8.2 and HA2026.9.2: native 13-group creation, weather/camera/
event/timestamp/count selectors, no-op Options, current child isolation, Store
and reload. No real device, camera endpoint or Telegram transport was used.
RU/UK mobile screenshots were inspected; timestamp values are displayed as
readable UTC dates, with precise ISO values retained only in the bounded API.
A bounded public-only AGY review timed out without findings; it is not accepted
review evidence. Full combined release/upgrade/CI acceptance remains separate.

Focused additions: `tests/test_home_status_typed.py`,
`tests/ha_home_status_typed_smoke.py`, `tests/frontend-home-status.test.js` and
`tests/browser/home-status.spec.js`. Existing argument-free configurations and
the exact no-op Options contract remain unchanged; no settings schema import
or household activation occurs on update.
