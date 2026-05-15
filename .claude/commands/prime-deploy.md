---
description: Prime agent with seestar-scope deploy + infrastructure context
---

# Prime Deploy: Jetson Stack + Docker Compose Orientation

## Objective

Orient on the deploy topology (workstation → Jetson), docker compose, the vendored seestar_alp submodule, CI, and cloudflared tunnel before working on infrastructure, dockerfiles, or the Jetson setup script.

## Process

### 1. Compose stack

Read `docker-compose.yml` — 4 services:

- `seestar-alp` (built from `vendor/seestar_alp/`) — ports 5555 (REST), 7556 (MJPEG). Healthcheck on `/management/apiversions`.
- `seestar-portal-backend` (built from `portal/backend/Dockerfile`) — port 8503. Healthcheck on `/health`. Depends on `seestar-alp`.
- `seestar-portal-ui` (built from `portal/Dockerfile`) — port 8502. Healthcheck on `/_stcore/health`. Depends on `seestar-portal-backend`.
- `seestar-cloudflared` (image: `cloudflare/cloudflared:latest`) — profile `tunnel`. Shares the workstation's tunnel via file-based config.

Note the volume model: `captures-data`, `sessions-data`, `gallery-db` (named volumes); `alp-config/config.toml` bind-mounted into seestar-alp; `cloudflared/` bind-mounted into the tunnel container.

### 2. Hosts

- **Workstation** `192.168.0.36` — source-only. `docker compose` here is NOT used for deploy.
- **Jetson** `192.168.0.234` — runs the stack via `docker compose up -d` and a systemd unit.
- **Scope** `192.168.0.132` — Seestar S50 firmware 7.34.

### 3. Jetson deploy assets

!`ls deploy/jetson/`

Read `deploy/jetson/README.md` — first-boot checklist, requirements.
Read `deploy/jetson/setup.sh` — idempotent installer (Docker, repo clone, .env config, ARM64 build, systemd install).
Read `deploy/jetson/seestar-stack.service` — systemd unit. **The real `ExecStart` is `docker compose --profile tunnel up`** (foreground, `Type=simple`, profile-on-by-default). NOT `up -d`. This means:

- Systemd-managed boot brings up **4 containers** including `seestar-cloudflared`.
- A bare SSH `docker compose up -d` brings up only **3** (no tunnel sidecar).

This matters for health-check scripts and post-deploy verification — count containers conditional on which path started the stack.

#### Production bug: `setup.sh` writes wrong `SEESTAR_PORT`

`deploy/jetson/setup.sh:96` writes `SEESTAR_PORT=11111` to `.env`. Every other source of truth uses **32323**. A fresh Jetson install will get the wrong port. **Workaround**: edit `.env` on Jetson after `setup.sh` completes to set `SEESTAR_PORT=32323`, or fix the bug upstream in `setup.sh`. Run `/sync-env` (if scaffolded) to detect this drift automatically.

#### `setup.sh` two-stage install

`setup.sh` lines 56-62 exit after adding the user to the docker group. The user **must re-login and re-run `setup.sh`** before the install completes. Without that, a fresh install will see exit 0 and assume "done" — but `docker` group membership isn't applied to the current shell, so subsequent steps would fail. The script prompts for this; respect the prompt.

#### `setup.sh` tunnel mismatch

`setup.sh` verifies **3 running containers** (lines 138-143) and reports success. But the systemd unit then starts a **4th** (`seestar-cloudflared` via `--profile tunnel`). There's a verification window where `setup.sh` says "3/3 healthy" and then systemd kicks in a 4th container — both states are normal, don't panic when the count changes after setup completes.

### 4. Vendored seestar_alp

`vendor/seestar_alp/` is a git submodule. **The Jetson container has its own copy that may be newer than this checkout** — diff inside the running container before patching, don't trust line numbers from `vendor/`.

`alp-config/config.toml` is bind-mounted into the seestar-alp container at `/home/seestar/seestar_alp/device/config.toml` — edit on Jetson host, `docker restart seestar-alp`.

