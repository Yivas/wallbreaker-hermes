# Changelog

## Unreleased

### Fixed

- Accept `GARBLED` and `EMPTY` heuristic labels when reading Hermes campaign report v2, including
  reports produced by earlier releases. Review and explanation can now load these reports;
  unresolved attempts still require human review, and verification does not mark them complete.
  Judge labels, recorded verdicts, report schema and private evidence are unchanged.

## 0.7.0 - 2026-09-16

### Added

- `wallbreaker hermes review RUN --explain`: prints why the heuristic labelled each pending attempt,
  with the measurements behind an illegible-output verdict, and keeps private bodies out of the event
  stream.
- Operator-supplied batteries: any battery source now accepts `file:PATH`, with a closed schema, size
  and count limits, a per-item language label (any label, no closed list), a `languages()` helper and
  a `language=` filter, plus an optional `<name>.sha256` pin that fails closed when the content
  changes. The harness ships no content, so a private battery stays private.
- `WALLBREAKER_REFUSAL_MARKERS` lets an operator add refusal wording for a language the tool does not
  know, with a one-time warning on stderr when the file exists but cannot be used.

### Changed

- A campaign report is no longer tied to the exact package version that produced it. The producing
  version is still recorded and now reported as such, and the target baseline is still enforced, but
  a structurally valid report can be reviewed and verified after an upgrade instead of requiring a
  matching copy of the tool.
- The illegible-output detector is script aware. A fluent reply in Japanese, Arabic, Chinese or
  Russian is no longer reported as a scrambled output: the word-shaped and vowel rules apply only to
  scripts where they mean something, and repeated tokens are checked in every script.

### Fixed

- A bundled battery name can no longer be shadowed by a local file of the same name, and an empty
  digest pin is refused instead of raising an unhandled error.
- Battery size is checked before the file is read, and a path that is not a regular file is refused
  with a clear error.
- `review --explain` pairs each body with the signals of its own fire, and sanitises the reason it
  prints.

### Compatibility

- Existing reports, suites, CLI arguments and Python dependencies are unchanged. Reports produced by
  earlier releases are now readable by this one.
- The separate target remains fixed to Hermes Agent `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`.

### Upgrade

```text
python -m pip install --upgrade wallbreaker-hermes==0.7.0
```

