---
name: wallbreaker-hermes
description: Operate authorized Wallbreaker Hermes campaigns.
version: 0.3.1
author: Yivas
license: AGPL-3.0-or-later
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [security, red-team, evaluation, wallbreaker]
    related_skills: []
---

# Wallbreaker Hermes

Operate Wallbreaker Hermes campaigns against a fixed, ephemeral Hermes Agent laboratory target.
The laboratory is not an operating-system sandbox.

## When to use

Load this skill when an operator asks to plan, run, resume, review, or verify a Wallbreaker Hermes
campaign. Use it only for systems the operator is authorized to test.

## Required checks

Before any live command, use `clarify` to obtain all of these decisions:

- Explicit authorization for the named target and suite.
- Suite path and Wallbreaker config path.
- Report output path.
- New run or resume.
- Repetitions, rounds, fire cap, token limits, and timeout.
- Confirmation that strict cleanup and review evidence are required.

A vague request, filesystem access, or possession of credentials does not establish authorization.
Stop if authorization is absent or denied.

## Procedure

1. Check that `wallbreaker` is installed and that the operator-side Hermes Agent release is
   `v2026.8.13`. Wallbreaker validates package `0.20.1` and commit
   `f80f453ae0679347e38abc917c7f94f717bf96c5` for the separate target checkout.
2. Use the normal shell or terminal tool to run the dry run. Never use `execute_code` for these
   commands.

   ```text
   wallbreaker hermes run SUITE --config CONFIG --output RUN --dry-run
   ```

3. Read the `plan.validated` NDJSON event. Present its limits, maximum network requests, maximum
   Hermes processes, maximum private-evidence bytes, artifact path, and confirmation token to the
   operator.
4. Use `clarify` again. Ask whether the operator authorizes that exact plan. If any input changes,
   discard the token and repeat the dry run.
5. After an affirmative answer, run the same command with the same limits, replacing `--dry-run`
   with:

   ```text
   --authorized --confirm TOKEN
   ```

6. If the command exits `2`, list pending review IDs without guessing decisions:

   ```text
   wallbreaker hermes review RUN
   ```

   Tell the operator to inspect the private evidence in a separate local terminal with
   `wallbreaker hermes review RUN --show-evidence`. Never invoke that option through a Hermes tool
   or ask the operator to paste bodies into the conversation. Use `clarify` only after the operator
   has reviewed the evidence, then apply the `pass` or `finding` decisions they supply:

   ```text
   wallbreaker hermes review RUN --set ATTEMPT=pass
   ```

7. Finish with:

   ```text
   wallbreaker hermes verify RUN
   ```

   Do not declare success unless verification exits `0`.

## Safety boundaries

- Do not read, print, copy, or modify credentials, `.env` files, SOUL, memories, conversations,
  prompts, responses, profiles, endpoints, or operational Hermes configuration.
- Pass operator-supplied paths to Wallbreaker without opening their contents.
- Never invoke `--show-evidence`, open `RUN.evidence.json`, or reproduce private review bodies.
- Do not install this skill into the clean Hermes checkout used as the target.
- Do not modify Hermes core, the source home, the ephemeral replica, or campaign JSON by hand.
- Do not treat a security finding as a harness failure. Report findings and their aggregate counts.
- On cancellation, report the existing RUN path. Resume only after a new dry run and exact-plan
  authorization.

## Exit codes

| Code | Meaning |
|-:|-|
| `0` | Plan, campaign, review, or verification completed |
| `1` | Invalid input, runtime, report, or execution |
| `2` | Review or strict evidence remains pending |
| `3` | Authorization or confirmation is missing |
| `130` | Operator cancelled the command |

Argparse also returns `2` for malformed command syntax before the workflow starts. Treat its stderr
as a syntax error, not pending review.

## Verification

A completed workflow has a `wallbreaker.hermes-campaign-report/v2` artifact, no pending review,
and verified attestation and cleanup evidence. The operator may delete `RUN.evidence.json` with
`wallbreaker hermes review RUN --delete-evidence` after verification. Keep the report path; do not
reproduce report or sidecar contents outside the operator's requested destination.
