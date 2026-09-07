# Shared card availability shell

The availability shell gives a Family Assistant card an understandable,
localized state when its normal domain projection cannot be rendered. It is a
read-only frontend helper: it adds no API, sends no command, and never inspects
or interpolates private records.

## States

The helper supports four states in English, Russian, and Ukrainian:

- `loading`: current projected data has not arrived;
- `module_disabled`: the module is absent from the projected enabled-module
  list;
- `role_unavailable`: the module is enabled but its projection is absent for
  this account;
- `error`: the latest read failed. Only fixed copy and a read-only Retry button
  are shown; the raw error code is not rendered.

The role-unavailable copy deliberately does not say that a card is
parent-only, name a role, or distinguish “no records” from “private records
exist”. An empty array or object is an available projection and must be passed
to the normal renderer, which owns its legitimate empty state.

Loading and unavailable states use a polite status region. Loading also sets
`aria-busy=true`. Errors use an assertive alert, and Retry is a native keyboard
button that calls the card's existing read-only `refresh()` method. This slice
does not change global focus restoration or background refresh behavior.

## API

`frontend/availability-shell.js` exports:

```js
availabilityState(card, module, projection)
renderAvailabilityShell(card, body, {module, projection, state})
AVAILABILITY_COPY
```

`availabilityState` and `renderAvailabilityShell` return one of the four state
strings or `null` when the regular card may render. The optional explicit
`state` is intended for the shared loading/error branches. Unknown explicit
states fail closed by appending nothing.

## FamilyCard wiring

The shared card now uses this gate in all five dedicated dispatch branches and
clears every corresponding draft when the module or role becomes unavailable.
Guest access is explicitly unavailable even if an empty projected object remains.
Existing household selection, initial loading and read-error branches are
preserved; the helper's optional loading/error primitives are independently tested.

Import `renderAvailabilityShell` in `family-assistant.js`. At each dedicated
module dispatch, call it only before the normal renderer and only with that
module's already projected value:

```js
if (renderAvailabilityShell(this, body, {
  module: "polls",
  projection: this._data.polls,
})) return;
renderPolls(this, body);
```

Use the equivalent projected roots for `school`, `maintenance`, `presence`,
and `digests`. Do not derive availability from record counts and do not combine
another member's projection. The current shared loading and read-error
branches may also delegate to this helper; they must still stop dispatch until
a successful fresh view is present.

The helper appends to the supplied real `FamilyCard` body and does not clear
it. Dispatch should call it before adding module content. Styling can reuse the
existing `empty`, `notice`, and button rules; the new classes are stable hooks
for a later shared style refinement.

## Acceptance boundary

The focused DOM tests instantiate the registered real FamilyCard subclass.
Browser tests cover actual refresh/dispatch, localized mobile module-off and
role-unavailable states, private canaries and horizontal overflow. DOM tests also
cover loading/error primitives and a realm without a global Element binding.
These synthetic checks do not replace a screen-reader and packaged
dashboard acceptance pass.
