# Optional provider chains

Family Assistant works without a language model or image generator. Keep the
corresponding switch off, or save an empty language-provider list, to use ordinary
bot commands without LLM inference. A configured provider is an explicit choice;
no AGY account, Qwen model, GPU, external search service or powered-on PC is required.

Open the integration's **Configure → AI & Assistant** menu. **Language provider
chain** and **Image generation** are separate settings. Each supports zero to
eight ordered providers with a display name, individual enabled switch, edit,
move earlier/later, remove and explicit connection test. The solid/hollow dots
mean enabled/disabled, not healthy/unhealthy.

Changes stay in the current native Options flow as a server-side draft until
**Save** on the chain's main form. Saving a row only stages that row. **Back**
does not apply the current form; **Cancel chain draft** discards all staged
changes. Closing a flow does not persist or automatically resume its draft.
Removing a row requires confirmation, then the chain still needs saving. Family
records and previous task/image results are not deleted by removing a provider.

Only the currently authorized owner can configure a chain. A changed owner,
member identity, loaded entry, backup state or concurrent Options edit invalidates
the old flow, including responses arriving after a connection test.

## Language models

One possible order is your NAS AGY gateway, one Ollama/Qwen server, then another
Ollama/Qwen server. This is an example, not three mandatory slots. You can use a
single provider, a different order or none.

1. Choose **Add provider**, then its protocol: **AGY (Ollama API)**, **Ollama /
   Qwen**, or the separately configured **Home Assistant** agent.
2. For HTTP providers, enter a display name and the base URL reachable from the
   Home Assistant container. Do not enter a `/api/chat` or `/api/tags` URL; the
   adapter appends its own route. Enter your key in the password field if needed.
3. If the model name is unknown, leave the row disabled and model blank, stage
   it, select it in the list and choose **Test connection / list models**. Return
   with **Back**, then **Edit** to choose an installed model or type its exact
   name. A successful metadata check does not run inference or guarantee that a
   later request will succeed.
4. Enable the desired rows, arrange their order, enable the chain and save it.
   Saving uses local validation only; an offline but valid endpoint remains
   configurable. Provider failures are handled at request time, not disguised
   as a successful connection test.

AGY here means an explicitly configured gateway implementing the observed
Ollama-compatible metadata/chat API, not a command executed on a developer PC.
The integration does not install a gateway or authenticate an AGY account for
you. Ollama/Qwen rows must implement that API; an arbitrary OpenAI-compatible
endpoint is not interchangeable with it.

The existing HA agent is configured and reviewed separately. Adding its reference
to the chain does not grant new HA tools or copy that agent's credentials.

The legacy two-slot Ollama form remains available for compatibility. Until a
chain is explicitly saved, legacy AGY, HA-agent, primary and fallback settings
are read in their prior order. Once the `providers` list exists, it is
authoritative—even when empty. Old slots remain stored and are not silently
reactivated when every new row is disabled or removed.

## Search is separate from inference

AGY rows have an off-by-default switch for explicit adult web searches. Enable it
only if that gateway supports the versioned search-evidence protocol; ordinary
model prose saying it searched is not evidence of a search. The existing SearXNG
settings remain a separate optional source/fallback. Child callers cannot obtain
adult search authority by selecting a different inference model. A metadata/model
test is not a search-capability test.

## Optional images and an offline ComfyUI PC

An example image order is **AGY Images API v1 → ComfyUI**. The text AGY protocol
alone does not establish image support: choose an image gateway implementing the
separate image-job protocol. ComfyUI must be reachable from Home Assistant and
already have the selected models installed.

Add the connection disabled if necessary, then use the explicit metadata test to
discover its installed models. The integration never downloads models, powers on
the PC or starts image generation during configuration. An empty model list is a
real missing setup step, not a reason to select a fabricated model name.

ComfyUI offers two built-in presets:

- **Checkpoint**: choose an installed checkpoint; normal text-to-image defaults
  are configurable, including a negative prompt.
- **Z-Image Turbo**: select the installed diffusion model, text encoder and VAE.
  In **Image defaults**, explicitly select **8 steps and CFG 1**. This preset
  ignores the negative prompt. Required model families and installation details
  are described in the [official ComfyUI tutorial](https://docs.comfy.org/tutorials/image/z-image/z-image-turbo).

The integration supports these bounded presets, not arbitrary workflow JSON,
custom-node installation, ControlNet or image-to-image graphs. Width and height
are each 512, 768 or 1024; steps are 1–50 and CFG is 1–20. Settings accepted by the
form still need hardware/model acceptance for your selected workflow. ComfyUI's
[official server routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
separate metadata, submission, history and image retrieval; a metadata response
is not an image result.

An offline optional image server must not block ordinary text commands. Fallback
does not mean blindly generating another image after an uncertain submission:
accepted/uncertain jobs keep their own identity and must be resolved according to
their status. The UI must not claim success merely because a job was queued.

The control panel's **Connections** section shows optional image settings and
adapter initialization separately. Initialization is not a live reachability
test. A reported provider failure is shown locally without adding a required
image capability to household readiness. Its configuration link opens the native
integration settings; the actual Options forms own editing and metadata tests.

## Credentials and transport

URLs, model selections and keys remain in that household's private Config Entry
Options. Keys are never filled into visible form defaults. A blank password field
keeps the old key; **Clear saved API key** removes it. Changing the endpoint while
retaining a key is rejected unless you enter a new key or explicitly clear the
old one. Disabling a provider does not erase its connection draft or key.

Use HTTPS where available. HTTP requires explicit consent for that configured
endpoint and exposes its traffic to the network path. Do not place credentials in
URLs or expose Home Assistant, private gateways or ComfyUI directly to the public
internet. This feature does not supply or request household credentials in the
public repository.

## Verification boundary

`test_provider_chain_options.py` covers native form defaults and owner/Options
fences with synthetic metadata. `ha_provider_chain_smoke.py` exercises authenticated
HA Options schemas, commits, reload and synthetic provider ordering when run by
the isolated HA settings acceptance case. Neither establishes real GPU output,
an external account's quota or a household network's reachability. Browser card
coverage is a separate gate; this native form implementation is not a replacement
for Home Assistant's own frontend.
