# Release-candidate artifact checks

`tools/build_release.py --version <manifest-version>` builds an in-memory ZIP,
reads every entry back and reports its version, counts and SHA-256. Add
`--source <reviewed-export>` to build the exact tested source export and
`--output <new-file.zip>` to retain the candidate. Existing artifacts are never
overwritten. This command does not tag, publish, update HACS or touch HA.

The ZIP has `custom_components/family_assistant/` as its only root. It contains
all runtime Python, translations, services, frontend modules and brand assets,
not tests, documentation, caches or workstation dependencies. Source privacy
checks run first; unknown runtime files and symlinks fail closed. Fixed ZIP
metadata and sorted paths make identical source bytes reproducible on the same
Python/zlib runtime. This is not a promise of identical compression across
different zlib versions.

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
