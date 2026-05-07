# seestar-scope

Private repo for the Seestar S50 telescope control and imaging portal.

## Architecture

```
Browser
  │
  ▼
┌─────────────────────────────────────────────┐
│  portal (Streamlit)  :8502                  │
│  UI — control, imaging, sequences, GoTo     │
└──────────────────┬──────────────────────────┘
                   │ ASCOM ALPACA REST
                   ▼
┌─────────────────────────────────────────────┐
│  ALP backend  :8503                         │
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
| ALP backend | 8503 | ASCOM ALPACA proxy to S50 |
| seestar-enhance | 8504 | AI post-stack (GraXpert + StarNet++) — UCIS-v1 service |

## Quick Start — Docker Compose

```bash
# Clone with submodule
git clone --recurse-submodules git@github.com:jmm2020/seestar-scope.git
cd seestar-scope

# Configure environment
cp .env.example .env
# Edit .env: set SEESTAR_IP to your S50's IP address

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

See `docs/architecture.md` for the Jetson Orin deployment playbook and
`UCIS-v1/deployments/jetson/` for Dockerfiles and systemd units.
See `docs/jetson_build_notes.md` for ARM64 build verification (dependency
tables and `docker buildx` commands).

## Attribution

`vendor/seestar_alp` is a git submodule pointing to
[smart-underworld/seestar_alp](https://github.com/smart-underworld/seestar_alp)
pinned to commit `7bed951` (March 1 2026).

The upstream project is distributed under its own licence — see
`vendor/seestar_alp/LICENSE.txt` and `vendor/seestar_alp/LICENSE-Seestar_Alp.txt`.
This repo does not fork or modify ALP source; it uses the submodule strategy to
preserve clean licensing and allow upstream tracking when desired.
