---
name: wallbreaker-campaign-setup
description: Prepare Wallbreaker Hermes campaign artifacts.
version: 0.5.0
author: Yivas
license: AGPL-3.0-or-later
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [security, red-team, evaluation, wallbreaker]
    related_skills: [wallbreaker-hermes]
---

# Wallbreaker campaign setup

Use this skill to prepare explicitly requested fictional campaign artifacts or diagnose a
Wallbreaker Hermes setup problem. Load `wallbreaker-hermes` too: it owns authorization,
execution, private review, verification, and the fixed target baseline. Keep the usual Hermes
as coordinator and a separate target; the laboratory is not an operating-system sandbox.

## Start with the measurement

Establish what the operator wants to measure before proposing models, paid probes, or a benchmark.
Reuse the current task's decisions; answer informational questions in prose, not approval menus.
Preparation does not authorize inference, runtime patches, or changes to existing review decisions.

The stock text judge scores harmful usefulness, not general instruction following. Its `REFUSED`
label can mean absence of usable harmful content; it does not necessarily describe rejection of a
benign request. Behavior expectations, judge labels, state evidence, and tool attempts are separate
signals. Agreement between judge and heuristic does not establish that either measures the intended
property. Explain a rubric mismatch and obtain a decision before changing evaluation semantics.
Do not change `allow` to `context_dependent`, remove controls, or reinterpret findings simply to
make a campaign pass. A small smoke test measures its own samples, not universal judge reliability.

## Prepare only the needed artifacts

1. Check the installed CLI version and its local `hermes --help` against this source's contract.
   A skill update does not update the package or remove local modifications. Stop on a material
   mismatch; do not repair the installation without a separate maintenance authorization.
2. Read [Preparing campaign artifacts](references/preparing-campaign-artifacts.md). For a new
   proposal, copy these fictional skeletons into the operator-approved artifact directory:
   - [Suite](templates/lab-suite.yaml)
   - [Configuration](templates/lab-config.toml)
   - [Manifest](templates/lab-manifest.json)
   Replace placeholders only with approved, non-secret choices. Do not open an existing private
   suite, operational config, context file, or evidence body to populate them.
3. Keep credentials out of the conversation and these files. The operator provisions an isolated
   campaign environment, never the coordinator's credentials. The campaign CLI does not load dotenv.
   Keep the same `WALLBREAKER_HERMES_EVIDENCE_KEY` for planning, execution, resume, and private review;
   offline structural verification does not require that key.
4. Select limits and identify attacker, target, and effective judge endpoints. Without an explicit
   judge, the default profile is used: its calls are not free or absent. Distinguish request caps
   from cost estimates; include input/output tokens, judge calls, and any separately approved retries
   or probes. Mark unknown prices or usage as unknown rather than inventing a precise total.
5. Use the operator skill's dry-run/exact-plan workflow from `wallbreaker-hermes`. Present the actual
   `plan.validated` limits before asking for execution approval. A valid plan creates no campaign
   report, provider request, or target replica, but does run local validation processes. It does
   not test model availability, calibrate the judge, or guarantee future execution.

## Diagnose without expanding the task

Read [Diagnosing harness failures](references/diagnosing-harness-failures.md) only when needed.
Begin with the authorized error output, installed source, and synthetic offline tests. Preserve
failed reports and locks; a later validation error does not prove every earlier property passed.
State what is confirmed and what still needs evidence. Do not launch direct provider calls,
regenerate private prompts, or patch runtime code to make diagnostics easier.

A live probe or evaluator change is a separate proposal with purpose, inputs, models, limits,
cost, acceptance criteria, and explicit authorization. It is not covered by an old campaign token.
Do not create helper scripts or a new evaluator unless requested.

## Maintain one source

Install both skills from the public integration and keep local files byte-identical to that source.
No private paths, incident reports, package patches, measured provider results, or local helpers
belong here. Preserve access controls during authorized updates; do not disable them to install.
Start a new conversation if an older skill was already loaded. A skill change alone does not require
another Hermes installation or a gateway restart.
