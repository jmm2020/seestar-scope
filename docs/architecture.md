# SeestarScope — System Architecture

> Documents the system **as it runs today** (2026-05-06).

## Overview

Three-service bridge-network design (unified `docker-compose.yml` at repo root):

| Service | Source | Container Name | Port |
|---------|--------|----------------|------|
| **seestar-portal-ui** (Streamlit UI) | `portal/` in this repo | `seestar-portal-ui` | :8502 |
| **seestar-portal-backend** (FastAPI) | `portal/backend/` | `seestar-portal-backend` | :8503 (internal) |
| **seestar-alp** (ALP backend) | `vendor/seestar_alp` (submodule, pinned `7bed951`) | `seestar-alp` | :5555 (internal) |
| **seestar-enhance** | `UCIS-v1:src/services/seestar_enhance` | separate service | :8504 |

All three Docker services share the `seestar-net` bridge network. Only the UI (`:8502`) is published to the host.

## Network Topology

```
LAN (192.168.0.x)
  │
  ├── Workstation (or Jetson Orin)
  │     └── Docker bridge: seestar-net
  │           ├── seestar-portal-ui      → host:8502  (Streamlit)
  │           ├── seestar-portal-backend → :8503      (FastAPI — internal only)
  │           └── seestar-alp            → :5555      (ALPACA — internal only)
  │     └── seestar-enhance  →  host:8504  (FastAPI + CUDA — separate service)
  │
  └── Seestar S50
        └── 192.168.0.132:32323  (proprietary TCP)
```

The portal UI talks to the portal backend via `http://seestar-portal-backend:8503` (container DNS).
The portal backend talks to `seestar-alp` via `http://seestar-alp:5555` (ASCOM ALPACA).
The ALP backend talks to the S50 directly via TCP.
`seestar-enhance` is a standalone service called by the portal for post-stack processing.

## Portal Stack (`portal/`)

| File / Dir | Purpose |
|------------|---------|
| `app.py` | Streamlit entry point — page routing |
| `config.toml` | Runtime config (S50 IP, ports, imaging defaults) |
| `config_loader.py` | TOML config loader with env-var overrides |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build (used by `seestar-portal-ui` service) |
| `clients/alpaca_client.py` | ASCOM ALPACA REST client (telescope, camera, focuser, filter, switch) |
| `clients/stellarium_client.py` | Stellarium Remote Control client |
| `views/dashboard.py` | Live status — 2 s auto-refresh |
| `views/goto.py` | GoTo/Slew — manual coords, Stellarium, Messier/NGC catalog |
| `views/imaging.py` | Camera control — exposure, gain, filter, loop mode |
| `views/stacking.py` | Siril stacking session management UI (start/add-frame/process/abort) |
| `views/focus.py` | Focuser position control |
| `views/sequence.py` | Multi-target automated imaging sequences |
| `views/settings.py` | App settings UI |
| `views/theme.py` | Cosmic CSS theme |
| `catalog/messier.py` | Messier catalog (110 objects) |
| `catalog/ngc_ic.py` | NGC/IC catalog subset |
| `utils/` | Coordinates, image processing, session logger |
| `tests/` | Unit + integration tests |

## ALP Backend (`vendor/seestar_alp` submodule)

Pin: `7bed951` (smart-underworld/seestar_alp, 2026-03-01)

Key directories:

| Dir | Purpose |
|-----|---------|
| `device/` | Core S50 TCP protocol implementation |
| `front/` | ALP's own web UI (not used by this portal) |
| `imaging/` | Imaging pipeline |
| `docker/` | Docker configs |

The ALP backend exposes an ASCOM ALPACA REST API on `:8503`.

## Stacking Service

The portal backend exposes a session-oriented Siril stacking pipeline at
`/api/stacking/*`, implemented by `portal/backend/services/stacking_service.py`
and routed via `portal/backend/routers/stacking.py`.

| Endpoint | Purpose |
|----------|---------|
| `POST /api/stacking/start` | Begin a new stacking session (returns `session_id`) |
| `GET /api/stacking/status` | Poll for `running`, `frame_count`, `progress`, `latest_result` |
| `POST /api/stacking/add-frame` | Append a captured-frame path to the active session |
| `POST /api/stacking/process` | Dispatch the Siril pipeline as a background task |
| `POST /api/stacking/abort` | Request abort of an in-progress run |
| `GET /api/stacking/config` | Default `StackingConfig` |

