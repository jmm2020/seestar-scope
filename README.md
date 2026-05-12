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
                   │ ASCOM ALPACA REST (native, firmware 7.34+)
                   ▼
             Seestar S50
          192.168.0.132:32323
```

| Service | Port | Notes |
|---------|------|-------|
| portal (Streamlit) | 8502 | Main control UI |
| portal backend (FastAPI) | 8503 | REST + WebSocket; published to host for browser WS |
| seestar-enhance | 8504 | AI post-stack (GraXpert + StarNet++) — UCIS-v1 service |

## Quick Start — Docker Compose

```bash
# Clone
git clone git@github.com:jmm2020/seestar-scope.git
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
# Clone
git clone git@github.com:jmm2020/seestar-scope.git
cd seestar-scope

# Start portal (talks directly to the S50's native ALPACA at :32323)
cd portal
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
