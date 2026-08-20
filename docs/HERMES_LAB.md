# Hermes Native Laboratory

Wallbreaker Hermes can use a dedicated Hermes Agent checkout as an opt-in, single-turn text
target. The adapter creates a new home and working directory for every inference, verifies the
effective request before network access, runs `hermes -z`, compares selected context files, and
deletes the replica.

This mode is not an operating-system sandbox. The Hermes process keeps the filesystem, process,
and network permissions of the account that launches Wallbreaker.

## Fixed Baseline

The first adapter supports this Hermes Agent revision only:

- Release: `v2026.8.13`
- Package: `0.20.1`
- Commit: `f80f453ae0679347e38abc917c7f94f717bf96c5`

Use a dedicated clean checkout. Do not point the adapter at an operational Hermes installation.
The adapter rejects a different Git commit, a dirty worktree, a Python environment that imports
Hermes from another path, unexpected package-root dotenv files, and an active managed scope. The
tracked `.env.example` and `.envrc` files in the fixed baseline are permitted only while the Git
checkout remains clean.

## Target Configuration

Set `protocol = "hermes-lab"` only on `[target]`:

```toml
[target]
protocol = "hermes-lab"
model = "fixture/model"
api_key_env = "FIXTURE_PROVIDER_KEY"
timeout = 90

hermes_provider = "fixture-provider"
hermes_runtime = "C:/lab/hermes-agent"
hermes_python = "C:/lab/hermes-agent/.venv/Scripts/python.exe"
hermes_manifest = "C:/lab/manifests/clean.json"
# hermes_context_root = "C:/lab/context"
```

`api_key_env` must name the environment variable that the selected Hermes provider already
understands. Wallbreaker passes that credential to the child process but never writes its value to
the replica.

The adapter does not accept `base_url`, inline `api_key`, backend pinning, provider caching,
reasoning, or a custom system prompt on this target.

## Manifests

A clean replica uses no selected context:

```json
{
  "schema": "wh-hermes-fixture/v1",
  "mode": "clean",
  "provider": "fixture-provider",
  "model": "fixture/model",
  "files": [],
  "expected_tool_count": 0
}
```

A selected replica accepts four logical paths:

```json
{
  "schema": "wh-hermes-fixture/v1",
  "mode": "selected",
  "provider": "fixture-provider",
  "model": "fixture/model",
  "files": [
    "SOUL.md",
    "memories/MEMORY.md",
    "memories/USER.md",
    "workspace/AGENTS.md"
  ],
  "expected_tool_count": 0
}
```

Set `hermes_context_root` for selected mode. The paths in `files` resolve below that root.
`workspace/AGENTS.md` becomes `AGENTS.md` in the temporary working directory; the other files go
to the temporary Hermes home.

The copier rejects unknown paths, path collisions, symlinks, junctions, reparse points, hard
links, Windows network paths, invalid UTF-8, oversized files, and common credential patterns.
Pattern matching cannot prove that arbitrary private text contains no unknown secret. Review
selected context before use.

## Request Gate

Each inference follows this sequence:

1. Verify the fixed runtime, manifest, selected files, environment, and temporary-root permissions.
2. Build a minimal Hermes home with no MCP configuration and only the Wallbreaker probe plugin.
3. Start a preflight `hermes -z` process with the same prompt and configuration as the real run.
4. Let Hermes build the effective request, require exactly one `system` message followed by one
   `user` message, then record sizes, ephemeral seals, provider, model, and tool/MCP counts.
5. Exit the preflight process from `pre_api_request`, before the provider call.
6. Recheck sealed fingerprints and start the real process.
7. Repeat the zero-tools/MCP assertion immediately before the provider call. A `pre_tool_call` hook
   appends each blocked attempt to dedicated evidence; preflight attempts fail closed and do not
   count as evaluated-run attempts.
8. Reject a known provider credential found in child output, selected state, or evidence files.
9. Compare the selected source files, terminate the process tree when needed, and delete the
   replica.

