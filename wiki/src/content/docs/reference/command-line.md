---
title: Command-line reference
description: Find the stable entry points and use the installed CLI as the source of truth.
sidebar:
  order: 1
---

The installed CLI is the source of truth for options and arguments:

```bash
wallbreaker --help
wallbreaker check
wallbreaker report --help
wallbreaker export --help
wallbreaker dashboard --help
wallbreaker hermes --help
```

Common entry points:

| Command | Purpose |
|-|-|
| `wallbreaker` | Start the terminal UI with the default profile |
| `wallbreaker --profile NAME` | Select an attacker profile |
| `wallbreaker --auto "OBJECTIVE"` | Run the autonomous loop |
| `wallbreaker --resume` | Reopen the autosaved local session |
| `wallbreaker report` | Render findings from a run log |
| `wallbreaker export` | Export structured findings and optional CI status |
| `wallbreaker dashboard` | Start the local dashboard |
| `wallbreaker hermes` | Inspect the Hermes laboratory workflow |

Commands that call a provider, target, judge, dataset source or update endpoint use the network only
when invoked and configured. Run `wallbreaker check` before an engagement and keep operational
configuration outside the repository.
