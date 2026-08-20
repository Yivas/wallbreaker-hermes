---
title: Dashboard
description: Run the local dashboard and understand its access boundary.
sidebar:
  order: 1
---

Install the optional dashboard dependencies and start the local service:

```bash
python -m pip install "wallbreaker-hermes[dashboard]==0.3.1"
wallbreaker dashboard
```

Open:

- WebUI V2: <http://127.0.0.1:8787/v2>
- Legacy dashboard: <http://127.0.0.1:8787/legacy>

The server binds to loopback by default. Each launch generates a bearer token, stores it with
restrictive local permissions and requires it with same-origin checks for protected API routes.
This protects the local operator session from unauthenticated and cross-site requests. It is not a
multi-user account or role system.

To bind another interface, you must acknowledge the exposure:

```bash
wallbreaker dashboard --host 0.0.0.0 --allow-network
```

:::danger
Do not expose the dashboard directly to the internet. Put any remote deployment behind a maintained
access-control, TLS and network boundary. Run history may contain prompts, responses, reasoning,
tool arguments and generated artifacts.
:::

## Development

```bash
cd wallbreaker/dashboard/web
npm ci
npm run dev
```

The development server proxies `/api` to the backend on `127.0.0.1:8787`. Rebuild the production
bundle with `npm run build` after frontend changes.
