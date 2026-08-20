---
title: Legacy dashboard
description: Use the original dashboard during the WebUI V2 parity period.
sidebar:
  order: 2
---

The original dashboard remains available at <http://127.0.0.1:8787/legacy> while WebUI V2 covers the
operator workflows at `/v2`.

Both interfaces use the same backend security middleware, launch token and local data. The legacy
route is not a separate service and does not provide a weaker opt-out from API authentication.

Use WebUI V2 for current operation, resumable executions and historical evidence. Use the legacy
view only for workflows that have not reached parity. Report a reproducible parity problem through
the repository bug form rather than building new features only in the legacy interface.
