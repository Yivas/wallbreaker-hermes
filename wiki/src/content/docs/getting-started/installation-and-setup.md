---
title: Installation and setup
description: Install Wallbreaker Hermes and verify the local environment.
sidebar:
  order: 1
---

## Requirements

- Python 3.11 or newer.
- Git for development checkouts and optional library updates.
- Node.js only for dashboard development, the P4RS3LT0NGV3 bridge, or this documentation site.
- Explicit authorization for every target.

## Install the release

```bash
python -m pip install wallbreaker-hermes==0.3.0
wallbreaker --help
wallbreaker check
```

The distribution is named `wallbreaker-hermes`. The import package and commands remain
`wallbreaker` and `wb` for upstream compatibility.

## Install for development

```bash
git clone https://github.com/Yivas/wallbreaker-hermes.git
cd wallbreaker-hermes
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
```

On Windows PowerShell, activate with:

```powershell
.\.venv\Scripts\Activate.ps1
```

Dashboard contributors use the lockfile rather than updating dependencies during setup:

```bash
python -m pip install -e ".[dev,dashboard]"
cd wallbreaker/dashboard/web
npm ci
npm test -- --run
npm run build
```

## Verify the checkout

```bash
wallbreaker check
python -m ruff check .
pytest -q
```

The default suite must not require provider credentials or run a live campaign.

:::caution
Do not use a checkout that contains operational configuration, run logs, reports, prompt corpora or
evidence from another engagement. Start from a clean clone and use fictional fixtures for tests.
:::
