# HACS early access — beta software

Family Assistant is early software under active development. A release candidate
is not a finished implementation of the full vision, a verified replacement for
every legacy workflow, or permission to migrate a household automatically. Review
the selected [release notes](https://github.com/Wave-is/home-assistant-family-assistant/releases)
and the [legacy parity audit](legacy-parity-audit.md) before deciding whether to
test it. Passing automated checks does not establish physical-device behavior.

## Installation through a custom repository

You can install a compatible public release without waiting for inclusion in the
default HACS catalog. In HACS, open the three-dot menu, choose **Custom
repositories**, enter `https://github.com/Wave-is/home-assistant-family-assistant`,
select **Integration**, and add it. Open Family Assistant and review the version
offered before downloading. This is the official
[HACS custom-repository workflow](https://www.hacs.xyz/docs/faq/custom_repositories/).

Candidates use the HACS display name **Family Assistant (Early Access)**. To receive
pre-release update offers, explicitly enable the repository's pre-release switch
as described in the [HACS switch documentation](https://hacs.xyz/docs/use/entities/switch/).
With it off, HACS does not consider pre-releases for update checks. Confirm the
selected `0.2.0-rc.*` version rather than assuming an old stable tag contains these fixes.

Use a separate test installation first. Before changing an existing household,
capture and verify its backup and previous integration files, review the release
requirements, and obtain the appropriate restart approval. A code rollback means
restoring the captured prior runtime through the same approved procedure; it is
not deletion of Store or Config Entry Options. A full backup restoration is a
separate operation. Downloading code is not approval to enable alarms, penalties,
network policies or optional providers.

The integration requires at least Home Assistant 2026.8.0. HACS uses the standard
`custom_components/family_assistant` source layout. The separately attached
runtime ZIP is not selected by a `zip_release` setting in this repository's
`hacs.json`.

## Release candidate versus default catalog

At the 13 September 2026 audit, `0.2.0-rc.2` was a published GitHub **prerelease**;
`0.1.1` remained the latest stable release. Check the current release page rather
than assuming that the newest candidate is the stable default. In particular,
“published on GitHub”, “installable as a HACS custom repository” and “included in
the default HACS catalog” are three different states.

At that audit, the repository was absent from the
[default integration list](https://github.com/hacs/default/blob/master/integration),
and a public search for the exact repository name found no catalog-submission
pull request. Inclusion is therefore not claimed. A submission is not acceptance:
HACS review can take time, and catalog visibility follows acceptance and scanning.

The official [catalog-inclusion requirements](https://www.hacs.xyz/docs/publish/include/)
require passing HACS Action without ignored errors, passing Hassfest for an
integration, a new full GitHub release after successful checks, and a reviewed
pull request against `hacs/default`. The repository already has both validation
jobs and a local integration brand icon; those prerequisites must be checked
again on the exact release commit. Do not label an unreviewed candidate “stable”
merely to make it appear in a catalog.
