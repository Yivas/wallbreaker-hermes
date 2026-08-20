# Hermes Agent operator skill

This source-distributed integration lets an operator-side Hermes Agent discover and run the
Wallbreaker Hermes CLI. It is installed directly from the public GitHub repository and is not part
of the Python wheel. It is separate from the ephemeral Hermes target. Installing the skill does
not modify Hermes core or the clean checkout used by `hermes-lab`.

## Compatibility

- Hermes Agent release: `v2026.8.13`
- Python package: `0.20.1`
- Git commit: `f80f453ae0679347e38abc917c7f94f717bf96c5`
- Wallbreaker report: `wallbreaker.hermes-campaign-report/v2`
- Wallbreaker CLI events: `wallbreaker.hermes-cli-event/v1`

Other Hermes Agent revisions are not supported by this integration.

## Install

Install the full Wallbreaker Hermes application from PyPI:

```text
pip install wallbreaker-hermes
```

The import package remains `wallbreaker`, and the commands remain `wallbreaker` and `wb`. Install
the operator skill separately from its public GitHub path:

```text
hermes skills install Yivas/wallbreaker-hermes/integrations/hermes/skills/wallbreaker-hermes
```

Confirm discovery:

```text
hermes skills list
hermes skills inspect wallbreaker-hermes
```

Do not install the skill into the dedicated checkout configured as `hermes_runtime`. That checkout
must remain clean at the fixed commit.

## Fictional fixtures

- `examples/synthetic-suite.yaml`: closed campaign suite with all three required splits.
- `examples/clean-manifest.json`: clean target manifest with no copied context.

The fixtures use synthetic names and contain no credentials, private prompts, operational paths,
or provider endpoints.

## Private review

An authorized campaign writes the sanitized `RUN` report and `RUN.evidence.json`. The sidecar is
local, gitignored, permission-restricted, and bound to the report with
`WALLBREAKER_HERMES_EVIDENCE_KEY`. Hermes Agent may list pending IDs but must not open or reproduce
that file.

The operator reviews bodies in a separate interactive terminal:

```text
wallbreaker hermes review RUN --show-evidence
wallbreaker hermes review RUN --set ATTEMPT=pass
wallbreaker hermes verify RUN
wallbreaker hermes review RUN --delete-evidence
```

Delete the sidecar only after all reviews resolve and verification succeeds. Deletion does not
remove backups or storage snapshots.

## Remove

Use Hermes Agent's normal skill removal command:

```text
hermes skills uninstall wallbreaker-hermes
```
