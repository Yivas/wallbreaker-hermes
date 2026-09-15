# Preparing campaign artifacts

These fictional skeletons document the public Wallbreaker Hermes contract. They are not a live
campaign, a calibrated evaluation set, or proof that a provider supports the target baseline.

## Files and boundaries

Choose a new operator-approved directory outside the target checkout and operational Hermes home.
Keep suite, configuration, and manifest separate from private credentials and evidence. Do not
create a launcher or documentation bundle unless needed for the requested work.

The operator must provision a trusted campaign-only environment without exposing secrets to the
assistant. The `wallbreaker hermes` CLI uses the existing process environment; it does not discover
or load dotenv files. Do not use `wallbreaker check` as a substitute for campaign validation: other
subcommands may load dotenv and resolve a different environment. Do not source an untrusted script.

`WALLBREAKER_HERMES_EVIDENCE_KEY` must hold at least 32 bytes. Keep it stable through dry run, run,
resume, and private review, and separate from the report. Structural `verify` does not open the
sidecar and does not require this key. HMAC provides binding, not encryption.

## Suite

The closed `wallbreaker.hermes-campaign-suite/v1` schema has `schema`, `id`, `version: 1`, and
`cases`. Each case has `id`, `split`, `objective`, `prompt`, `expected_behavior`, and
`expected_state`, with optional `allowed_state_paths`.

- Include distinct `discovery`, `qualification`, and `holdout` cases; do not repeat the same
  objective/prompt pair across splits.
- Behavior: `allow`, `refuse`, or `context_dependent`. The last requires manual review by design.
- State: `unchanged`, `declared_changes`, or `manual`. Only `declared_changes` supplies
  `allowed_state_paths`, and it requires at least one supported path.
- Supported paths: `SOUL.md`, `memories/MEMORY.md`, `memories/USER.md`, `workspace/AGENTS.md`.
- Preserve the intended expectations. The included examples exercise the schema, not judge accuracy.

The loader checks UTF-8, size and case limits, unique IDs, closed fields, and YAML restrictions.
Use its validation rather than assuming that syntactically valid YAML satisfies the schema.

## Configuration and manifest

`default_profile` names the attacker profile. The template's `.invalid` endpoint and fictional model
are placeholders, not usable defaults. Choose the actual protocol, model, and credential-variable
name explicitly. An optional `[judge]` selects a judge; otherwise the default profile is used.
A custom judge system prompt is prepended to the stock system prompt, not a replacement for its
rubric. Changing that setting cannot by itself establish semantic compatibility or valid JSON.

`[target]` uses `protocol = "hermes-lab"`, `model`, `api_key_env`, `hermes_provider`,
`hermes_runtime`, `hermes_python`, and `hermes_manifest`. Runtime and Python must be absolute paths
inside the same dedicated pinned checkout; choose the interpreter path for the host OS.
`api_key_env` must name the variable the chosen Hermes provider actually understands. A placeholder
variable is not a credential configuration. Do not set target `base_url`, inline credentials,
backend pinning, caching, reasoning, or a custom system prompt.

The manifest uses `wh-hermes-fixture/v1`, and its provider/model must match the target. Keep
`expected_tool_count: 0`. `clean` has empty `files`; `selected` has explicitly approved files from
the four supported paths and needs `hermes_context_root`. Do not silently switch modes to work
around a validation error. Never select the coordinator's home or copy its state. File scanning
does not prove arbitrary context is secret-free.

## Limits and validation

Use the installed CLI help for supported flags and ranges. Every case/repetition has its own
attacker conversation and fire budget; each target fire uses a fresh replica. The judge also
consumes requests. Read maximum requests, Hermes processes, and evidence bytes from `plan.validated`
instead of maintaining a second budgeting formula here.

Carry every chosen limit into both dry run and execution. Changed inputs, resolved credentials,
limits, output, version, or resume state require another dry run and exact-plan approval.
A validation error proves that check failed; it is not proof of the full preceding execution path.
A valid dry run proves only its documented local checks, not provider availability or measurement
quality. Never run a paid smoke test implicitly to fill that gap.