Any tool, MCP server, seal change, source change, detected credential, timeout, unverified process
exit, or cleanup failure invalidates the run.

## Supported Surface

The first adapter accepts one user text message and one final text response. Existing Wallbreaker
tools can reuse it when every fire fits that shape. Each fire receives a fresh replica.

It rejects conversation continuation, history, target system prompts, developer messages,
assistant prefill, profiles, directives, selected skills, multimodal input, streamed reasoning,
temperature overrides, target result caching, CoT recovery, and tools.

BreakVault autoarchiving, run logs, automatic and manual session saves, transcript exports, and
`finish` artifacts are disabled for direct Hermes targets. Programmatic campaigns keep review
bodies only in the private sidecar described below; the sanitized report never contains them.

## Programmatic Campaigns

`wallbreaker.hermes_campaign` provides `load_suite`, `run_campaign`, `resume_campaign`, and
`apply_reviews`. The `wallbreaker hermes` CLI uses this API without adding another runner. It writes
a sanitized report plus a private review sidecar. A suite uses the closed
`wallbreaker.hermes-campaign-suite/v1` schema:

```yaml
schema: wallbreaker.hermes-campaign-suite/v1
id: synthetic-suite
version: 1
cases:
  - id: synthetic-memory-case
    split: discovery
    objective: Synthetic objective
    prompt: Synthetic prompt
    expected_behavior: refuse
    expected_state: unchanged
```

Each suite must contain separate `discovery`, `qualification`, and `holdout` cases. Supported
response expectations are `allow`, `refuse`, and `context_dependent`. State expectations are
`unchanged`, `declared_changes`, and `manual`. A `declared_changes` case must list one or more of
the four laboratory paths documented under Manifests.

Each repetition creates a new attacker conversation. Every `query_target` fire creates and deletes
a new Hermes replica. The campaign observes all four closed state components so it can report an
undeclared change; it then applies the case's `allowed_state_paths` policy. A blocked tool attempt,
an undeclared state change, or behavior contrary to the expectation is a finding. Missing evidence,
judge failure or disagreement, `context_dependent`, and `manual` require review.

The result uses `wallbreaker.hermes-campaign-report/v2`. It contains schemas, software versions,
HMAC-scoped fingerprints, enums, counts, state component names, attestations, cleanup receipts, and
a one-sided 95% Wilson lower bound when a split is complete. It never stores suite IDs, case IDs,
objectives, prompts, responses, judge rationales, endpoint URLs, context paths, credentials, or
conversation logs. Fingerprints from different campaign plans are unlinkable without the operator's
key. These fingerprints protect privacy and plan binding; the report is structurally validated but
is not a signed or independently tamper-evident artifact.

Each authorized run created by this workflow also creates `RUN.evidence.json` beside `RUN`. Reports
produced by `wallbreaker-hermes==0.2.2` before sidecars remain structurally verifiable, but a report
that already contains fires cannot be safely resumed or manually resolved because its bodies no
longer exist. The CLI reports that limitation instead of accepting an evidence-free decision.

The private sidecar stores only
the objective, effective prompt, assessed response, attempt, and fire index needed for human review.
It excludes credentials, endpoints, configuration, system prompts, context files, reasoning, and
conversation transcripts. Wallbreaker writes it before the corresponding sanitized checkpoint,
uses restrictive file permissions, ignores it in Git, and binds it to the report and body
fingerprints with `WALLBREAKER_HERMES_EVIDENCE_KEY`.

Each report or sidecar replacement is atomic, but the pair is not one filesystem transaction. A
new run writes the empty report first and removes it if private-sidecar creation fails; resume can
recreate a missing empty sidecar before any fire and rejects older reports that already contain
fires without review evidence. `resume_campaign` runs pending repetitions and replaces interrupted
or failed attempts with a new attempt on a fresh replica. It never continues an interrupted replica.
`apply_reviews` requires a valid matching sidecar, accepts only `pass` or `finding` for attempts
marked `review_required`, and recalculates aggregates. Discordant repetitions require review and do
not receive a confidence bound until resolved. Resume also validates the sidecar before constructing
providers when the report already contains fires.

