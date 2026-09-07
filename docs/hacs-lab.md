# Offline HACS install and upgrade lab

This is a synthetic acceptance gate for the pinned HACS installer. It does not
contact GitHub, use a real HACS token, read a household configuration, publish a
release, or claim admission to the HACS default catalogue.

## Pinned inputs

Supply these files separately as read-only inputs:

- HACS `2.0.5` (`c0dfd8b44297c3673c21973e2539375a53687a9c`), official
  `hacs.zip`, SHA-256
  `97be6b824a4f38e683728cc6dd72367f6b8bad0a43428b1b3b987a3087adf413`;
- `aiogithubapi-22.10.1-py3-none-any.whl`, SHA-256
  `d5f722090545d033e022692fbe09d72c68a86b53e4de69cca1d500abd1388252`;
- an exact reviewed baseline repository export and a distinct candidate export.

The runner verifies each dependency's absolute regular-file identity, hash and
archive layout before starting Home Assistant. The wheel is added to the child
process import path; the network-disabled HA environment does not run `pip` or
resolve packages.

```text
python /candidate/tools/run_hacs_upgrade_acceptance.py \
  --baseline /baseline \
  --candidate /candidate \
  --hacs-archive /inputs/hacs.zip \
  --aiogithubapi-wheel /inputs/aiogithubapi-22.10.1-py3-none-any.whl \
  --timeout-seconds 300
```

Run this inside the same pinned Home Assistant `2026.8.2` image used by the
actual-HA gate, with networking disabled and all source/input mounts read-only.

## What runs

The outer process validates both repositories with the existing deterministic
release builder and creates one marker-owned temporary HA configuration. It
installs only the pinned HACS bootstrap into that temporary configuration.

Fresh HA child processes then:

1. register the synthetic public repository through HACS's admin WebSocket
   command and install the baseline through HACS's repository download path;
2. create the existing synthetic Family Assistant upgrade contract;
3. inject an unavailable candidate transport and require HACS to restore the
   exact baseline directory without advancing its installed version;
4. perform the successful candidate download through HACS and stop for the
   normal integration restart boundary;
5. boot the candidate and run the existing durable continuity/replay checks.

The GitHub/download transport boundary is synthetic. It exposes a bounded
repository tree, manifests, release metadata and tag archive made solely from
the already validated runtime bytes. Any unrecognized URL fails the phase.
HACS performs repository registration, download selection, directory backup,
removal, extraction, rollback, installed-version bookkeeping and HACS Store
writes.

The offline bootstrap does not enroll an OAuth-backed HACS Config Entry. Its
post-install request to recreate **HACS's own update entities** is recorded once
instead of forwarding a nonexistent entry. This is not a test of HACS's update
entity platform or account lifecycle. The repository installer and persistence
are unmodified; Family Assistant's actual setup, entities and frontend resources
are exercised by the later HA application phases.

Child stdout and stderr are discarded. On a failed phase, the helper writes a
bounded structural marker containing only the exception class and up to eight
`file-basename:function:line` frames. The runner validates that fixed schema
before including it in the failure code; exception messages, locals, URLs,
tokens and absolute paths are never returned.

## Artifact identity and limits

The current `hacs.json` does not enable `zip_release`. HACS therefore consumes a
GitHub-shaped tag archive, not the deterministic ZIP produced by
`tools/build_release.py`. The test requires the installed runtime file map and
every byte to equal the validated artifact entries. It does not claim the two
transport archives have identical bytes.

This gate does not exercise the HACS browser UI, live GitHub releases, rate
limits, public download availability, a real HACS account, production providers,
physical devices, a full backup restore, or migration of private household data.
