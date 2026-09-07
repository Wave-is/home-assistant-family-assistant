# Release-candidate artifact checks

`tools/build_release.py --version <manifest-version>` builds an in-memory ZIP,
reads every entry back and reports its version, counts and SHA-256. Add
`--source <reviewed-export>` to build the exact tested source export and
`--output <new-file.zip>` to retain the candidate. Existing artifacts are never
overwritten. This command does not tag, publish, update HACS or touch HA.

The ZIP has `custom_components/family_assistant/` as its only root. It contains
all runtime Python, translations, services, frontend modules and brand assets,
not tests, documentation, caches or workstation dependencies. Source privacy
checks run first; unknown runtime files, symlinks and Windows reparse
points/junctions fail closed without being traversed. Every regular runtime file
is captured once against a stable filesystem identity, and a second inventory
must match before packaging. The manifest version is validated from those exact
captured bytes rather than from an earlier read. Missing relative Python or
JavaScript modules also fail the build. These checks validate declared local
imports; Home Assistant can still load documented integration entry points that
are not imported by another module.

ZIP entry names are sorted in canonical POSIX order and have fixed metadata, so
identical captured source bytes are reproducible on the same Python/zlib runtime.
This is not a promise of identical compression across different zlib versions.

HACS continues to use the existing repository layout (`zip_release` is not
enabled). This candidate is a packaging/verification artifact, not an alternative
HACS installation route. HACS expects all runtime files under the integration
directory and can offer tagged GitHub releases independently of ZIP assets.
See [official integration publication requirements](https://hacs.xyz/docs/publish/integration/).

Before any release: review the exact source; run privacy, package, unit,
frontend/browser, actual-HA, HACS and Hassfest checks; confirm the tag equals the
manifest version; document migration and rollback limits. A prerelease must
remain explicitly labelled as such. Packaging success does not certify legacy
migration, production providers, physical devices, a full HA restore or inclusion
in the HACS default catalogue.