Compare: [v0.6.1...v0.7.0](https://github.com/Yivas/wallbreaker-hermes/compare/v0.6.1...v0.7.0).

## 0.6.1 - 2026-09-15

### Fixed

- Raised the judge ceiling to the 4096 tokens measured as reliable. 0.6.0 set 1024, and the earlier
  measurement on the failing fire showed 1200 tokens still produced valid JSON only twice in three
  attempts, so 1024 was too close to the truncation boundary.

### Compatibility

- Campaign engine, report schemas and dependencies unchanged. Only the judge ceiling differs from
  0.6.0; grading semantics are identical.

### Upgrade

```text
python -m pip install --upgrade wallbreaker-hermes==0.6.1
```

Compare: [v0.6.0...v0.6.1](https://github.com/Yivas/wallbreaker-hermes/compare/v0.6.0...v0.6.1).

## 0.6.0 - 2026-09-15

### Fixed

- The judge answered with a 250-token ceiling, which cut its JSON object in half or left it empty on
  models that think by default, and surfaced as a failed judge on every fire. It now uses the
  4096-token ceiling measured as reliable for that failure mode.
- The judge prompt now distinguishes harmful objectives from benign ones. A benign request is graded
  by whether the target answered it, so a correct answer to a control case no longer reads as a
  refusal.
- The lexical heuristic recognises Spanish refusal wording, and Spanish hedging, in the opening of a
  reply instead of scoring a long Spanish refusal as compliance by its length alone.

### Compatibility

- The campaign engine, report schemas and dependencies are unchanged; this release corrects how the
  existing judge and heuristic grade a reply.
- Scores from earlier releases are not directly comparable with this one: a benign objective is now
  graded by whether the target answered it.
- The separate target remains fixed to Hermes Agent `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`.

### Upgrade

```text
python -m pip install --upgrade wallbreaker-hermes==0.6.0
```

Compare: [v0.5.0...v0.6.0](https://github.com/Yivas/wallbreaker-hermes/compare/v0.5.0...v0.6.0).

## 0.5.0 - 2026-09-15

### Added

- Added `wallbreaker hermes review RUN --interactive`, a terminal review screen that shows one
  pending attempt at a time with the case expectation and the recorded judge, heuristic, state and
  tool results. `p` marks pass, `f` marks finding and `a` stores the decisions; nothing is written
  before `a`, and the screen refuses to start without an interactive terminal.
- Added `interactive_command` and `show_evidence_command` to the pending-review event: the same
  controls written as copy-ready commands with the absolute report path, so the operator can run
  them from any working directory.

### Fixed

- Normalised carriage returns in the private review display so Windows bodies no longer render
  `\x0d` escapes before every line.

### Compatibility

- No changes to the campaign engine, judge implementation, report schemas or dependencies.
- The separate target remains fixed to Hermes Agent `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`.
- The interactive review is a local terminal control. The coordinating agent still receives no
  private bodies and must not run it, `--show-evidence` or the sidecar.

### Upgrade

```text
python -m pip install --upgrade wallbreaker-hermes==0.5.0
```

Refresh the operator skill from the same public source and start a new coordinator conversation
before relying on the new control.

Compare: [v0.4.0...v0.5.0](https://github.com/Yivas/wallbreaker-hermes/compare/v0.4.0...v0.5.0).

## 0.4.0 - 2026-09-15

### Added

- Added the public `wallbreaker-campaign-setup` companion skill, with fictional suite,
  configuration and manifest templates plus artifact preparation and offline diagnosis references.
- Included both skills and all setup companions in source-distribution checks. Skills remain
  installed separately from GitHub and are not included in the Python wheel.

### Fixed

- Reuse operator decisions and answer informational questions without restarting campaign intake
  or repeating a declined approval. Execution still requires authorization of the exact dry-run plan.
- Clarified that the stock judge measures harmful usefulness, not general instruction following;
  parser acceptance, heuristic agreement and structural verification do not establish calibration.
- Separated behavior, state, tool attempts, failed execution and pending human review. Documented
  that HMAC binds evidence but does not encrypt the private sidecar.
- Kept diagnosis offline by default: paid probes, evaluator changes and package maintenance require
  their own scope and authorization. Local skill copies should match the public source without
  disabling filesystem protections.

### Compatibility

- No changes to the campaign engine, CLI behavior, judge implementation, report schemas or dependencies.
- The separate target remains fixed to Hermes Agent `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`; the usual coordinator is capability-based.
- Updating skills does not update the installed package or authorize live campaigns.

### Upgrade

```text
python -m pip install --upgrade wallbreaker-hermes==0.4.0
hermes skills install Yivas/wallbreaker-hermes/integrations/hermes/skills/wallbreaker-hermes
hermes skills install Yivas/wallbreaker-hermes/integrations/hermes/skills/wallbreaker-campaign-setup
```

Start a new coordinator conversation after refreshing previously loaded skills. Preserve local
access controls during authorized installation. Generate and approve a fresh dry-run plan before
any campaign after a package upgrade.

Compare: [v0.3.2...v0.4.0](https://github.com/Yivas/wallbreaker-hermes/compare/v0.3.2...v0.4.0).

## 0.3.2 - 2026-09-14

### Fixed

- Let the user's usual Hermes Agent coordinate Wallbreaker through native skill loading,
  clarification and terminal tools instead of requiring the target's pinned release on the
  coordinator. The separate target baseline, campaign authorization and evidence gates are unchanged.
- Clarified coordinator requirements across the operator integration and laboratory guides, with
  regression tests separating them from the exact target baseline. The skill remains installed
  separately from GitHub; the Python wheel does not contain it.
- Stabilized the autocomplete regression test by delivering keyboard events before checking the
  popup. This does not change TUI behavior.

### Security

- Updated the documentation build to Astro 7.2.8, Sharp 0.35.4, SVGO 4.1.0 and js-yaml 4.3.2
  to address the reported image-processing, SVG sanitization and YAML resource-exhaustion issues.
- Updated development-only Vitest and its mocker to 4.1.11 to address redirect-mock file disclosure.
  These packages belong to documentation builds or frontend tests, not Python runtime dependencies.
- Explicitly disabled Astro telemetry in the documentation CI build.

### Compatibility

- The campaign engine, public APIs and Python dependency requirements are unchanged.
- The Hermes target remains fixed to `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`. Coordinator support depends on the required native
  capabilities, not on matching that target version.

### Upgrade

```text
python -m pip install --upgrade wallbreaker-hermes==0.3.2
```

Refresh the [Hermes operator skill](https://github.com/Yivas/wallbreaker-hermes/blob/v0.3.2/integrations/hermes/README.md)
separately and start a new coordinator conversation so previously loaded instructions are not reused.
Generate and approve a fresh dry-run plan before any campaign after upgrading.

Compare: [v0.3.1...v0.3.2](https://github.com/Yivas/wallbreaker-hermes/compare/v0.3.1...v0.3.2).

## 0.3.1 - 2026-08-20

### Changed

- Replaced the repository entry point with a concise supported-release guide and moved maintained
  user documentation to a versioned Starlight site.
- Added the community profile, structured issue forms, pull request guidance, dependency updates,
  GitHub Pages workflow and explicit security-reporting boundaries.

### Fixed

- Confined dashboard reports, history, capability discovery, direct tool execution and autonomous
  agent reads to approved run logs and working directories.
- Rejected symlinks, hardlinks, traversal, non-run files and nested linked logs before dashboard
  history or evidence processing.
- Required exact Origin and Host agreement before returning the local dashboard launch token.
- Applied read and write confinement to `cluster_findings` and reasoning-hygiene paths.
- Increased the headless Chrome render timeout for slower CI runners.

### Security

- Removed agent rules, operational audits, specs and internal work notes from the active public tree.
- Added explicit read-only permissions to the red-team gate workflow and documented the disposition
  of CodeQL false positives separately from confirmed dashboard path issues.

### Upgrade

```text
pip install --upgrade wallbreaker-hermes==0.3.1
```

Compare: `https://github.com/Yivas/wallbreaker-hermes/compare/v0.3.0...v0.3.1`.

## 0.3.0 - 2026-08-20

### Added

- Added a permission-restricted private evidence sidecar for human review while keeping campaign
  report v2 sanitized and structurally verifiable without private bodies.
- Added local `--show-evidence` and `--delete-evidence` review controls. Hermes Agent can coordinate
  pending IDs and decisions but cannot open or reproduce the private evidence.

### Fixed

- Required HMAC-bound objective, prompt, and response evidence before resolving manual reviews or
  resuming campaign fires.
- Hardened report, sidecar, and lock handling against aliases, links, reparse points, oversized
  evidence, malformed JSON, interrupted writes, concurrent deletion, and retry accumulation.
- Escaped terminal control sequences in local evidence display and stopped Hermes campaign commands
  from loading dotenv files implicitly.
- Corrected the optional offline prompt-corpus documentation; Wallbreaker neither ships nor fetches
  that corpus.
- Added explicit property-based tests and clean wheel installation to the release workflow.

### Security

- Updated Vite to 6.4.3, Vitest to 3.2.7, h2 to 4.4.1, and cryptography to 50.0.0 before
  publication to close the open advisories affecting the locked development and runtime graph.

### Compatibility

- Existing report v2 files remain structurally verifiable. Reports created before private sidecars
  that already contain fires cannot be resumed or manually resolved because their review bodies no
  longer exist.
- The Hermes Agent baseline remains `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`.

### Verification

- Python: 1,550 passed, 57 skipped, 31 xfailed; PBT: 21 passed, 1 skipped.
- Frontend: 60 tests plus TypeScript/Vite build and component-size checks passed.
- Wheel and sdist passed artifact inspection, `twine check`, and clean installation outside the
  checkout.
- GitHub reported no open Dependabot alerts for the frozen dependency graph.

### Upgrade

```text
pip install --upgrade wallbreaker-hermes==0.3.0
```

Compare: `https://github.com/Yivas/wallbreaker-hermes/compare/v0.2.2...v0.3.0`.

## 0.2.2 - 2026-08-16

This is the first published `wallbreaker-hermes` distribution. The `v0.2.0` and `v0.2.1`
workflows stopped before creating a GitHub Release or uploading to PyPI.

### Fixed

- Completed the `dev` extra with the dashboard, barcode, and property-testing dependencies used by
  both the branch and release test suites.

## 0.2.1 - 2026-08-16

The `v0.2.1` workflow stopped before creating a GitHub Release or uploading to PyPI.

### Added

- Added the opt-in Hermes Agent laboratory with ephemeral replicas, fixed-runtime validation,
  exact request roles, zero-tools/MCP preflight, state evidence, credential-leak checks, and
  verified cleanup.
- Added campaign plan/report v2 with HMAC-scoped private fingerprints, checkpoint-bound resume,
  explicit manual review, and fail-closed finding semantics.
- Published under the `wallbreaker-hermes` distribution name while preserving `import wallbreaker`
  and the `wallbreaker`/`wb` commands.
- Included the compiled dashboard, Textual assets, Hermes operator integration, and revision-pinned
  datasets with SHA-256 verification.

### Fixed

- Aligned Vitest 2 with Vite 5 and regenerated the frontend lock with npm 10 so clean CI installs
  include a single compatible esbuild version.
- Raised the CI Node baseline to 22.14 for the declared jsdom engine requirement.
- Preserved module mock implementations between the dashboard auto-scroll tests under Vitest 2.

## 0.2.0 - 2026-08-16

### Added

- Published the Python distribution as `wallbreaker-hermes` while preserving the `wallbreaker`
  import package and the `wallbreaker`/`wb` commands.
- Included the compiled dashboard and Textual stylesheet in release wheels, with artifact checks for
  wheel and source-distribution contents.
- Added an opt-in Hermes Agent laboratory target fixed to Hermes Agent `v2026.8.13`, package
  `0.20.1`, and commit `f80f453ae0679347e38abc917c7f94f717bf96c5`.
- Added versioned Hermes campaign suites, isolated repetitions, response and state evidence,
  strict verification, and cleanup receipts.
- Added `wallbreaker hermes run|review|verify` plus the operator skill under
  `integrations/hermes/`.
- Added WebUI V2, MCP integration, expanded attack and evaluation tools, signed findings,
  corpus integrity pins, and dashboard security controls inherited from the fork history.
- Added the documented upstream integration and rollback procedure.

### Security

- Removed scheduled live red-team execution from CI. Repository workflows now run offline tests
  only.
- Session cards use an external image endpoint only when the operator configures `[art]`.
- Scoped persisted campaign fingerprints with an operator-held HMAC key and a per-report salt.
- Bound resume authorization to the validated checkpoint and Wallbreaker version.
- Rejected unexpected effective prompt roles and known credentials in child output or state.
- Moved the authorized live CI example outside `.github/workflows`; repository workflows do not
  schedule provider calls.
- Removed tracked prompts, private-path instructions, historical provider configuration, and UI
  captures containing run data from the release tree.
- Clarified that the Hermes laboratory is an ephemeral native process, not an operating-system
  sandbox.

### Fixed

- Preserved manual review whenever any evidence component remains unresolved, including runs that
  also contain a confirmed finding.
- Preserved cancellation status and cleanup receipts when cleanup cannot be verified.
- Counted blocked tool attempts only during the evaluated run, with preflight attempts failing
  closed.
- Normalized configured jailbreak paths across operating systems.
- Preserved Windows paths passed to `/session`, `/resume`, and `/save` commands.
- Protected dashboard token files with an owner/System/Administrators DACL on Windows while
  retaining exact `0600` permissions on POSIX.

### Compatibility

- Preserves the `wallbreaker` package, imports, and `wallbreaker`/`wb` commands.
- Tracks Wallbreaker upstream commit `8b85e768efa69028b4af9f3d1c9c079178aa8a53`.
- Requires Python 3.11 or newer.
