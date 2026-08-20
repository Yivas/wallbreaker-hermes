---
title: Hermes campaigns and review
description: Run versioned suites and resolve human-review findings without exposing private bodies.
sidebar:
  order: 3
---

Hermes campaigns load a versioned YAML suite and start every repetition in a new laboratory replica.
The flow reuses Wallbreaker's attack loop and judge instead of creating a separate attack engine.

## Operator flow

1. Prepare a fictional or authorized suite.
2. Run the dry run and inspect the resolved target, limits and manifest.
3. Confirm authorization and resource limits.
4. Execute the campaign.
5. Review findings that lack enough automated evidence.
6. Verify the sanitized report and its integrity binding.

Use the CLI help for the exact arguments supported by the installed release:

```bash
wallbreaker hermes run --help
wallbreaker hermes review --help
wallbreaker hermes verify --help
```

## Reports and evidence

The campaign report contains IDs, verdicts, scores, state comparisons and integrity metadata. It
does not contain target prompts or responses.

When a finding requires a human decision, private bodies live in a separate
`RUN.evidence.json` sidecar. The sidecar:

- is permission-restricted and excluded from version control;
- has a bounded size;
- is bound to the report and its target, prompt and response with HMAC;
- is opened only by explicit local evidence controls;
- is never passed to Hermes Agent through the operator skill.

`review` without an explicit evidence display and `verify` do not reveal those bodies. Treat the
sidecar as sensitive engagement data and account for backups when deleting it.
