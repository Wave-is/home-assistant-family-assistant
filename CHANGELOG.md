# Changelog

## 0.2.0-rc.4 — optional text and image providers

Prepared prerelease; publication and exact-commit CI are separate gates.

- Owner-configurable ordered chains of zero to eight text providers: AGY's
  Ollama-compatible HTTP API, Ollama/Qwen and an independently reviewed HA agent.
  Explicit empty chains stay empty; legacy slots remain compatible until replaced.
- Separate optional AGY image gateway / ComfyUI chain, private Telegram drawing
  requests, verified image bytes, durable request history and conservative fallback.
- Native RU/UK/EN provider editing, ordering, removal, metadata discovery and
  credential clearing, without generating content during setup.
- Optional standalone AGY CLI gateway with authenticated APIs, restricted tool
  hooks, schema validation and request-ID-bound image jobs. Gateway installation
  and authentication remain separate from HACS.
- Explicit adult-only AGY evidence search with optional SearXNG fallback; model
  prose is not a search source and child searches do not use this AGY route.
- Unified optional image health reporting, replacement guards and cleanup that
  does not erase unrelated generation/delivery failures.

See [release notes](docs/releases/0.2.0-rc.4.md) for acceptance, compatibility,
retention limits and rollback. This does not complete the legacy parity audit.

## Earlier releases

- [0.2.0-rc.3 — bounded task-recipient learning](docs/releases/0.2.0-rc.3.md)
- [0.2.0-rc.2 — control and legacy parity audit](docs/releases/0.2.0-rc.2.md)
- [0.2.0-rc.1](docs/releases/0.2.0-rc.1.md)
- [0.1.1](docs/releases/0.1.1.md)

Historical release notes remain under [docs/releases](docs/releases). Their
original completeness labels do not supersede the current acceptance matrix.
