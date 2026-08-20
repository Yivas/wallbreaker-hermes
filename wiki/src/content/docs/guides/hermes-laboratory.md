---
title: Hermes Native Laboratory
description: Configure the fixed, ephemeral Hermes Agent target without claiming OS sandboxing.
sidebar:
  order: 2
---

The Hermes laboratory is an opt-in target that starts a native Hermes Agent child process against an
ephemeral copy of an approved home. It is validated against:

| Component | Baseline |
|-|-|
| Hermes Agent tag | `v2026.8.13` |
| Package version | `0.20.1` |
| Commit | `f80f453ae0679347e38abc917c7f94f717bf96c5` |

## What the laboratory enforces

- A dedicated checkout and interpreter.
- A clean home or an explicitly selected, sanitized context.
- A closed manifest of copied files.
- No target tools or MCP servers.
- No custom system or developer prompt layers, profiles, prefills or continuation.
- One text turn per fresh replica.
- State comparison before and after each repetition.
- Cleanup of the replica on success, failure, timeout and interruption.

## What it does not enforce

The child process keeps the operating-system permissions of the account that launches it. The
laboratory does not restrict filesystem or network access at the operating-system level. Run it
under a separate account, container or virtual machine when the target requires stronger isolation.

## Preflight

The preflight resolves the target checkout, interpreter, Hermes baseline, manifest and provider
configuration. It rejects unexpected runtime files, tools, MCP, prompt layers and mutable scope
before sending a turn.

Read the detailed repository contract in
[`docs/HERMES_LAB.md`](https://github.com/Yivas/wallbreaker-hermes/blob/main/docs/HERMES_LAB.md)
before changing the manifest or supported baseline.