The pipeline converts the queued PNG/JPG frames to FITS, generates an SSF script
(adding a `calibrate` block when dark/flat/bias paths are provided), invokes
`siril-cli` via `asyncio.create_subprocess_exec`, and moves the stacked
output (`<target>_<session>.fit` and `.jpg`) into `/data/seestar/gallery/` so
it shows up in the existing Gallery page.

**SIRIL_BIN env var override.** The Dockerfile installs `siril` via apt,
which works on x86_64 and Ubuntu 22.04 aarch64 from the main repo (the
`lock042/siril` PPA has a broken ARM64 build as of early 2026 — do not use it).
For ARM64 hosts where apt-supplied Siril is unavailable, set `SIRIL_BIN` to a
wrapper that invokes Flatpak Siril, e.g.
`SIRIL_BIN="flatpak run --command=siril-cli org.siril.Siril"`. `SIRIL_TIMEOUT`
(default 600 seconds) controls the asyncio timeout for the subprocess call.

## seestar-enhance Service

Separate service in `UCIS-v1:src/services/seestar_enhance` — not checked into this repo.

- Runs on `:8504`
- Requires NVIDIA GPU (GraXpert + StarNet++ via CUDA)
- Called by the portal's sequence runner for post-stack enhancement
- See [UCIS-v1 PR #290](https://github.com/jmm2020/UCIS-v1/pull/290) for implementation

## Jetson Orin Deployment

Jetson Orin runs the portal + ALP backend (no GPU required for these two; seestar-enhance stays on workstation for now).

Deployment artefacts live in `deploy/jetson/` in this repo (generated from `UCIS-v1:projects/seestar-scope/deploy/jetson/`):
- `setup.sh` — idempotent one-shot installer (Docker + clone + build + systemd)
- `seestar-stack.service` — systemd unit; brings stack up at boot with `Restart=always`
- `.env.example` — Jetson-specific environment defaults (SEESTAR_IP=192.168.0.132)
- `README.md` — first-boot checklist, disk requirements, and troubleshooting

See `deploy/jetson/README.md` for the full first-boot procedure.

## Data Flow — Capture Session

```
User (browser)
  │ click "Start Exposure"
  ▼
portal views/imaging.py
  │ POST /api/v1/camera/0/startexposure
  ▼
ALP backend (ALPACA)
  │ S50 TCP command
  ▼
Seestar S50 hardware
  │ raw frame over TCP
  ▼
ALP backend
  │ GET /api/v1/camera/0/imagearray
  ▼
portal utils/image_processing.py
  │ normalize → PIL Image → apply_stretch()
  ▼
portal (display + save to captures/)

[Optional post-stack]
portal sequence runner
  │ POST http://localhost:8504/enhance
  ▼
seestar-enhance (GraXpert → StarNet++)
  │ enhanced FITS / PNG
  ▼
portal (display)
```

## CI Setup

GitHub Actions CI runs on every push/PR to `main` via `.github/workflows/ci.yml`.

**Pipeline steps:**

| Step | Command | What it checks |
|------|---------|----------------|
| Lint | `ruff check portal/` | Code quality (portal only — vendor code excluded) |
| Build | `docker compose build` | All three Docker images build on linux/amd64 |
| Test | `pytest portal/tests/ -m "not hardware"` | Unit tests pass (hardware-dependent tests skipped) |

**One-time setup (run from the seestar-scope repo root):**

```bash
# 1. Create private repo and push
gh repo create jmm2020/seestar-scope --private --source . --push

# 2. Enable branch protection (after first CI run is green)
gh api repos/jmm2020/seestar-scope/branches/main/protection \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -F "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=ci" \
  -F "enforce_admins=false" \
  -F "required_pull_request_reviews=null" \
  -F "restrictions=null"
```

After branch protection is enabled, direct pushes to `main` are blocked — all changes must go through a PR with passing CI.

## Ports Summary

| Port | Service | Protocol |
|------|---------|----------|
| 8502 | portal (Streamlit) | HTTP |
| 8503 | ALP backend (ASCOM ALPACA) | HTTP REST |
| 8504 | seestar-enhance | HTTP REST |
| 8091 | Stellarium Remote Control | HTTP REST |
| 32323 | Seestar S50 | TCP (proprietary) |
