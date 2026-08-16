# Upstream maintenance

Wallbreaker Hermes tracks `JailbrokenAI/wallbreaker` without renaming the Python package,
imports, or `wallbreaker`/`wb` commands.

## Verified baselines

- Wallbreaker upstream: `8b85e768efa69028b4af9f3d1c9c079178aa8a53`
- Hermes Agent: tag `v2026.8.13`, package `0.20.1`, commit
  `f80f453ae0679347e38abc917c7f94f717bf96c5`

The Hermes adapter rejects a checkout or package version that does not match its closed
manifest. Update these baselines only after the laboratory contract tests pass against the new
revision.

## Integrate upstream

Use a clean checkout with `origin` pointing to `Yivas/wallbreaker-hermes` and `upstream` pointing
to `JailbrokenAI/wallbreaker`.

```bash
git status --short
git remote -v
git fetch upstream
pre_update=$(git rev-parse HEAD)
git merge --no-commit --no-ff upstream/main
```

Resolve conflicts without replacing fork-specific Hermes behavior or upstream attribution. Then
run the release checks:

```bash
python -m compileall -q wallbreaker p4rs3lt0ngv3_mcp agent_dashboard_harden
python -m pytest -q
cd wallbreaker/dashboard/web
npm ci
npm test -- --run
npm run build
```

Review `git diff --check`, the merge diff, license notices, network changes, and the Hermes tests
before committing the merge. Do not push during validation.

## Roll back

Before committing, use `git merge --abort`. After a local merge commit but before publication,
reset only the disposable validation checkout to `$pre_update`:

```bash
git reset --hard "$pre_update"
```

If an integration commit has already been pushed, revert the merge commit instead of rewriting
public history:

```bash
git revert -m 1 <merge-commit>
```

Re-run the same checks after rollback. Never move or reuse a published release tag.
