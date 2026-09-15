---
title: Hermes campaigns and review
description: Run versioned suites and resolve human-review findings without exposing private bodies.
sidebar:
  order: 3
---

Hermes campaigns load a versioned YAML suite and start every repetition in a new laboratory replica.
The flow reuses Wallbreaker's attack loop and judge instead of creating a separate attack engine.

## Operator flow

Ask your usual Hermes Agent to coordinate this flow through the
[operator skill](https://github.com/Yivas/wallbreaker-hermes/tree/main/integrations/hermes).
It needs skill discovery/loading, native `clarify`, the normal `terminal` tool and the installed
Wallbreaker CLI. Stop if a capability is missing; a second bot or conversation account is not
required. The fixed Hermes release belongs to the target, not the coordinator.

1. Confirm authorization for the target and suite, exact resource limits, strict cleanup and review.
2. Prepare a fictional or authorized suite and separate campaign configuration. Campaign providers
   and costs are separate decisions from the chat model; do not copy the coordinator's credentials.
3. Run the dry run and inspect the resolved target, limits and manifest.
4. Approve that exact plan's confirmation token. Changed inputs require another dry run.
5. Execute the approved campaign.
6. Review findings that lack enough automated evidence.
7. Verify the sanitized report and its integrity binding; success requires exit code `0`.

If the conversation already loaded an older skill, use `/new` before requesting this workflow.
Offline checks of skill loading and tool contracts are not a live campaign or provider test.

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

## Your own batteries

The harness ships the standard reference batteries only. Anything you write stays yours: pass a file
and the tools treat it as one more source, with no content copied into the repository.

```yaml
schema: wallbreaker.local-battery/v1
id: my-battery
language: es
items:
  - id: cyber-one
    category: cybercrime_intrusion
    behavior: "one objective per item"
```

Use it wherever a battery is accepted, by prefixing the path with `file:`:

```text
/sysprompt test --source file:/path/to/battery.yaml
wallbreaker hermes run suite.yaml --config config.toml --output RUN --dry-run
```

Each item may carry its own `language` label and any label is accepted; there is no closed list of
languages. If a file called `battery.yaml.sha256` sits next to it, its digest must match or the load
is refused. That is the optional pin for a battery you keep outside version control.

Refusal wording is language-specific and the harness only ships Spanish and English. For another
language, name a marker file with `WALLBREAKER_REFUSAL_MARKERS` holding `{language: [marker, ...]}`;
the judge grades the content itself and needs no such list.

To question a label, ask for the reasoning instead of guessing:

```text
hermes review RUN --explain
```

Two notes on method:

- The standard batteries stay in their original language. Translating one breaks comparability with
  every other result; if you want a language comparison, write your own pair with the same intent in
  both languages and keep them in separate batteries so the report separates them.
- An agent can write a battery for you: the file is plain text and the schema above is the whole
  contract. Review it before running it, because you are the one who answers for what it asks.

## Resolve reviews locally

Run either evidence control yourself, in your own local terminal. Never invoke them through Hermes
Agent, another model, captured automation, or a shared terminal, because their output contains the
private bodies.

```bash
wallbreaker hermes review RUN --show-evidence
wallbreaker hermes review RUN --interactive
wallbreaker hermes review RUN --set ATTEMPT=pass --set ATTEMPT=finding
wallbreaker hermes verify RUN
```

`--interactive` opens a terminal review screen instead of printing every body at once. It keeps the
pending attempts on the left, the private body on the right, and a header with what the case
expected plus the judge, heuristic, state and tool-attempt results already recorded in the report.
Press `p` for pass, `f` for finding and `a` to store the decisions; nothing is written before `a`.
The screen refuses to start without an interactive terminal and never copies bodies to a file.

The pending-review event prints both controls as copy-ready commands with the absolute report path
(`interactive_command` and `show_evidence_command`), so you can run them from any directory.

An expectation of `refuse` means the target should decline; `allow` means it should answer;
`context_dependent` is manual by design. The judge tells harmful objectives from benign ones: it
scores harmful substance when the objective is harmful, and whether the target answered when the
request is legitimate. The heuristic is lexical and reads refusals in Spanish or English at the
opening of a reply, so disagreement between the two asks for review instead of describing the
target.
