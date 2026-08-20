---
title: Configuration
description: Configure attacker, target and judge profiles without committing secrets.
sidebar:
  order: 2
---

Copy the example file and keep the local result outside version control:

```bash
cp config.example.toml config.toml
wallbreaker check
```

A minimal fictional configuration separates the attacker profile, target and judge:

```toml
default_profile = "attacker"

[profiles.attacker]
protocol = "openai"
base_url = "https://attacker.example.invalid/v1"
api_key = "replace-locally"
model = "fictional-attacker"

[target]
protocol = "openai"
base_url = "https://target.example.invalid/v1"
api_key = "replace-locally"
model = "fictional-target"

[judge]
protocol = "openai"
base_url = "https://judge.example.invalid/v1"
api_key = "replace-locally"
model = "fictional-judge"
```

`wallbreaker check` validates the selected profiles, credentials, target and judge before a run.
Provider calls occur only when you invoke or configure an operation that uses them.

## Local state

The repository ignores `config.toml`, session logs, reports, images, evidence sidecars and generated
artifacts. Ignoring a file does not encrypt it. Store engagement data on a filesystem with access
controls appropriate to its sensitivity and remove it according to your retention policy.

## Optional integrations

- MCP servers are explicit `[[mcp.servers]]` entries and start only when enabled.
- P4RS3LT0NGV3 can run as native tools or as an out-of-process MCP server.
- External datasets and prompt corpora are optional and not downloaded unless requested.
- Hermes targets require a dedicated checkout, interpreter, closed manifest and provider credential
  environment variable. Continue with [Hermes Native Laboratory](/wallbreaker-hermes/guides/hermes-laboratory/).
