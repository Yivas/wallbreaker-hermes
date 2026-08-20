---
title: Security and privacy
description: Understand authorization, local trust boundaries, network access and sensitive outputs.
sidebar:
  order: 1
---

## Authorization

Use Wallbreaker Hermes only against models and endpoints you own, operate or have explicit written
permission to test. The repository license does not grant permission to test a third party.

## Local trust boundary

The harness can execute commands, read and write files, call configured endpoints and load local
artifacts. It runs with the operator account's permissions. Neither the dashboard nor the Hermes
laboratory is an operating-system sandbox.

## Sensitive outputs

Run logs, model responses, reports, images and human-review evidence may contain confidential or
harmful material. Their default paths are ignored by Git, but they are not encrypted or securely
erased.

Keep them on an access-controlled filesystem, minimize retention and review every file before
sharing it. Never attach an unsanitized engagement to an issue or pull request.

## Network access

Provider, target, judge, dataset update, corpus update and verification operations use the network
only when configured or invoked. The default tests and documentation build do not run live
campaigns.

## Vulnerability reporting

Report vulnerabilities in Wallbreaker Hermes through GitHub Private Vulnerability Reporting. Read
[`SECURITY.md`](https://github.com/Yivas/wallbreaker-hermes/blob/main/SECURITY.md) for supported
versions, required evidence and disclosure boundaries.
