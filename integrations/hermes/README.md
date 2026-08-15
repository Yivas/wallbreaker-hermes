# Hermes Agent operator skill

This source-distributed integration lets an operator-side Hermes Agent discover and run the
Wallbreaker Hermes CLI. It is installed directly from the public GitHub repository and is not part
of the Python wheel. It is separate from the ephemeral Hermes target. Installing the skill does
not modify Hermes core or the clean checkout used by `hermes-lab`.

## Compatibility

- Hermes Agent release: `v2026.8.13`
- Python package: `0.20.1`
- Git commit: `f80f453ae0679347e38abc917c7f94f717bf96c5`
- Wallbreaker report: `wallbreaker.hermes-campaign-report/v1`
- Wallbreaker CLI events: `wallbreaker.hermes-cli-event/v1`

Other Hermes Agent revisions are not supported by this integration.

## Install

Install Wallbreaker from this repository first. Then install the public skill from its GitHub path:

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

## Remove

Use Hermes Agent's normal skill removal command:

```text
hermes skills uninstall wallbreaker-hermes
```
