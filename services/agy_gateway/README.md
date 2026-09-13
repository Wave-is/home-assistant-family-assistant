# Standalone Optional AGY CLI Gateway (early version)

The AGY CLI Gateway is an optional, standalone HTTP microservice that bridges Home Assistant Family Assistant integrations to local or host-installed Antigravity CLI (`agy`) tools and inference.

> [!IMPORTANT]
> This service is **strictly optional**. Family Assistant does not have any hardcoded, production, or mandatory dependency on this service, developer PCs, or private infrastructure. It is only contacted if a user explicitly configures an `agy` or `agy_gateway` provider in the integration options.

---

## Features & Architecture

- **Ollama-Compatible Chat**: Implements `/api/chat` and `/api/tags` so conversation agents can communicate via standard payloads.
- **Evidence-Only Web Search**: Implements `/v1/search` using the `family-search` custom agent profile. URLs and evidence are parsed strictly from actual `search_web` tool outputs—never fabricated from conversational model hallucinations. Child search requests (`safesearch=2`) are explicitly rejected with `501 Not Implemented`.
- **Asynchronous Image Generation**: Implements durable jobs (`/v1/images`), exact request-ID deduplication (`job_id == request_id`), two workers, queue limit 16, and verified PNG/JPEG/WebP up to 6 MB. Different request IDs are separate requests, even with identical prompts. Text responses are never images. Changed payload under an existing ID is rejected.
- **Subprocess & Custom Agent Isolation**:
  - `family-text`: Text generation only (`tools: []`), no tools or filesystem permissions.
  - `family-search`: Search only (`tools: [search_web]`), no shell or device tools.
  - `family-image`: Image generation only (`tools: [generate_image]`), output verified strictly inside the job directory.
- **Security-First Execution**:
  - Profiles alone are **not a permission boundary**. Global and per-job hooks deny all tools except completion, the exact requested search in search mode, or fresh image generation in image mode. Shell, arbitrary files, browser, MCP, timers and subagents are denied. `--new-project` ensures job-local policy discovery.
  - Requires Bearer token authentication verified via constant-time comparison (`hmac.compare_digest`).
  - Public-only `/health` endpoint exposing zero private metadata.
  - Subprocesses are spawned directly with argument lists (`shell=False`), and process groups are terminated upon timeout or cancellation.
  - Process stdout/stderr bounded to 8MB max.
  - The gateway does not log prompts, raw errors or credentials. The CLI can retain its own private history and source images in the dedicated authentication volume; gateway workspace pruning does not erase that separate CLI history.

Use a **dedicated container and authentication volume** with a user-owned,
authenticated AGY binary. The Dockerfile's `AGY_BASE_IMAGE` must already contain
the CLI; its default Python base does not install or authenticate AGY. Never mount
a developer's full home, Home Assistant config, Docker socket, host credentials
or devices. `AGY_DEDICATED_PROFILE=1` installs a deny-by-default policy into this
dedicated home; **do not run it against an ordinary user's CLI settings**.
Authenticate your own dedicated CLI using the vendor's supported procedure.
Keep credentials, API key and job data outside the image and repository.
Use dropped capabilities, no-new-privileges and bounded CPU, memory, PIDs and logs.
Bind only to a trusted LAN or private authenticated proxy, not the public Internet.

---

## Configuration

All configuration is provided via environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `AGY_API_KEY` | *(Required)* | Secret Bearer authentication token. |
| `AGY_DEDICATED_PROFILE` | *(Required: `1`)* | Dedicated service-home attestation; startup installs its tool policy. |
| `AGY_MODELS` | `gemini-3.8-flash-low` | Comma-separated list of allowed models. |
| `AGY_DATA_DIR` | `./data` | Directory for durable job state and run sandboxes. |
| `AGY_BIN` | `agy` | Executable path for the AGY CLI binary. |
| `AGY_HOST` | `127.0.0.1` | Binding interface (`HOST` is also accepted). |
| `AGY_PORT` | `8080` | Port (`PORT` is also accepted). |

---

## API Protocol

### 1. `GET /health`
Public health status. Does not require authentication.
- **Response**: `200 OK`
  ```json
  {"status": "ok"}
  ```

### 2. `GET /api/tags`
Returns available models in Ollama-compatible format. Requires Bearer authentication.
- **Response**: `200 OK`
  ```json
  {
    "models": [
      {"name": "gemini-3.8-flash-low"}
    ]
  }
  ```

