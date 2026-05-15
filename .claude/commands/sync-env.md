---
description: Cross-check env-var sources for drift (especially the setup.sh SEESTAR_PORT=11111 bug)
---

# Sync Env

## Objective

Check that `SEESTAR_PORT`, `SEESTAR_IP`, `SITE_*`, `SIRIL_*` are consistent across:

- `.env.example` (root)
- `deploy/jetson/.env.example`
- `deploy/jetson/setup.sh` (the values it writes to `.env`)
- `.github/workflows/ci.yml` (the stub env vars at the docker-build step)
- `.env` (if present — local + on Jetson)

Specifically catches **`setup.sh:96` writing `SEESTAR_PORT=11111`** instead of `32323` — a real production bug that breaks fresh Jetson installs.

## Process

### 1. Extract values from each source

!`grep -nE '^(SEESTAR_(IP|PORT)|SITE_|SIRIL_|TZ|BACKEND_URL)' .env.example`

!`grep -nE '^(SEESTAR_(IP|PORT)|SITE_|SIRIL_|TZ|BACKEND_URL)' deploy/jetson/.env.example 2>/dev/null || echo "(no jetson .env.example)"`

!`grep -nE '(SEESTAR_(IP|PORT)|SITE_|SIRIL_)' deploy/jetson/setup.sh`

!`grep -nE 'SEESTAR_(IP|PORT)|TZ|BACKEND_URL' .github/workflows/ci.yml`

If a local `.env` exists:
!`test -f .env && grep -nE '^(SEESTAR_(IP|PORT)|SITE_|SIRIL_|TZ|BACKEND_URL)' .env || echo "(no local .env)"`

### 2. Identify drift

Build a comparison table:

| Variable | .env.example | deploy/jetson/.env.example | setup.sh | ci.yml | .env (local) |
|---|---|---|---|---|---|
| SEESTAR_IP | ... | ... | ... | ... | ... |
| SEESTAR_PORT | **32323** expected | ... | **11111 — BUG** | ... | ... |
| SITE_LAT | ... | ... | ... | ... | ... |
| ... | | | | | |

Flag any row with mismatched values.

### 3. Verify on Jetson (if reachable)

```bash
ssh jmm2020@192.168.0.234 'cd ~/seestar-scope && grep -nE "^(SEESTAR_|SITE_|SIRIL_)" .env'
```

### 4. Report

Output:

```
## Env Sync Report

| Variable | Status | Sources | Action |
|---|---|---|---|
| SEESTAR_PORT | DRIFT | setup.sh=11111, others=32323 | **Fix setup.sh:96** or override .env after install |
| ... | OK | (all match) | — |

### Recommended fixes
1. Edit `deploy/jetson/setup.sh:96` — change `SEESTAR_PORT=11111` to `SEESTAR_PORT=32323`
2. ...

### Jetson .env state
{ssh result — does the live .env on Jetson have the right port?}
```

If `setup.sh:96` still has the `11111` bug, suggest a one-liner fix and offer to apply it.
