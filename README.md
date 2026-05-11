# seestar-scope

Private repo for the Seestar S50 telescope control and imaging portal.

## Architecture

```
Browser
  │
  ▼
┌─────────────────────────────────────────────┐
│  portal (Streamlit)  :8502                                       │
│  UI — control, imaging, live-stack, sequences, GoTo, conditions  │
└──────────────────┬──────────────────────────┘
                   │ ASCOM ALPACA REST
                   ▼
┌─────────────────────────────────────────────┐
│  portal backend  :8503  (FastAPI)           │
│  REST + WebSocket — status, stacking, jobs  │
└──────────────────┬──────────────────────────┘
                   │ ASCOM ALPACA REST
                   ▼
┌─────────────────────────────────────────────┐
│  ALP backend  :5555                         │
│  vendor/seestar_alp — device + scheduler    │
└──────────────────┬──────────────────────────┘
                   │ TCP (proprietary Seestar protocol)
                   ▼
             Seestar S50
          192.168.0.132:32323
```

| Service | Port | Notes |
|---------|------|-------|
| portal (Streamlit) | 8502 | Main control UI |
| portal backend (FastAPI) | 8503 | REST + WebSocket; published to host for browser WS |
| ALP backend | 5555 | ASCOM ALPACA proxy to S50 |
| seestar-enhance | 8504 | AI post-stack (GraXpert + StarNet++) — UCIS-v1 service |

## Quick Start — Docker Compose

```bash
# Clone with submodule
git clone --recurse-submodules git@github.com:jmm2020/seestar-scope.git
cd seestar-scope

# Configure environment
cp .env.example .env
# Edit .env: set SEESTAR_IP to your S50's IP address; verify SEESTAR_PORT=32323

# Build and start all services
docker compose build
docker compose up -d

# Portal UI is available at http://localhost:8502
# View logs:
docker compose logs -f
```

## Quick Start — Workstation Dev

```bash
# Clone with submodule
git clone --recurse-submodules git@github.com:jmm2020/seestar-scope.git
cd seestar-scope

# Start ALP backend
cd vendor/seestar_alp
python3 device/seestar_device.py

# In another terminal — start portal
cd ../../portal
pip install -r requirements.txt
streamlit run app.py --server.port 8502
```

## Quick Start — Jetson Deploy

```bash
# From the seestar-scope repo root (or run standalone on the Jetson):
bash deploy/jetson/setup.sh
```

The script is idempotent — safe to re-run. It installs Docker, clones the repo,
configures `.env`, builds the ARM64 images, and installs the `seestar-stack` systemd service.

See `deploy/jetson/README.md` for the full first-boot checklist, requirements, and troubleshooting.
See `docs/jetson_build_notes.md` for ARM64 dependency verification and `docker buildx` build commands.

When ready to cut over from workstation to Jetson, follow `docs/migration_runbook.md`
(pre-flight checklist, `scripts/smoke_test.sh` validation, rollback procedure).

## Attribution

`vendor/seestar_alp` is a git submodule pointing to
[smart-underworld/seestar_alp](https://github.com/smart-underworld/seestar_alp)
pinned to commit `7bed951` (March 1 2026).

The upstream project is distributed under its own licence — see
`vendor/seestar_alp/LICENSE.txt` and `vendor/seestar_alp/LICENSE-Seestar_Alp.txt`.
This repo does not fork or modify ALP source; it uses the submodule strategy to
preserve clean licensing and allow upstream tracking when desired.
