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

> **Auth prerequisite**: The portal requires Supabase credentials to log in.
> Follow `docs/auth-billing-setup.md` §1 to provision a free Supabase project and capture
> `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_JWT_SECRET`. Without them the
> login form will appear but all submissions will silently fail.

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

> **Auth prerequisite**: The portal requires Supabase credentials to log in.
> Follow `docs/auth-billing-setup.md` §1 to provision a free Supabase project and capture
> `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_JWT_SECRET`. Without them the
> login form will appear but all submissions will silently fail.

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

## Optional: Stellarium Integration

The portal integrates with [Stellarium](https://stellarium.org/) to let you click a target in its sky map and slew the telescope to it. Features appear in the Dashboard, GoTo, and Sequence views. Stellarium is **optional** — the portal works without it.

### Enabling Remote Control in Stellarium

1. Open Stellarium
2. Go to **Configuration** (F2) → **Plugins** → **Remote Control**
3. Click **Configure**, enable **Start server**, set port to `8090`
4. Save settings and restart Stellarium (or toggle the plugin off/on)

### Docker Networking

In the Docker deployment, `localhost` inside the container does **not** reach the Jetson host or your workstation. If Stellarium runs on a different machine, set `STELLARIUM_HOST` in your `.env` file:

```env
STELLARIUM_HOST=192.168.0.36   # workstation IP where Stellarium runs
STELLARIUM_PORT=8090
```

To verify the connection:
```bash
curl http://<stellarium-host>:8090/api/main/status
```

A JSON response confirms Remote Control is active.
