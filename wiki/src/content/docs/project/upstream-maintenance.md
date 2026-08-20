---
title: Upstream maintenance
description: Update the fork without erasing Wallbreaker history or Hermes-specific contracts.
sidebar:
  order: 3
---

Wallbreaker Hermes keeps two remotes:

- `origin`: the maintained Wallbreaker Hermes fork;
- `upstream`: `JailbrokenAI/wallbreaker`.

Before integrating upstream changes:

1. fetch both remotes without changing the working tree;
2. inspect upstream history, release notes and dependency changes;
3. compare the provider, CLI, dashboard and packaging contracts touched by the update;
4. replay the Hermes laboratory and campaign tests against the merged candidate;
5. verify AGPL attribution, NOTICE and built artifacts;
6. keep the update and any Hermes adaptation in reviewable commits.

Do not force-push `main`, move published tags or open an upstream pull request without separate
approval. The detailed rollback procedure remains in
[`docs/UPSTREAM.md`](https://github.com/Yivas/wallbreaker-hermes/blob/main/docs/UPSTREAM.md).
