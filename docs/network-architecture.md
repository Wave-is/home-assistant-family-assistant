# Optional RouterOS module

Connection, inventory, reviewed lease plans and adopted Kid Control profiles are
implemented and tested with a synthetic router in real HA. Native synthetic-profile
checks on an authorized reserve hAP additionally verified pause/resume, hours,
rate, temporary grant and router-only expiry. REST-wire, actual reboot/startup and
end-to-end traffic checks remain separate gates. No production router
changes are made by installation, options validation or inventory polling.

The client follows the [RouterOS REST API](https://manual.mikrotik.com/docs/developer-guides/rest-api/)
over HTTPS, with certificate verification and optional owner-supplied CA trust.
There is no insecure TLS switch, redirect following or generic console endpoint.
Basic credentials stay in local HA options. A different server or username
requires entering the password again. Do not paste a private key in the CA field.

Use a dedicated custom RouterOS group with `read,rest-api` for inventory.
The built-in `read` group includes more privileges than its name suggests;
RouterOS policies are not a field-level ACL. See the official
[user policy documentation](https://manual.mikrotik.com/docs/authentication-authorization-accounting/user/).
Explicitly approved writes require `write`; this does not justify adding
`reboot`, `policy`, `sniff`, `sensitive`, SSH, FTP or WinBox.

The table and property allowlists cover DHCP leases/servers/networks, ARP, bridge
hosts, interfaces, supported Wi-Fi registration/access tables, Kid Control and
limited topology indicators. A missing optional table is a reported capability,
not an empty successful table. A failed read keeps the last good observation and
sets a visible health error. Polling is every two minutes, with bounded requests
and a five-second minimum between refresh attempts.

HA matching uses registry MAC connections and a narrow projection of device
trackers. Exact MAC evidence ranks above a currently corroborated tracker IP;
hostname-only evidence is a suggestion, never an automatic assignment. Equal
matches remain ambiguous. Locally administered MACs are flagged, not declared
random or malicious. Router interfaces are protected. The current inventory is
parent-only in authenticated HA APIs; it is not forwarded to a language model.

## Reviewed lease changes

Only owners perform bulk lease administration. Connection options require
explicit write enablement plus verified, protected HA-host and administration
device MACs. Preview selection preserves comments unless replacement is checked.
No mutation runs while the preview is being prepared. Plans expire after five
minutes and bind to the configured router, user and protected-device scope.

- Static-lease previews check IP/MAC, DHCP server and interface-subnet conflicts.
  Applying repeats those checks, journals each effect intent in Store before
  sending it and verifies the selected records after the operation. Only typed
  make-static, comment and approved reservation-compensation methods exist.
- RouterOS has `make-static` but no equivalent way to reconstruct a dynamic
  lease verbatim. A rollback that removes a new reservation leaves recovery to
  DHCP renewal; the UI explains this and requires explicit recovery consent.
  No exact dynamic-lease rollback is claimed. A failed read-back triggers scoped
  compensation; a concurrent user edit or revoked authority stops further writes
  and marks the plan for review. Disk failure stops effects immediately.
- Timeout after an accepted write is resolved by reading its result, not blindly
  repeating the write. Persisted phases let an interrupted operation reconcile
  its already-applied conversion. A replayed confirmation cannot run it twice.
  Final status is saved before an owner-private notification. Network inventory
  is not posted to a family group by this workflow.

## Reviewed Kid Control

Ownership is explicit: only an owner can adopt an existing profile after checking
all its device records. Parents then control that adopted profile; an adult needs
separate delegated permission. Children see only their own status without MACs.
Connection write enablement is separate from lease write enablement.

Plans are actor-bound, five-minute previews. Every effect journals its phase,
rechecks ownership/permissions and reads back the resulting configuration. A timed
operation installs and verifies two owned scheduler templates **before** changing
mode. The expiry guard restores the previous disabled/paused mode independently
of HA; a startup guard is intended to end the exception early on router reboot.
The latter's configuration is checked, but real startup execution is still a test
gate. Timers name the exact adopted profile and internal ID, preserve unrelated
schedule/rate edits and remove only their own two entries. RouterOS 7.16+ and
synchronized matching time zones are required. There is no arbitrary script API.

Telegram commands and the card use the same permissions and plans. Telegram
confirmation is bound to its author; duplicate updates cannot extend the duration.
The worker's verified/failed/expired result goes privately to that author.
Native duration (`7h30m`, `1d`) and script boolean (`yes/no`, unlike REST strings)
compatibility have regression tests based on native hardware findings.

## Remaining control gates

- Kid Control resume means return to its configured schedule, not unrestricted
  access. Temporary grants require the verified router-local expiry described
  above. Restriction state is not proof that FastTrack, IPv6 or downstream
  NAT cannot bypass it. Read-back and topology checks are separate gates.
- No ownership is inferred from a familiar comment or profile name. Adopting
  existing profiles/devices and adding a protected administration path require
  explicit user selection. No generic firewall editor is exposed.

References: [Kid Control](https://manual.mikrotik.com/docs/firewall-and-quality-of-service/kid-control/),
[DHCP lease behavior](https://manual.mikrotik.com/docs/network-management/dhcp/).