### 3. `GET /v1/images/models`
Returns available image models. Requires Bearer authentication.
- **Response**: `200 OK`
  ```json
  {
    "models": ["gemini-3.8-flash-low"]
  }
  ```

### 4. `POST /api/chat`
Ollama-compatible chat endpoint.
Schema requests are prompted with the full schema and independently validated.
The CLI's unreliable `--json-schema` flag is not used. Exactly one JSON object is
required; repeated JSON, external schema references and unsupported vision input
fail visibly. The integration can then use the next configured text provider.
- **Headers**: `Authorization: Bearer <AGY_API_KEY>`
- **Request**:
  ```json
  {
    "model": "gemini-3.8-flash-low",
    "messages": [
      {"role": "user", "content": "Hello"}
    ],
    "format": null,
    "options": {"timeout": 30}
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "model": "gemini-3.8-flash-low",
    "message": {
      "role": "assistant",
      "content": "Response text or schema JSON"
    },
    "done": true
  }
  ```

### 5. `POST /v1/search`
Evidence search endpoint.
- **Headers**: `Authorization: Bearer <AGY_API_KEY>`
- **Request**:
  ```json
  {
    "query": "local community events",
    "limit": 5,
    "model": "gemini-3.8-flash-low"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "results": [
      {
        "url": "https://example.org/events",
        "title": "Community Calendar",
        "snippet": "Upcoming events for families..."
      }
    ]
  }
  ```
  *(Note: Requests with `safesearch=2` return `501 Not Implemented`)*.
  Missing completed tool evidence produces an empty result list, allowing the
  integration's optional SearXNG fallback. Model-written citations never count.

### 6. `POST /v1/images`
Submit asynchronous image generation job.
- **Headers**: `Authorization: Bearer <AGY_API_KEY>`
- **Request**:
  ```json
  {
    "request_id": "b3e0c406-8bfa-4c4f-9e7e-3ecdc061f22d",
    "prompt": "sunset over mountains",
    "model": "gemini-3.8-flash-low",
    "width": 512,
    "height": 512
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "job_id": "b3e0c406-8bfa-4c4f-9e7e-3ecdc061f22d"
  }
  ```

### 7. `GET /v1/images/{job_id}`
Poll image generation job status.
- **Response**: `200 OK`
  ```json
  {
    "job_id": "b3e0c406-8bfa-4c4f-9e7e-3ecdc061f22d",
    "status": "succeeded"
  }
  ```
  *(Possible statuses: `queued`, `running`, `succeeded`, `failed`, `uncertain`). If `failed`, includes `error: {"code": "quota_exceeded" | "unavailable" | "rejected"}`.*

### 8. `GET /v1/images/{job_id}/content`
Retrieve binary image artifact bytes (`image/png`, `image/jpeg`, or `image/webp`).
- **Response**: `200 OK` (verified binary bytes, max 6 MB).

At most 64 gateway workspaces and 24-hour outputs are retained. Up to 10,000
durable ID/hash tombstones prevent old requests being silently executed after
pruning; new requests then fail capacity instead. Corrupt state fails closed.
Restarted in-flight work, timeout and ambiguous execution become `uncertain`;
they are not blindly resubmitted or routed to another image provider. Only
proven rejection (such as an explicit quota failure with no artifact) allows
fallback. Actual image dimensions may differ from the requested size upstream.

---

## Home Assistant Integration Setup

In Home Assistant:
1. Navigate to **Settings** -> **Devices & Services** -> **Family Assistant** -> **Configure**.
2. To use as an optional conversational/search provider:
   - Configure an **AGY** provider slot.
   - Set **URL** to `http://<host>:8080`.
   - Set **API Key** to your configured `AGY_API_KEY`.

Use the ordered Provider chain settings to enable/reorder AGY and Ollama text
providers; search is a separate opt-in. Image generation has its own optional
ordered chain, including ComfyUI. Saving an offline provider is allowed; Test
checks metadata without generating content. See [image generation](../../docs/image-generation.md)
for the current private-chat restriction and ComfyUI workflow prerequisites.
   - Set **Model** to one of the configured models (e.g. `gemini-3.8-flash-low`).
3. To use as an optional image provider:
   - Configure an **Image Generation** provider of type `agy_gateway`.
   - Set **URL** to `http://<host>:8080`.
   - Set **API Key** to your configured `AGY_API_KEY`.
