# Changelog

## Unreleased

## 0.2.1 - 2026-08-16

This is the first published `wallbreaker-hermes` distribution. The `v0.2.0` workflow stopped
before creating a GitHub Release or uploading to PyPI.

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
