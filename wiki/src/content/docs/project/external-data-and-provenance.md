---
title: External data and provenance
description: Know which optional datasets and corpora are not part of the distribution.
sidebar:
  order: 2
---

Wallbreaker Hermes includes code and fixtures whose licenses permit redistribution. Large benchmarks,
prompt corpora and third-party repositories may be downloaded only when an operator invokes the
corresponding update or setup command.

The project does not automatically bundle or fetch an offline product prompt corpus. Native-format
mimicry can search a corpus supplied by the operator, who is responsible for its permission,
provenance, storage and disclosure limits.

Before adding data or code:

1. record the source URL, commit or version and license;
2. confirm that redistribution and the intended transformation are allowed;
3. include only the minimum files required by the feature;
4. preserve notices and attribution required by the source;
5. inspect the built wheel and sdist to ensure local data was not included.

The authoritative inventory and license notes remain in
[`NOTICE`](https://github.com/Yivas/wallbreaker-hermes/blob/main/NOTICE) and
[`docs/EXTERNAL_DATA.md`](https://github.com/Yivas/wallbreaker-hermes/blob/main/docs/EXTERNAL_DATA.md).
