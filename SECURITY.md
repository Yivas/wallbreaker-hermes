# Security policy and responsible use

Wallbreaker Hermes is an offensive security research tool for authorized LLM red-teaming. This
policy covers vulnerabilities in the harness and its maintained integrations. It does not grant
permission to test third-party systems.

## Supported versions

| Version | Supported |
|-|-|
| `0.3.x` | Yes |
| `< 0.3` | No |
| Unreleased `main` | Best effort; not a stable security contract |

Upgrade to the latest supported release before reporting a defect that may already be fixed.

## Report a vulnerability privately

Use GitHub's **Report a vulnerability** form for this repository:
<https://github.com/Yivas/wallbreaker-hermes/security/advisories/new>.

Do not disclose an unpatched vulnerability in a public issue, discussion or pull request. Public
issues are appropriate for ordinary defects only after removing exploit details and sensitive data.

Include, when available:

- affected Wallbreaker Hermes version or commit;
- operating system, Python version and installation method;
- affected component and security boundary;
- minimal, sanitized reproduction steps;
- expected and observed behavior;
- impact, prerequisites and any known workaround.

Remove credentials, cookies, authorization headers, private endpoints, prompts, responses, system
instructions, account or session identifiers, operational configuration, run logs and evidence
sidecars. If exact content matters, describe its shape with a fictional replacement.

Maintainers will review the report, reproduce it when possible and decide how to coordinate a fix
and disclosure. The project does not promise a response deadline, embargo period, bounty, CVE or
release date.

## Security boundaries

Wallbreaker Hermes runs with the permissions of the local account. Its shell, file and network
tools are intentionally powerful. Do not treat the harness, dashboard or Hermes laboratory as a
sandbox for untrusted code.

The Hermes laboratory uses an ephemeral, explicitly authorized target home. It excludes
credentials, sessions, channels, logs, caches and gateway state; denies target tools and MCP;
compares state before and after each repetition; and removes the temporary home on exit. The child
process still retains the host account's filesystem and network permissions.

The dashboard binds to `127.0.0.1` by default. Keep it local unless you provide an appropriate
external authentication, TLS and network-control layer. Local authentication controls reduce
accidental access but do not make an internet-facing deployment safe by themselves.

## Sensitive outputs

Adversarial prompts, model responses, findings and generated files may contain harmful or
confidential material. Default output locations are ignored by Git, but that does not encrypt,
redact or erase them.

Hermes campaign reports are sanitized. Human-review bodies live in a separate local sidecar with
restrictive permissions and an integrity binding to the report. `review` and `verify` do not send
those bodies to Hermes Agent. Operators remain responsible for backups, filesystem access and
secure deletion.

## Network behavior

Network access occurs only through configured or explicitly invoked operations, including provider,
target and judge calls, dataset or corpus updates and provider verification. An optional `[art]`
endpoint receives labels, scores and technique names required to render a session card; do not
configure it for sensitive engagements.

The default test and documentation workflows must not run live campaigns or require provider
credentials.

## Responsible use

Use the project only against systems you own, operate or have explicit written authorization to
test. Follow the provider's terms and applicable law. Report target-provider weaknesses through the
provider's disclosure channel, especially when a test surfaces confidential system instructions.
