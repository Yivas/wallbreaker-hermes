# Repository documentation

The maintained user documentation is published at
<https://yivas.github.io/wallbreaker-hermes/>. Its source lives under [`wiki/`](../wiki/).

This directory keeps references that need to remain beside the source tree or distribution process.

| Document | Purpose | Authority |
|-|-|-|
| [`EXTERNAL_DATA.md`](EXTERNAL_DATA.md) | Optional data sources, provenance and licenses | Data acquisition and redistribution boundaries |
| [`HERMES_LAB.md`](HERMES_LAB.md) | Detailed Hermes laboratory contract | Public implementation contract for the fixed baseline |
| [`SETUP.md`](SETUP.md) | Cross-platform development notes | Repository development reference |
| [`UPSTREAM.md`](UPSTREAM.md) | Fork update and rollback procedure | Upstream maintenance procedure |
| [`mcp-integration.md`](mcp-integration.md) | MCP integration details | MCP operator reference |
| [`examples/redteam-gate.yml`](examples/redteam-gate.yml) | Opt-in live workflow example | Example only; never runs from this repository's Actions |

The files `persona_spec.md`, `reasoning_token_visibility_methods.md`, and
`mcp_client_config.json` are technical references for specialized maintainers. They are not required
for installation and are not a source of operational prompts or active configuration.

When user-facing behavior changes, update the wiki first and keep repository references consistent.
Do not add credentials, prompts, responses, profiles, session identifiers, endpoints, run logs or
private evidence to this directory.
