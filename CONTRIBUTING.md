# Contributing to Wallbreaker Hermes

Wallbreaker Hermes is an open source collaborative project. We welcome reproducible bug reports,
focused proposals, documentation corrections and pull requests that improve authorized LLM
security evaluation.

By contributing, you agree that your work is provided under the project's
[AGPL-3.0-or-later license](LICENSE).

## Choose the right channel

- Use the [bug report form](https://github.com/Yivas/wallbreaker-hermes/issues/new?template=bug_report.yml)
  for reproducible defects.
- Use the [feature request form](https://github.com/Yivas/wallbreaker-hermes/issues/new?template=feature_request.yml)
  for scoped proposals.
- Use GitHub Private Vulnerability Reporting for undisclosed security issues. Do not put
  vulnerability details in a public issue.
- Use the pull request template for code or documentation changes.

Search open and closed issues before filing a new report. The project does not promise a response
time, acceptance or a release date.

## Protect sensitive data

Use fictional and minimized examples. Remove or replace:

- credentials, cookies and authorization headers;
- prompts, model responses and private system instructions;
- provider, account, session, request and conversation identifiers;
- private endpoints, configuration, profiles and filesystem paths;
- run logs, reports, evidence sidecars and generated attack artifacts.

Do not upload real engagements. If a sanitized reproduction is not sufficient, start with a private
vulnerability report and explain what evidence is available.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
```

Dashboard contributors also install the dashboard extra and use the frozen frontend lockfile:

```bash
python -m pip install -e ".[dev,dashboard]"
cd wallbreaker/dashboard/web
npm ci
npm test -- --run
npm run build
npm run check:line-counts
```

Documentation contributors build the wiki independently:

```bash
cd wiki
npm ci
npm run build
```

## Repository structure

- `wallbreaker/providers/` normalizes supported provider protocols.
- `wallbreaker/agent/` owns the protocol-independent loop and messages.
- `wallbreaker/tools/` contains registry-based tools.
- `wallbreaker/transforms/` contains pure encoders and decoders.
- `wallbreaker/tui/` contains the Textual interface.
- `wallbreaker/dashboard/` contains the FastAPI backend and React/Vite frontend.
- `wallbreaker/hermes_*` and `integrations/hermes/` contain the opt-in Hermes laboratory.
- `tests/` is the executable contract.
- `wiki/` is the source for GitHub Pages documentation.

## Change requirements

- Write code, comments, documentation, tests, fixtures, commits and pull requests in English.
- Preserve Wallbreaker behavior unless the change explicitly fixes or extends that contract.
- Add focused tests for changed behavior and its relevant failure path.
- Keep provider calls and live campaigns out of the default test suite.
- Reuse existing registries, services and configuration before adding abstractions or dependencies.
- Cite the source and license of incorporated techniques, data or code.
- Do not add private prompts, active configuration, operational profiles or unlicensed corpora.
- Update the README or wiki when a public command, configuration key, compatibility promise or
  safety boundary changes.

Generic academic techniques should cite their source without claiming novelty. Contributions whose
only purpose is to increase real-world harm without evaluation value are out of scope.

## Before opening a pull request

Run the checks that apply to your change. A full repository change normally uses:

```bash
python -m ruff check .
python -m compileall -q wallbreaker p4rs3lt0ngv3_mcp agent_dashboard_harden
pytest -q
pytest tests/pbt/ -q -W error::ResourceWarning
```

For release-facing changes, also build and inspect the distributions using the commands documented
in the repository workflow. Do not create or move tags as part of a pull request.

The pull request must explain the motivation, user-visible behavior, compatibility, security and
privacy effects, tests performed and documentation changes. Keep unrelated refactors out of the
same change.

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
