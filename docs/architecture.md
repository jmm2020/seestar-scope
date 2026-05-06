# SeestarScope — System Architecture

> Documents the system **as it runs today** (2026-05-06).

## Overview

Two-stack design:

| Stack | Source | Host |
|-------|--------|------|
| **Portal** (Streamlit UI) | `portal/` in this repo | Workstation / Docker |
| **ALP backend** | `vendor/seestar_alp` (submodule, pinned `7bed951`) | Workstation / Docker |
| **seestar-enhance** | `UCIS-v1:src/services/seestar_enhance` | Workstation (GPU) |

## Network Topology

```
LAN (192.168.0.x)
  │
  ├── Workstation (or Jetson Orin)
  │     ├── portal           →  :8502  (Streamlit)
  │     ├── ALP backend      →  :8503  (FastAPI / ASCOM ALPACA)
  │     └── seestar-enhance  →  :8504  (FastAPI + CUDA — GraXpert + StarNet++)
  │
  └── Seestar S50
        └── 192.168.0.132:32323  (proprietary TCP)
```

The portal talks **only** to the ALP backend via ASCOM ALPACA REST.
The ALP backend talks to the S50 directly via TCP.
`seestar-enhance` is a standalone service called by the portal for post-stack processing.

## Portal Stack (`portal/`)

| File / Dir | Purpose |
|------------|---------|
| `app.py` | Streamlit entry point — page routing |
| `config.toml` | Runtime config (S50 IP, ports, imaging defaults) |
| `config_loader.py` | TOML config loader with env-var overrides |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build |
| `docker-compose.yml` | Workstation compose |
| `clients/alpaca_client.py` | ASCOM ALPACA REST client (telescope, camera, focuser, filter, switch) |
| `clients/stellarium_client.py` | Stellarium Remote Control client |
| `views/dashboard.py` | Live status — 2 s auto-refresh |
| `views/goto.py` | GoTo/Slew — manual coords, Stellarium, Messier/NGC catalog |
| `views/imaging.py` | Camera control — exposure, gain, filter, loop mode |
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

## seestar-enhance Service

Separate service in `UCIS-v1:src/services/seestar_enhance` — not checked into this repo.

- Runs on `:8504`
- Requires NVIDIA GPU (GraXpert + StarNet++ via CUDA)
- Called by the portal's sequence runner for post-stack enhancement
- See [UCIS-v1 PR #290](https://github.com/jmm2020/UCIS-v1/pull/290) for implementation

## Jetson Orin Deployment

Jetson Orin runs the portal + ALP backend (no GPU required for these two; seestar-enhance stays on workstation for now).

Deployment artefacts live in `UCIS-v1:deployments/jetson/`:
- `Dockerfile.jetson` — ARM64 build for portal
- `docker-compose.jetson.yml`
- systemd unit: `seestar.service`

Access via Tailscale / Cloudflare Tunnel — no open ports on LAN required.

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

## Ports Summary

| Port | Service | Protocol |
|------|---------|----------|
| 8502 | portal (Streamlit) | HTTP |
| 8503 | ALP backend (ASCOM ALPACA) | HTTP REST |
| 8504 | seestar-enhance | HTTP REST |
| 8091 | Stellarium Remote Control | HTTP REST |
| 32323 | Seestar S50 | TCP (proprietary) |
