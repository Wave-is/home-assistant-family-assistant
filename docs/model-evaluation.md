# Opt-in live model contract evaluation

CI uses synthetic providers and never contacts a family's model. To assess an
explicitly chosen Ollama deployment, set process-local `FA_EVAL_URL` and
`FA_EVAL_MODEL` (optionally `FA_EVAL_API_KEY`) and run from this repository:

```text
python -m tools.evaluate_model --run-live
```

Use `--allow-http` only if you deliberately accept unencrypted transport to that
provider. No endpoint/model/key is built in. `--case ru_points` selects a named
case; omit it for the fixed bounded suite. The script has no HA configuration,
credential-file, source-export, user-prompt or external-dataset loader. It sends
only checked-in fictional members and records. Model-generated commands are
simulated using the real Engine on fresh in-memory state, never on HA.

Results contain case IDs, languages, outcome codes, elapsed seconds and a
content-free shape of known response fields. Unknown model field names, response
text, URLs, prompts, tokens and household records are not printed. The provider
has a 45-second request ceiling; a timeout is a result, not a successful test.

The suite covers multilingual presence checks, reading point reasons, separate
weekday/weekend alarm commands, a receipt-backed task deadline, an untrusted quote,
partial-shopping completion, child award denial and separate answer-only quote
discussion/injection cases. It exercises direct inference
and plan/domain validation, **not the entire deterministic-first router**, live
Telegram delivery or real devices. In particular normal `/ping`/«ты тут»/«ти тут»
already have a no-model path. The child award case evaluates the safety boundary;
it does not certify every word of a model's refusal. A `pass` on an answer case
means a valid answer envelope, not a comprehensive language-quality judgment.

Model-generated writes still need a real user's confirmation in the application.
A passing finite sample is not proof of reliable language understanding or immunity
to every prompt injection. Keep failures visible and repeat after schema/prompt or
model changes. Never replace current authority/role/revision checks with an LLM score.

## Development observations, 2026-09-07

A user-authorized Qwen3.5-9B Q5_K_M deployment was tested with fictional fixtures
only. The published alpha.3 schema passed only 3 of the initial 10 cases: it allowed
extra envelope fields that strict server validation rejected, and did not reliably
produce action arrays. Exact per-kind schemas improved the same sample to 6/10.
Forcing commands in a narrow experiment worked, but forcing that branch globally
would incorrectly turn ordinary conversation into action proposals and is not used.

The tested provider emitted the command array before `kind` when the schema field
was called `commands`. Changing the wire field to `operations` keeps `kind` first
even with alphabetically ordered properties; real mutation cases then produced
commands without forcing the kind. This is an observation of this deployment,
not a guarantee about every provider. Payload extensibility is explicit because
the [llama.cpp JSON grammar converter](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md#json-schemas--gbnf)
has a different default for additional properties than JSON Schema.

The newly reachable alarm path exposed Sunday-first numeric indexing, then translated
source phrases. Deterministic weekday parsing plus literal per-request choices fixed
those cases. A later 9/10 run exposed a quote injection producing an unwanted plan.
Raw quotes were consequently removed from planning and routed to a separate
answer-only pass. The original ten cases then passed together; two additional
quote-pass cases were added instead of hiding the earlier failure.
The complete extended 12-case Qwen3.5-9B run then passed; observed request times
in that warm run were 1.8–5.4 seconds. Cold/loading latency was higher in earlier
runs and is not excluded from the tool's reported elapsed time.

These are finite contract/intent checks, not a general model-quality benchmark.
First-request loading time varied materially. No live household data, bot or device
was used, and no production model configuration was changed.

The same deployment's `qwen3-vl:4b` returned empty final message content for all 12
cases with the current adapter parameters. This is 0/12, **not accepted** for this
configuration. A direct synthetic check returned HTTP 200 with an empty `content`
field; HTTP success alone is therefore not treated as a usable model response.
The adapter does not reinterpret a model's thinking field as an executable answer.
