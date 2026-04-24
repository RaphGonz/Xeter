---
created: 2026-04-24T20:32:10.236Z
title: Audit env var defaults before going live
area: tooling
files:
  - services/view/next.config.ts
  - deploy/docker-compose.yml
---

## Problem

`PRESENTER_URL` in `next.config.ts` defaulted to `http://presenter:8000` (the Docker internal hostname). This silently breaks `npm run dev` locally with an `ENOTFOUND presenter` error. The fix was to change the fallback to `http://localhost:8000` — Docker overrides it explicitly via `docker-compose.yml` anyway so that side is safe.

The pattern to audit: any service URL that hardcodes a Docker service name as the fallback default instead of `localhost`. There may be other similar defaults elsewhere in the config.

## Solution

Before going live, grep `next.config.ts` and `docker-compose.yml` (and any other config files) for Docker service hostnames used as fallback defaults. Each should either:
- Default to `localhost` (safe for local dev), with Docker setting the real hostname via env var
- Or have no default and fail loudly if the env var is missing (safer for production)
