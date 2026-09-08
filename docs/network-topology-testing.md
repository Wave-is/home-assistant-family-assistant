# Network enforcement acceptance boundaries

The local approval ledger and private discovery subscriptions never grant or
block packet access. A successful RouterOS configuration read-back is not proof
of connectivity, and one tested topology cannot certify arbitrary home networks.

## Native isolated fixture

The developer harness uses a pinned official CHR 7.20.1 disk inside a disposable
QEMU VM. The containing Docker job has no external network, physical interfaces,
published ports or household mounts. Three virtual NICs serve container-only
management and two synthetic routed subnets. Only fictional identities and
documentation address ranges are used.

The existing full test verifies DHCP exchange, selected lease conversion/comments,
Kid Control configuration/replay, routed IPv4 probes, temporary modes, autonomous
timer expiry and VM startup restoration. The extended topology acceptance is
passed round-trip checks together with this full suite on vmxnet3. A stronger
one-way check subsequently exposed leakage described below; the earlier pass
must not be interpreted as complete packet isolation. Only explicit passed
observations are evidence, not the presence of code.

The full suite also passed a two-target lease failure using actual native
read-only credentials for the second comment. The first target was compensated,
the denied target and an unselected sentinel retained their configuration hashes,
and terminal replay performed zero router calls. The dynamic case additionally
simulated a lost response after real make-static, reconciled it through native
read-back, removed only that converted reservation and completed a fresh DHCP
exchange. The static case restored the original comment exactly.

## IPv6 finding

The added IPv6 fixture computes and independently verifies UDP pseudo-header
checksums, rejects unsupported extension/fragment headers and checks both Ethernet
and IPv6 endpoints plus a fresh payload. A scoped Neighbor Discovery responder
handles only the synthetic router and target address. It does not implement SLAAC
or a general IPv6 stack. See [RFC8200 section8.1](https://www.rfc-editor.org/rfc/rfc8200#section-8.1)
and [RFC4861 section7.1.1](https://www.rfc-editor.org/rfc/rfc4861#section-7.1.1).

Native tests observed a working bidirectional IPv6 baseline. Pausing the same
MAC through the integration's KidExecutor created dynamic source/destination
IPv6 reject rules and stopped that IPv6 probe. A separate control client still
passed; resuming the profile restored the selected client's traffic. The initial
assumption that Kid Control never affects IPv6 was therefore rejected, not made
into a product limitation. This is evidence for the pinned build and these
learned addresses only: not privacy-address rotation, a downstream NAT, offloaded
bridging, a different RouterOS version or every traffic protocol.

## FastTrack gate

MikroTik documents that FastTrack can bypass firewall and simple-queue processing;
changing the profile alone cannot be treated as a traffic assertion.
[Connection tracking manual](https://manual.mikrotik.com/docs/firewall-and-quality-of-service/connection-tracking/).
The CHR manual specifies Fast Path support on virtio-net/vmxnet3, so the new
fixture accepts only virtio-net or vmxnet3, not the earlier e1000 emulation.
[CHR installation](https://manual.mikrotik.com/docs/getting-started/installation-and-upgrade/install/chr-installation/).

The candidate test selects unused flow tuples, establishes a repeated bidirectional
UDP flow, and requires an actual FastTrack flag and packet-counter evidence. A
configuration-only rule cannot pass this gate. New and established flows are
then checked separately around pause/resume, together with an independent
control client. Both focused and full vmxnet3 runs passed: the dedicated pre-adoption flow
increased the native IPv4 FastTrack counter by 253 packets, and adopting then
pausing that client stopped round-trip completion for established and new IPv4 probes. Independent
IPv4/IPv6 control clients remained reachable and resume restored selected traffic.
The full run included lease conversion, timer expiry and restart before this
topology phase. A parallel full virtio run reached the same FastTrack flag but
zero accelerated packets and failed the calibration gate. The verified default
is therefore vmxnet3; documentation of general driver support is not substituted
for this fixture's actual traffic evidence.

**Raw Kid Control is not a complete isolation guarantee.** A later focused run separately
observed request arrival at the server and reply arrival at the client. Some
outbound requests reached the server during pause although the response did not
return. Therefore an unsuccessful echo alone cannot establish an Internet
quarantine. Another run still passed complete exchanges even after the native
directional reject rules appeared. These are observations of the accelerated
configuration, not successful isolation checks.

A subsequent focused run passed the stronger gate only after disabling the
fixture-owned FastTrack rule and expiring the two selected synthetic connection
tuples. Each deletion re-resolves and verifies one current tuple; an earlier
snapshot-wide deletion left a selected connection present. The test does not
guess that a successful DELETE response means all selected state is gone.
After verified disappearance, both new/old IPv4 tuples and the learned IPv6
address showed no outbound delivery. Independent control clients still passed;
resume restored the selected client's exchanges. Final full-suite/CI integration
of this stronger checkpoint is pending.

This mitigation exists only inside the disposable developer fixture. The public
runtime neither disables a user's FastTrack rules nor flushes connections, and
it continues to label Kid Control results as configuration, not connectivity.
Strict/quarantine modes must account for acceleration separately before release.

Calibration intentionally precedes creation of the Kid Control profile. Earlier
runs that calibrated after adoption saw a FastTrack flag but zero accelerated
packets and correctly failed; they did not establish a bypass or prove active
acceleration. Connection records can expose IPv4 address/port separately or as a
combined endpoint; the fixture rejects conflicting forms and selects unused tuples.
Every probe uses a fresh payload even when retaining the established five-tuple.

## Not yet certified

IPv6 FastTrack, IPv6 address churn, hardware-offloaded bridge/VLAN paths,
downstream NAT, Wi-Fi access lists, real bandwidth rates, broader native
fault recovery and production topology acceptance remain separate tests. Strict
unknown-client enforcement must not be enabled on the strength of these partial
results. No default DHCP/static-only setting is claimed to authenticate a device
or stop a manually configured address.
