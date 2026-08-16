# External data sources

Wallbreaker Hermes does not ship third-party attack corpora, benchmark rows, leaked prompts, or
locally cached downloads in its wheel or source distribution. Dataset loaders fetch only the
revision-pinned files listed below when an operator explicitly uses that source. The measured
revisions and file digests also live in `library.lock.toml`. Loaders verify downloads and cached
files against those reviewed SHA-256 values before parsing them.

| Source | Pinned revision | File | Upstream license | Redistribution |
| --- | --- | --- | --- | --- |
| HarmBench | `8e1604d1171fe8a48d8febecd22f600e462bdcdd` | `data/behavior_datasets/harmbench_behaviors_text_all.csv` | MIT | Not included |
| AdvBench (`llm-attacks`) | `098262edf85f807224e70ecd87b9d83716bf6b73` | `data/advbench/harmful_behaviors.csv` | MIT | Not included |
| JailbreakBench JBB-Behaviors | `886acc352a31533ffbcf4ef22c744658688086fc` | `data/harmful-behaviors.csv`, `data/benign-behaviors.csv` | MIT | Not included |
| StrongREJECT | `f7cad6c17e624e21d8df2278e918ae1dddb4cb56` | `strongreject_dataset/strongreject_dataset.csv` | Mixed; see below | Not included |
| `asgeirtj/system_prompts_leaks` | `332f3e7ef5a5f317bf147c0838528fdaab423626` | Operator-selected local checkout | Repository declares CC0-1.0; underlying rights may differ | Not included or fetched automatically |

StrongREJECT releases its code and custom rows under MIT. Its combined CSV also identifies rows
from prior datasets. Upstream documents some of those sources as MIT and others as having no stated
license. Wallbreaker therefore does not redistribute the CSV. Review its `source` column and the
upstream README before using or sharing cached rows.

The `system_prompts_leaks` repository declares CC0-1.0. That declaration may not settle rights in
third-party product prompts collected by the repository. Wallbreaker neither downloads nor bundles
that corpus. An operator who supplies a local checkout is responsible for provenance, permission,
and policy compliance.

## Verification record

Revisions were measured from upstream `HEAD` on 2026-08-16. SHA-256 values in
`library.lock.toml` were calculated from the exact pinned files. `ENI` remains `UNRESOLVED` because
its configured repository returned “not found” on that date; Wallbreaker refuses to load it.

When updating a source, review its license and provenance again, update the revision and SHA-256,
and run the offline test suite before committing the lock change.
