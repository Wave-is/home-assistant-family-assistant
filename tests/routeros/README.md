# Native RouterOS acceptance lab

Developer-only tests, **not** a component dependency and not a tool for connecting
to a physical router. The harness has no router-address or credentials input.
It boots a temporary copy of an official CHR image in QEMU/TCG and destroys that
copy when the run ends. No CHR image is distributed in this repository/release.

## Isolation

- Run with Docker `--network none`, no published ports, no devices, all Linux
  capabilities dropped and no-new-privileges. Never use host networking.
- Mount only this public source tree and the operator-downloaded CHR archive,
  both read-only. Never mount HA configuration, a real router disk, credentials,
  SSH keys or the Docker socket.
- QEMU management uses restricted user-mode networking and a container-loopback
  HTTPS forward. Two other emulated NICs exchange Ethernet frames with synthetic
  Python endpoints over fixed loopback UDP ports. There are no TAPs or host bridges.
- All emulated addresses are documentation/test ranges. The VM cannot reach the
  household network or the Internet. Its generated password is never printed.
- The test imports the VM-generated public certificate into its TLS trust store;
  certificate validation remains enabled for every integration request.

## Run

Use a disposable Linux Docker development environment. Obtain the official image
from [MikroTik](https://download.mikrotik.com/routeros/7.20.1/chr-7.20.1.img.zip)
and review the [CHR license](https://manual.mikrotik.com/docs/getting-started/routeros-licensing/chr/chr-licensing/).
The 7.20.1 archive tested during development has SHA-256:

```text
aab591e9c2da21d8416ad1ed9966fa2359ebef7a25c3b20453efe93f05234e6b
```

The archive hash verifies the downloaded fixture, not a MikroTik signature. Obtain
it only from the official HTTPS origin and do not silently accept a changed hash.
Place it at a task-specific absolute path, then from the repository root:

```sh
docker build -t family-routeros-lab tests/routeros
docker run --rm --network none --cap-drop ALL \
  --security-opt no-new-privileges --memory 768m --cpus 1 \
  --env FAMILY_ROUTEROS_ISOLATED=1 \
  --env FAMILY_ROUTEROS_SHA256=aab591e9c2da21d8416ad1ed9966fa2359ebef7a25c3b20453efe93f05234e6b \
  --mount type=bind,src="$PWD",dst=/work,readonly \
  --mount type=bind,src=/absolute/test-fixtures/chr-7.20.1.img.zip,dst=/input/chr.img.zip,readonly \
  family-routeros-lab
```

TCG deliberately does not require KVM access. Allow several minutes for initial
boot/certificate generation and two real one-minute expiry tests. A failed
assertion stops the run; a successfully saved command is not a traffic assertion.
The **Native RouterOS acceptance** workflow runs the same isolated test on manual
dispatch, with a fixed official image URL/hash and without repository secrets.

## Acceptance coverage and limits

The harness exercises actual verified-HTTPS inventory and the integration's
`LeaseExecutor`/`KidExecutor`, including durable-intent callbacks, selected-record
read-back, terminal replay, native scheduler expiry and isolated VM restart.
The packet fixture obtains a real dynamic DHCP lease and sends routed IPv4 UDP
between two emulated subnets to check restriction effects. Unit tests separately
cover faults, role revocation and rollback; the native lab is not a replacement.

Consult [the acceptance matrix](../../docs/implementation-status.md) for which
gates actually passed on a given checkpoint. This lab does not establish IPv6,
FastTrack, hardware-offloaded bridge, downstream NAT, real Wi-Fi, throughput or
production migration correctness. The CHR free license's bandwidth limit also
precludes a meaningful speed-limit performance claim.

Packet fixture references: [DHCP RFC 2131](https://www.rfc-editor.org/rfc/rfc2131),
[QEMU network invocation](https://www.qemu.org/docs/master/system/invocation.html).