#### `portal/clients/` shared dep — rebuild gotcha

`portal/clients/` is **COPIED** into the `seestar-portal-backend` Docker image (see `portal/backend/Dockerfile` lines 33-36). This was added to fix stale-snapshot bugs from PRs #38, #39, #41 where the backend image held outdated client code.

**Touching anything under `portal/clients/` requires rebuilding the backend image too**, not just the UI. If you `docker compose up -d --build seestar-portal-ui` only, the backend will still hold the old client code. Build both: `docker compose up -d --build seestar-portal-ui seestar-portal-backend`.

### 5. CI

Read `.github/workflows/ci.yml` — runs on push/PR to `main`. **Full flow** (not just lint/build/test):

1. **Checkout with submodules** (`actions/checkout@v4` with `submodules: recursive`) — vendored `seestar_alp` must be present for build.
2. **Setup Python 3.11** (`actions/setup-python@v5`).
3. **Pip install** three requirement files:
   - `portal/requirements.txt`
   - `portal/backend/requirements.txt`
   - `portal/requirements-dev.txt`
4. **Ruff** — `ruff check portal/`
5. **Docker build** — `docker compose build` (with stub env vars provided in the workflow env block).
6. **Pytest** — `pytest portal/tests/ -m "not hardware"` with two deselects (cv2.imencode CI quirk on opencv-python-headless).

Submodule-recursive + pip-install steps are load-bearing — local `pytest` runs in CI-equivalent mode require all three requirement files installed.

### 6. Cloudflare tunnel — shared with workstation

!`ls cloudflared/ 2>/dev/null`

Tunnel ID `831e21c1-a274-4f14-8b29-b91097f96c92` (referenced in `cloudflared/config.yml`) is **shared with the workstation UCIS-constellation tunnel**. This is an **external dependency on the workstation** — if that tunnel credential is rotated for any reason, seestar-scope breaks silently (the connector will fail to authenticate on next restart, but the running connector keeps working until then).

Credentials JSON is gitignored (`cloudflared/*.json`). `config.yml` template is committed.

### 6a. Two `.env.example` files

The repo has **two** `.env.example` files and they differ:

- root `./.env.example`
- `deploy/jetson/.env.example`

The Jetson version has commented `SITE_LAT`, `SITE_LON`, `SITE_ELEVATION_M`, `SITE_NAME` overrides not present in the root version. **Don't trust either alone** — `diff` them before relying on either as canonical, and update both when adding a new env var.

### 6b. ARM64 / multi-arch build

Both Dockerfiles use `FROM python:3.11-slim`, which is a multi-arch image. ARM64 build on the Jetson "just works" via the base-image's multi-arch manifest, **not via explicit `--platform` flags** in the compose file. If you need to force a platform (e.g. cross-build from workstation), you must add `--platform` yourself.

`portal/backend/Dockerfile` lines 5-10 and line 21 carry a Siril ARM64/Flatpak override block — when building on ARM64, the Siril CLI path is overridden to the Flatpak install location.

### 6c. SIRIL env vars

`SIRIL_BIN`, `SIRIL_TIMEOUT`, `SIRIL_CLI_PATH` are listed in `.env.example:28-35`. **Important**: `SIRIL_BIN` and `SIRIL_TIMEOUT` are read **directly via `os.environ`** in `services/stacking_service.py:97-99`, NOT through pydantic settings. On ARM64 these are overridden to the Flatpak path (see the Dockerfile override block above). If you change these env vars and the service doesn't pick them up, check `os.environ` access, not `config.py`.

### 7. Migration / rollback

Skim `docs/migration_runbook.md` — workstation → Jetson cutover procedure, smoke test, rollback steps.

## Output Report

In under 200 words:

- The 4 compose services + their ports + health endpoints
- Workstation vs Jetson split (what runs where)
- Submodule caveat (in-container code can diverge from `vendor/`)
- CI gates and known-skip tests
- Tunnel topology in one sentence

Don't start coding until this is in your context.
