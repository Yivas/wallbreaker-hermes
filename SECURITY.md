# Security & Responsible Use

Wallbreaker Hermes is an AGPL-licensed fork of Wallbreaker. It is an **offensive security
research tool** for red-teaming and safety
evaluation of large language models. It exists so defenders, alignment researchers,
and model providers can find and fix weaknesses before adversaries exploit them.

## Authorized use only

Use Wallbreaker **only** against:

- models and endpoints you own or operate, or
- targets you have **explicit written authorization** to test (e.g. a provider's
  red-team program, a bug-bounty scope, an internal evaluation).

Do **not** use it to attack third-party services without permission, to generate or
distribute genuinely harmful operational content, or in any way that violates the
target provider's terms of service or applicable law. You are responsible for how you
use it.

## What the tool produces

Wallbreaker generates adversarial prompts and records model responses for evaluation.
Run logs, findings, and generated artifacts can contain sensitive or harmful material.
They are written to `wb_runs/`, `wb_images/`, `wb_artifacts/`, and `findings/`, all of
which are **gitignored** — keep them out of version control and handle them as
sensitive data.

## Hermes runtime mode

The planned Hermes mode will run only against an ephemeral, explicitly authorized target home.
It must exclude credentials, sessions, channels, logs, caches, and real gateway state; constrain
filesystem, tools, and network; compare state before and after each repetition; and destroy the
sandbox on every exit path. Until those controls ship and are verified, do not treat a copied
Hermes directory as a security sandbox.

## Reporting a vulnerability in Wallbreaker Hermes itself

If you find a security issue in the harness (e.g. a sandbox-escape in `run_shell`, a
secret-leak path, an unsafe default), please open a private report rather than a public
issue: use GitHub's **"Report a vulnerability"** (Security Advisories) on the repository,
or contact the maintainers listed in the org. Include repro steps and impact.

## Handling model-provider system prompts

`leak_scan` and related tools may surface a target's hidden system prompt. Treat any
extracted prompt as the provider's confidential material — report it through their
responsible-disclosure channel; do not publish it.