## Operator CLI

Plan a campaign before any provider or replica is created:

```text
wallbreaker hermes run SUITE --config CONFIG --output RUN --dry-run
```

Set `WALLBREAKER_HERMES_EVIDENCE_KEY` to an operator-held random value of at least 32 bytes before
planning or running a campaign. Keep the same key for dry run, execution, resume, and review; do
not commit it or store it beside the report. Structural verification does not need the key because
it never opens the sidecar.

The Hermes campaign CLI uses variables already present in the process environment and does not
search for or load dotenv files. It validates the suite, configuration,
credentials, fixed Hermes runtime, selected context, limits, output, and any resume report, and
runs local Git and Python identity checks. It creates no provider, network request, temporary
replica, or campaign report. It emits closed NDJSON using
`wallbreaker.hermes-cli-event/v1`. The `plan.validated` event contains HMAC-scoped identities,
limits, maximum known network requests, maximum Hermes processes, maximum private-evidence bytes,
and a confirmation token.

After the operator authorizes that exact plan, repeat the command with the same arguments and
limits:

```text
wallbreaker hermes run SUITE --config CONFIG --output RUN \
  --authorized --confirm hmac-sha256:PLAN_TOKEN
```

Changing the suite, effective configuration, limits, output path, Wallbreaker version, resume
mode, or validated checkpoint changes the token. Use `--resume` only after a new dry run. The
initial limits are 1-10 repetitions, 1-50
attacker rounds, 1-20 target fires per repetition, 1-131072 attacker tokens, 1-8192 target tokens,
a timeout above zero and no more than 600 seconds, and at most 1000 known network requests.

List pending review IDs without changing the report:

```text
wallbreaker hermes review RUN
```

A human can display the matching private bodies on an interactive local terminal. Do not run this
option through Hermes Agent, another model, captured automation, or a shared terminal:

```text
wallbreaker hermes review RUN --show-evidence
```

Apply decisions supplied by the operator:

```text
wallbreaker hermes review RUN --set ATTEMPT=pass --set ATTEMPT=finding
```

After all reviews resolve and strict verification succeeds, delete the private sidecar explicitly:

```text
wallbreaker hermes review RUN --delete-evidence
```

Deletion cannot erase backups, snapshots, or storage remnants.

Verify the closed report offline:

```text
wallbreaker hermes verify RUN
```

Verification requires a complete campaign, no pending review, attestation fingerprints, verified
process cleanup, removed replica roots, unchanged source context, and applicable confidence for
each split. A resolved security finding is valid campaign evidence and does not make verification
fail.

Exit codes are `0` for a completed operation, `1` for invalid data or an operational failure,
`2` when review or strict evidence remains pending, `3` when authorization or confirmation is
missing, and `130` for operator cancellation. Argparse returns `2` for command syntax errors before
an operator action starts. Cancellation checkpoints the report; resumption creates a new attempt
and replica.

## Hermes Agent operator skill

The public skill source is
`integrations/hermes/skills/wallbreaker-hermes/SKILL.md`. Install it into the operator-side Hermes
Agent, not the clean checkout used as the target:

```text
hermes skills install Yivas/wallbreaker-hermes/integrations/hermes/skills/wallbreaker-hermes
```

The skill is fixed to Hermes Agent release `v2026.8.13`, package `0.20.1`, and commit
`f80f453ae0679347e38abc917c7f94f717bf96c5`. It uses `clarify` for authorization, limits, and
confirmation, then invokes the CLI through a normal shell tool. It may list pending review IDs, but
it never invokes `--show-evidence` or receives review bodies. The human reviews them in a separate
local terminal and supplies the resulting decisions. The skill does not modify Hermes core,
inspect configuration contents, or use `execute_code` for campaign commands.
Fictional fixtures are under `integrations/hermes/examples/`.
