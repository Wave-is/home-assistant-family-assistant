# Optional private image generation

Image generation is independent of text conversation providers. It is disabled
by default and requires explicit owner configuration. No provider is contacted
merely by loading settings; the native connection test reads model metadata only.
An installed developer-PC `agy` CLI is not an image endpoint. A separately
installed gateway implementing the protocol below is required for AGY images.
Gateway execution isolation must be verified separately before enabling it.

## Telegram behavior

- `/draw a friendly blue robot`, `нарисуй синего робота`, and
  `намалюй синього робота` request an image explicitly.
- `/images` shows the requesting member's latest 20 job statuses. It exposes no
  prompt, credentials, filesystem path, remote job identifier, or image URL.
- This initial implementation accepts drawing only in an authenticated member's
  private bot chat. Group requests receive private-chat guidance without creating
  a provider job. Guests, unbound senders and forwarded messages are not accepted.
- A genuine, decoder-verified PNG/JPEG/WebP file is uploaded to that same private
  identity. A text answer or URL is never treated as generated output.
- Failed and uncertain requests produce a private status notice. Uncertain
  generation or Telegram delivery is held without an automatic duplicate retry.

## Providers and supported workflows

`image_generation.providers` is an owner-ordered list of optional enabled rows.
Rows use `id`, `type`, `name`, `enabled`, `url`, `allow_http`, `api_key`, `model`,
`timeout`, `workflow`, `encoder` and `vae`. Supported types are `agy_gateway` and
`comfyui`; secrets stay in the ConfigEntry options, never job records/browser data.
Plain HTTP requires explicit opt-in. Redirects and output URLs are not followed.

Global settings are `enabled`, `width`, `height`, `steps`, `cfg` and
`negative_prompt`. Width/height are 512, 768 or 1024; steps 1–50, CFG 1–20,
per-request HTTP timeout 5–60 seconds, and a prompt is at most 2,000 characters.

ComfyUI uses its official local server endpoints:
[`/object_info`, `/prompt`, `/history/{prompt_id}`, `/view`](https://docs.comfy.org/development/comfyui-server/comms_routes).
It does not require an internet connection once the selected models are installed.
The integration does not download models or execute custom/API nodes.

- `checkpoint` uses the fixed
  [basic text-to-image graph](https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/basic_api_example.py),
  with one installed `CheckpointLoaderSimple` model.
- `z_image_turbo` follows the official
  [Z-Image Turbo template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_z_image_turbo.json):
  separate UNET, CLIP (`lumina2`) and VAE selections, SD3 latent image,
  AuraFlow shift 3, `res_multistep`/`simple` sampling and zeroed negative
  conditioning. The template suggests steps 8 and CFG 1. Select those values
  explicitly; the configurable checkpoint defaults are steps 20 and CFG 7.
  `negative_prompt` applies only to the checkpoint graph; the Turbo graph uses
  its documented zeroed conditioning. Arbitrary workflow import is not supported.

## Optional AGY gateway contract

This is a Family Assistant gateway protocol, not a claim that the stock AGY CLI
or text API exposes image generation:

- `GET /v1/images/models` → `{"models": ["configured-image-model"]}`.
- `POST /v1/images` accepts `request_id` (UUID), `prompt`, `model`, `width`,
  `height`. The server must persist idempotency before work; the job ID equals
  the request ID. Reusing an ID with different input must fail.
- `GET /v1/images/{job_id}` returns that ID and `status`: `queued`, `running`,
  `succeeded`, `failed`, or `uncertain`. A definitive failure may carry
  `error.code` (`quota_exceeded`, `unavailable`, or `rejected`).
- `GET /v1/images/{job_id}/content` returns actual image bytes with the matching
  image MIME type; it must never redirect to an external URL.

Only a definite pre-submission failure or confirmed failed job with no output
permits fallback. A POST timeout recovers AGY by GET of the durable request ID.
ComfyUI has no equivalent submission idempotency: after a persisted intent and
lost POST acknowledgement, no second POST or fallback is allowed. A poll GET
being rate-limited does not prove that the accepted generation failed.

## Bounds, privacy and recovery

Every job pins its member revision/role/private Telegram binding, household
namespace and complete provider configuration digest. These are rechecked before
and after awaits and inside state transactions. Changes to identity, settings,
module or runtime prevent further effects. Provider bodies and credentials are
not surfaced as errors. Cancellation preserves the durable submission/delivery
intent instead of claiming that an external operation was undone.

Queue admission is bounded to 20 pending jobs, three per member, and ten reserved
image slots (at most 60 MB at the 6 MB/file cap). A job expires after ten minutes.
Local files are decoder-verified in the existing bounded helper process and stay
outside static/frontend paths. File publication uses opaque keys and cannot
overwrite a different image. Local files expire after 24 hours; cleanup runs
independently of the Telegram worker and removes known abandoned candidates.

Generated images are transient cache, not task evidence. Their bytes are not
part of the existing household-report media backup registry. Restoring a state
without this cache does not regenerate or resend an image. Telegram messages
and remote ComfyUI output files have their own retention; local cleanup does not
delete them. Telegram's `protect_content` flag is not a guarantee against copying.

The latest 20 statuses are projected, while at most 1,000 durable job receipts
are retained to prevent old updates regenerating images. At that safety cap,
admission stops rather than silently dropping deduplication history. A reviewed
receipt-compaction UI and cross-channel image viewer are not implemented.

The parent-facing connection panel shows image generation as an optional
connection, separate from required module readiness. Saved providers, the
enable switch and a current initialized adapter are distinct facts: none prove
HTTP reachability or a successful generation. Disabled settings hide stale
connection errors; available adapters must still match the current configuration
and authority scope. Provider details and generated bytes are never included in
this status projection.

## Verification scope

`tests/test_image_generation.py` exercises actual Engine transactions, fake HTTP
using the documented request/response shapes, real private files and the Pillow
validator. It covers both workflows, quota/offline fallback, cancellation and
restart, lost submission receipts, Store failures, invalid/oversized output,
traversal rejection, revoked scope, private history and retention cleanup.
`tests/test_telegram_image_generation.py` exercises actual manager admission and
the multipart client without a real bot. `tests/test_image_runtime_wiring.py`
checks runtime replacement, configuration/module fences and cleanup wiring.
`tests/test_provider_readiness.py` checks authoritative text-provider chains,
AGY search opt-in, optional private image status and complete runtime-error
translations; no metadata or generation requests run while building readiness.
These are synthetic checks, not a claim that AGY, ComfyUI or Telegram generated
or delivered an image in the user's installation.
