# Family Assistant public integration

This is the canonical, publishable source tree. The private operations project
is a separate directory. Do not copy private configuration, logs, attachments,
device identifiers, family data, or credentials into this repository.

Read docs/vision.md and docs/implementation-status.md before continuing work.
The vision is the accepted scope. An alpha, skeleton, or subset is not completion.
Update the requirement matrix with implementation and verification evidence.

All required integration runtime belongs under custom_components/family_assistant.
No production dependency on a developer PC, private gateway, or second custom
integration. Optional services use explicit user-configured providers.

Preserve the running legacy installation until migration is verified. Live
operations are governed by the private operations project's AGENTS.md.

Never publish without reviewing the exact staged files and running privacy,
packaging, unit, frontend and Home Assistant compatibility checks appropriate
to the release. Synthetic fixtures only. Do not claim tests passed if they did
not run. Do not use broad Git staging in the private operations project.

