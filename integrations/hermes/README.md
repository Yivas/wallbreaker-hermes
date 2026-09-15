# Hermes Agent campaign skills

This source-distributed integration lets an operator-side Hermes Agent discover and run the
Wallbreaker Hermes CLI. It is installed directly from the public GitHub repository and is not part
of the Python wheel. It is separate from the ephemeral Hermes target. Installing the skill does
not modify Hermes core or the clean checkout used by `hermes-lab`.

## Compatibility

Use your usual Hermes Agent as the coordinator. It needs skill discovery/loading, native
`clarify` for decisions, the normal `terminal` tool, and an installed Wallbreaker CLI.
The coordinator is not pinned to the target release; a second bot or conversation account is
not required. If a capability is missing, stop rather than bypassing authorization. These
requirements do not promise compatibility with every Hermes revision or provider.

Only the **separate target checkout** is fixed to:

- Hermes Agent release: `v2026.8.13`
- Python package: `0.20.1`
- Git commit: `f80f453ae0679347e38abc917c7f94f717bf96c5`

Other target revisions remain unsupported. Do not downgrade the coordinator or point the target
at its checkout or home. Campaign models, provider credentials and costs are separate from the
chat model; do not copy the coordinator's credentials or assume consent to provider charges.

The workflow continues to use:

- Wallbreaker report: `wallbreaker.hermes-campaign-report/v2`
- Wallbreaker CLI events: `wallbreaker.hermes-cli-event/v1`

## Install

Install the full Wallbreaker Hermes application from PyPI:

```text
pip install wallbreaker-hermes
```

The import package remains `wallbreaker`, and the commands remain `wallbreaker` and `wb`. Install
the two companion skills separately from their public GitHub paths:

```text
hermes skills install Yivas/wallbreaker-hermes/integrations/hermes/skills/wallbreaker-hermes
hermes skills install Yivas/wallbreaker-hermes/integrations/hermes/skills/wallbreaker-campaign-setup
```

Confirm discovery:

```text
hermes skills list
hermes skills inspect wallbreaker-hermes
hermes skills inspect wallbreaker-campaign-setup
```

Do not install the skill into the dedicated checkout configured as `hermes_runtime`. That checkout
must remain clean at the fixed commit.

If a conversation has already loaded an older skill, start a new conversation with `/new` before
requesting the updated workflow. Editing the skill does not replace instructions in chat history.
A skill update alone does not require another Hermes installation or a gateway restart.

## Responsibilities and updates

- `wallbreaker-hermes`: authorization, exact-plan execution, private review and verification.
- `wallbreaker-campaign-setup`: fictional artifact templates, evaluator suitability and offline
  diagnosis. Its references and templates are included in the skill directory.

Both are distributed through GitHub and the source archive, not the Python wheel. Keep installed
files identical to the public source; preserve filesystem protections during authorized updates.
Updating the skills does not update Wallbreaker or authorize package patches, live probes, or costs.
Check installed CLI compatibility before use. Historical release archives do not acquire files
added later on the source branch.

The text judge grades harmful substance for a harmful objective and whether the target answered a
benign one; the lexical heuristic reads refusals in Spanish or English at the opening of a reply.
A parseable judgment, or agreement between the two, still does not calibrate them. Establish
measurement suitability before proposing paid work, and keep behavior, state, tool attempts and
execution failures separate.

## Fictional fixtures

- `examples/synthetic-suite.yaml`: closed campaign suite with all three required splits.
- `examples/clean-manifest.json`: clean target manifest with no copied context.

The fixtures use synthetic names and contain no credentials, private prompts, operational paths,
or provider endpoints.

## Private review

An authorized campaign writes the sanitized `RUN` report and `RUN.evidence.json`. The sidecar is
local, gitignored, permission-restricted, and bound to the report with
`WALLBREAKER_HERMES_EVIDENCE_KEY`. HMAC binds evidence but does not encrypt it. Hermes Agent may
list pending IDs but must not open or reproduce that file.

The operator reviews bodies in a separate interactive terminal:

```text
wallbreaker hermes review RUN --show-evidence
wallbreaker hermes review RUN --interactive
wallbreaker hermes review RUN --set ATTEMPT=pass
wallbreaker hermes verify RUN
wallbreaker hermes review RUN --delete-evidence
```

`--interactive` opens a terminal review screen: one pending attempt at a time, the case expectation
and the recorded judge, heuristic, state and tool results, `p` for pass, `f` for finding and `a` to
store the decisions. Nothing is written before `a`, it refuses to start without an interactive
terminal, and it keeps the bodies on screen instead of printing them all at once. Run it yourself;
deriving or reproducing bodies through the agent remains forbidden.

The pending-review event carries the same two controls as `interactive_command` and
`show_evidence_command`, already written with the absolute report path. Hand those to the operator
so they can run them from any directory instead of navigating to the campaign folder.

Delete the sidecar only after all reviews resolve and verification succeeds. Deletion does not
remove backups or storage snapshots.

## Remove

Use Hermes Agent's normal skill removal command:

```text
hermes skills uninstall wallbreaker-hermes
hermes skills uninstall wallbreaker-campaign-setup
```
