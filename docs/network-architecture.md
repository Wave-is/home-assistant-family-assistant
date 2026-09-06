# Optional RouterOS module

Connection and inventory are implemented; applying mutation plans, Kid Control and
allowlist enforcement remain separate acceptance gates. No production router
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
Future explicitly approved writes require `write`; this does not justify adding
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

## Mutation requirements still to implement

The pure lease preview and conflict/protection checks are unit-tested. They are
not exposed as a router write operation yet; the following application gates remain.

- Static-lease previews must preserve comments by default, check current IP/MAC,
  server and subnet conflicts, bind to a live fingerprint and expire. Apply only
  selected records, preserve exact pre-state and read back every operation.
- RouterOS has `make-static` but no equivalent way to reconstruct a dynamic
  lease verbatim. A rollback that removes a new reservation leaves recovery to
  DHCP renewal; the UI must explain and explicitly authorize that distinction.
  Never claim an exact rollback from a guessed dynamic flag.
- Kid Control resume means return to its configured schedule, not unrestricted
  access. Temporary grants need a router-local expiry before they are called
  autonomous. Restriction state is not proof that FastTrack, IPv6 or downstream
  NAT cannot bypass it. Read-back and topology checks are separate gates.
- No ownership is inferred from a familiar comment or profile name. Adopting
  existing profiles/devices and adding a protected administration path require
  explicit user selection. No generic firewall editor is exposed.

References: [Kid Control](https://manual.mikrotik.com/docs/firewall-and-quality-of-service/kid-control/),
[DHCP lease behavior](https://manual.mikrotik.com/docs/network-management/dhcp/).
