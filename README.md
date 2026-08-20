# Wallbreaker Hermes

[![Red-team gate](https://github.com/Yivas/wallbreaker-hermes/actions/workflows/redteam-gate.yml/badge.svg)](https://github.com/Yivas/wallbreaker-hermes/actions/workflows/redteam-gate.yml)
[![PyPI](https://img.shields.io/pypi/v/wallbreaker-hermes)](https://pypi.org/project/wallbreaker-hermes/)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)

Wallbreaker Hermes is an AGPL-licensed fork of
[Wallbreaker](https://github.com/JailbrokenAI/wallbreaker) for authorized LLM red-teaming. It
keeps the standard Wallbreaker harness and adds an opt-in native laboratory for testing a fixed,
ephemeral Hermes Agent target.

[Documentation](https://yivas.github.io/wallbreaker-hermes/) ·
[PyPI](https://pypi.org/project/wallbreaker-hermes/) ·
[Releases](https://github.com/Yivas/wallbreaker-hermes/releases) ·
[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

## Scope and status

- **Current release:** `v0.3.1` / `wallbreaker-hermes==0.3.1`.
- **Python:** 3.11 or newer.
- **Project mode:** open source collaborative. In-scope issues and pull requests are welcome.
- **Hermes baseline:** Hermes Agent `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`.

The standard CLI, TUI, dashboard, provider layer, attack tools, judge, reports and reliability
checks remain available. The Hermes laboratory supports one text turn against a clean home or a
selected, sanitized context. It rejects target tools, MCP, custom prompt layers, profiles, prefill,
continuation and multimodal input.

The laboratory is **not an operating-system sandbox**. Its child process retains the filesystem and
network permissions of the account that runs it.

## Install

Install the published package:

```bash
python -m pip install wallbreaker-hermes==0.3.1
wallbreaker --help
```

The distribution name is `wallbreaker-hermes`. The import package and commands remain
`wallbreaker` and `wb` for compatibility with upstream.

For development:

```bash
git clone https://github.com/Yivas/wallbreaker-hermes.git
cd wallbreaker-hermes
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
```

On Windows PowerShell, activate the environment with `.\.venv\Scripts\Activate.ps1`.

## First use

Copy the example configuration, add credentials for providers you are authorized to use, then run
the preflight check:

```bash
cp config.example.toml config.toml
wallbreaker check
wallbreaker
```

`config.toml` is ignored by Git. Do not commit credentials, prompts, responses, reports, session
state or generated evidence.

Common entry points:

```bash
wallbreaker                         # terminal UI
wallbreaker dashboard               # local dashboard on 127.0.0.1:8787
wallbreaker --auto "objective..."   # autonomous loop against the configured target
wallbreaker report                  # render the latest local run
wallbreaker hermes --help           # Hermes laboratory workflow
```

See the [installation guide](https://yivas.github.io/wallbreaker-hermes/getting-started/installation-and-setup/)
and [configuration guide](https://yivas.github.io/wallbreaker-hermes/getting-started/configuration/)
for provider, dashboard and platform details.

## Main capabilities

- OpenAI Chat Completions and Anthropic Messages provider normalization.
- Interactive and autonomous attack workflows with operator pause and explicit finish controls.
- HarmBench-backed evaluation, LLM judging and repeated reliability checks.
- Transform, preset, persona, multimodal, campaign and report tooling inherited from Wallbreaker.
- Optional P4RS3LT0NGV3 integration and generic MCP client support.
- Local FastAPI and React/Vite dashboard using the same application services as the TUI.
- Opt-in Hermes Agent laboratory with clean replicas, closed manifests, state comparison and
  permission-restricted evidence for local human review.

The documentation describes each capability without relying on private prompts, operational
profiles or unpublished corpora.

## Security and privacy

Use Wallbreaker Hermes only against systems you own or have explicit permission to test. Provider
calls, target calls, judge calls and requested dataset updates can use the network. Run logs and
reports may contain sensitive or harmful material even though their default locations are ignored
by Git.

The Hermes campaign report is sanitized. When human review is required, prompt and response bodies
are stored separately in a local permission-restricted sidecar. Hermes Agent does not receive or
open that evidence.

Read [SECURITY.md](SECURITY.md) before exposing the dashboard, running untrusted targets or sharing
artifacts. Report vulnerabilities through GitHub Private Vulnerability Reporting, not a public
issue.

## Documentation

The maintained documentation is published at
<https://yivas.github.io/wallbreaker-hermes/>. Source files live under `wiki/`.

Repository-level references remain under [`docs/`](docs/README.md), including external-data
attribution and examples that must stay close to the code. The operator integration and skill live
under [`integrations/hermes/`](integrations/hermes/README.md).

## Support and contributing

Use [GitHub Issues](https://github.com/Yivas/wallbreaker-hermes/issues) for reproducible bugs and
scoped proposals. Pull requests are reviewed when they fit the project, preserve upstream
compatibility and include the relevant tests and documentation. The project does not promise a
response time or support for unauthorized testing.

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before opening a
pull request.

## License and upstream

Wallbreaker Hermes is licensed under [AGPL-3.0-or-later](LICENSE). Modified versions, including
versions offered over a network, must provide their complete corresponding source under the same
license.

This repository preserves the Wallbreaker history and attribution. Third-party datasets and prompt
corpora are not bundled automatically; their provenance and terms are documented in [NOTICE](NOTICE)
and the [external-data reference](docs/EXTERNAL_DATA.md).
