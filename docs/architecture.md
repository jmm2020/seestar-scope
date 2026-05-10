# SeestarScope — System Architecture

> Documents the system **as it runs today** (2026-05-06).

## Overview

Three-service bridge-network design (unified `docker-compose.yml` at repo root):

| Service | Source | Container Name | Port |
|---------|--------|----------------|------|
| **seestar-portal-ui** (Streamlit UI) | `portal/` in this repo | `seestar-portal-ui` | :8502 |
| **seestar-portal-backend** (FastAPI) | `portal/backend/` | `seestar-portal-backend` | :8503 |
| **seestar-alp** (ALP backend) | `vendor/seestar_alp` (submodule, pinned `7bed951`) | `seestar-alp` | :5555 (internal) |
| **seestar-enhance** | `UCIS-v1:src/services/seestar_enhance` | separate service | :8504 |

All three Docker services share the `seestar-net` bridge network. Both the UI (`:8502`) and portal backend (`:8503`) are published to the host; 8503 is accessed directly by the browser for WebSocket connections.

## Network Topology

```
LAN (192.168.0.x)
  │
  ├── Workstation (or Jetson Orin)
  │     └── Docker bridge: seestar-net
  │           ├── seestar-portal-ui      → host:8502  (Streamlit)
  │           ├── seestar-portal-backend → host:8503  (FastAPI — REST + WebSocket, published to host)
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
| `config.toml` | Runtime config (S50 IP, ports, imaging defaults, site coordinates) |
| `config_loader.py` | TOML config loader with env-var overrides |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build (used by `seestar-portal-ui` service) |
| `clients/alpaca_client.py` | ASCOM ALPACA REST client (telescope, camera, focuser, filter, switch) |
| `clients/stellarium_client.py` | Stellarium Remote Control client |
| `views/conditions.py` | Observing conditions page — weather + sun/moon/twilight dashboard |
| `views/dashboard.py` | Live status — 2 s auto-refresh |
| `views/goto.py` | GoTo/Slew — manual coords, Stellarium, Messier/NGC catalog |
| `views/imaging.py` | Camera control — exposure, gain, filter, loop mode; live-stack WebSocket panel |
| `views/stacking.py` | Siril stacking session management UI (start/add-frame/process/abort) |
| `views/focus.py` | Focuser position control |
| `views/sequence.py` | Multi-target automated imaging sequences |
| `views/settings.py` | App settings UI |
| `views/theme.py` | Cosmic CSS theme |
| `backend/routers/conditions.py` | REST endpoints: `/api/conditions/current`, `/api/conditions/forecast` |
| `backend/services/conditions_service.py` | ConditionsService — astropy astro data + Open-Meteo weather; degrades gracefully offline |
| `catalog/messier.py` | Messier catalog (110 objects) |
| `catalog/ngc_ic.py` | NGC/IC catalog subset |
| `utils/` | Coordinates, image processing (`image_enhancement.py` — 6-algorithm pipeline imported by backend), session logger |
| `tests/` | Unit + integration tests |

## Portal Backend (`portal/backend/`)

The FastAPI backend (`seestar-portal-backend`, port `:8503`) handles all persistent state and CPU-bound work, keeping the Streamlit UI stateless. It is distinct from `seestar-enhance` (GPU-only, separate service).

| File / Dir | Purpose |
|------------|---------|
| `main.py` | FastAPI app entry point; mounts routers |
| `config.py` | `Settings(BaseSettings)` — paths, ports, env-var overrides |
| `routers/postprocessing.py` | POST `/api/postprocessing/apply` (async job), GET `/jobs/{id}`, calibration frame CRUD |
| `routers/gallery.py` | Image gallery CRUD, thumbnail serving |
| `routers/autofocus.py` | Autofocus run endpoint |
| `services/postprocessing_service.py` | Enhancement pipeline: calibration frame management + `apply_pipeline()` |
| `services/autofocus_service.py` | Autofocus algorithm service |
| `services/siril_service.py` | Siril stacking integration |

**Security note**: `image_path` in `PostprocessingRequest` is restricted to `captures_dir`, `gallery_dir`, and `processing_dir` via Pydantic validator to prevent path traversal.

## Environment Variables

All env vars override their `config.toml` counterparts.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEESTAR_IP` | `192.168.0.132` | Seestar S50 IP address |
| `SITE_LAT` | `37.12` | Observing site latitude (°N positive) |
| `SITE_LON` | `-123.45` | Observing site longitude (°E positive) |
| `SITE_ELEVATION_M` | `0.0` | Site elevation in metres |
| `SITE_NAME` | `My Observatory` | Display name for the site |

