# Editing an online-school account

An existing account now opens with its selected student, notification switches,
preparation time and recipients. New bindings still default to notifications off,
18:00, and no recipients. Passwords remain blank in the form: blank means retain
the password only for the same account URL and username.

A normal edit offers only the previously verified student and does not contact
the school portal. This permits label and notification-policy changes during a
portal outage. Select **Refresh available students** to discover a different
student for the same account; refresh requires a successful connection. Changed
credentials, provider identity, household timezone, child binding or child epoch
also require discovery. An unavailable portal cannot authorize a new binding.

An exact no-op retains the original Options envelope. Label, notification-policy
and account-disable edits retain the generation, cache, homework acknowledgements
and durable notification markers. They advance the source configuration revision,
so already-queued notices from the previous policy cannot be delivered. Existing
same-day preparation markers remain consumed: changing recipients, disabling and
re-enabling notices does not send a second preparation notice that day. A newly
selected recipient receives future notices, not a replay of an old one.

Re-enabling a disabled account is explicit reauthorization: it requires discovery,
creates a new generation and resets facts and acknowledgements. This differs from
turning the notification switch off and on for an otherwise enabled account.
Changing a verified student/account/binding also starts a new generation and
deliberately resets the cached facts and homework acknowledgements.

## Concurrency and delivery authority

The owner-reviewed policy marker pins the source ID, generation, configuration
revision, owner epoch and selected-recipient epochs. Reconciliation also requires
the unchanged current child binding and household timezone. It cannot enable a
canonically disabled source or overwrite a later source edit. The consumed marker
ID persists; replay, restart and unrelated later Options saves cannot reapply it.
Stale queued markers are ignored. A later canonical edit may therefore require a
fresh Options flow; stale review is not automatically rebased.

The native flow still checks the exact full Options value and owner/runtime/
member/source scope before its steps and after discovery/close awaits. Unrelated
tasks, cache refreshes and homework acknowledgements do not invalidate a reviewed
policy edit. Source cache and credentials remain separate: credentials stay in
ConfigEntry Options and are never copied into the domain Store or private view.

## Verification boundary

`tests/test_online_school_options_editing.py` exercises the actual native Options
implementation with adapter-only HA form stubs and fictional provider discovery,
then applies results through real Engine transactions and reloads the persisted
Store shape. It covers defaults, offline/no-op saves, policy and account-disable
cache retention, changed-identity reset, stale owner/child/recipient/source scopes,
malicious unverified student IDs, consumed-marker replay and same-day deduplication.

`tests/ha_online_school_smoke.py` extends actual Home Assistant acceptance with
native offline policy editing, current defaults, no-op saves, preserved homework
acknowledgements, disable and Store reload. Running this fixture requires the
separate isolated HA acceptance environment; unit tests alone do not establish
native HA acceptance. No real school account or external school endpoint is used.