## ALP Backend (`vendor/seestar_alp` submodule)

Pin: `7bed951` (smart-underworld/seestar_alp, 2026-03-01)

Key directories:

| Dir | Purpose |
|-----|---------|
| `device/` | Core S50 TCP protocol implementation |
| `front/` | ALP's own web UI (not used by this portal) |
| `imaging/` | Imaging pipeline |
| `docker/` | Docker configs |

The ALP backend exposes an ASCOM ALPACA REST API on `:5555`.

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
| `GET /api/stacking/config` | Default session configuration values |

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

## Data Flow — Stacking Session

```
User (browser)
  │ configure + click "Start Session"
  ▼
portal views/stacking.py
  │ POST /api/stacking/start  →  session_id returned
  │ POST /api/stacking/add-frame (× N — one per captured frame)
  │ POST /api/stacking/process
  ▼
FastAPI BackgroundTasks
  │ asyncio task: stacking_service.run_stacking()
  │   1. Convert PNG/JPG frames → FITS
  │   2. Generate SSF script (calibrate block if dark/flat/bias provided)
  │   3. asyncio.create_subprocess_exec(siril-cli)
  │   4. Move output → /data/seestar/gallery/
  ▼
portal views/stacking.py  ←  polls GET /api/stacking/status (2 s)
  │ on success: latest_result.output_jpeg shown; gallery page picks up output
```

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

## Data Flow — Post-Processing Pipeline

```
User (browser)
  │ click "Process" or "Apply Enhancement"
  ▼
portal views/imaging.py or views/gallery.py
  │ POST /api/postprocessing/apply  {image_path, stretch, ...}
  ▼
seestar-portal-backend (FastAPI, CPU)
  │ background task: PostprocessingService.apply_pipeline()
  │   ├── optional: _apply_calibration() (bias→dark→flat)
  │   └── utils/image_enhancement.run_pipeline()
  │         background_sub → hot_pixel → denoise → stretch → sharpen → color_balance
  │ output written to data/processed/
  ▼
portal polls GET /api/postprocessing/jobs/{job_id}
  │ status: running → completed
  ▼
portal displays before/after comparison
```

**CPU vs GPU split**: `seestar-portal-backend` runs all pipeline steps on CPU (suitable for Jetson Orin ARM64). `seestar-enhance` (separate service, GPU) handles GraXpert + StarNet++ post-stack enhancement.

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

## Status Streaming (`portal/backend/routers/status_ws.py`)

The FastAPI backend exposes a WebSocket status stream and a REST snapshot endpoint.

**Endpoints**:

| Endpoint | Protocol | Purpose |
|----------|----------|---------|
| `/api/status/ws` | WebSocket | Real-time push — telescope, processing, stack progress |
| `/api/status/live-stack` | HTTP GET | Last known stack state (for reconnect/page-load recovery) |

**WebSocket Message Types** (`MessageType` enum):

| Type | Broadcaster | Poll Interval | Payload Fields |
|------|-------------|---------------|----------------|
| `telescope_status` | `telescope_status_broadcaster` | 2 s | connected, ra, dec, altitude, azimuth, at_park; camera state/temp/gain; focuser position/temp |
| `processing_status` | `processing_status_broadcaster` | on change | session_id, status, output_fits, output_jpeg, error_message, stats |
| `stack_progress` | `stack_progress_broadcaster` | 3 s (on change) | frame_count, elapsed_s, snr_estimate, is_stacking, stage, mode, target, captured_at |
| `heartbeat` | `heartbeat_sender` | 30 s | timestamp only |
| `connected` | on connect | — | welcome message + reconnect snapshot |
| `error` | any broadcaster | on exception | error string |

Broadcasters are started lazily on the first WebSocket connection via `app.state._ws_tasks_started`.
The Streamlit UI's live-stack panel (`views/imaging.py`) connects directly from the browser to `host:8503`.

## Ports Summary

| Port | Service | Protocol |
|------|---------|----------|
| 8502 | portal (Streamlit) | HTTP |
| 8503 | portal backend (FastAPI) | HTTP REST + WebSocket |
| 5555 | ALP backend (ASCOM ALPACA) | HTTP REST |
| 8504 | seestar-enhance | HTTP REST |
| 8091 | Stellarium Remote Control | HTTP REST |
| 32323 | Seestar S50 | TCP (proprietary) |
