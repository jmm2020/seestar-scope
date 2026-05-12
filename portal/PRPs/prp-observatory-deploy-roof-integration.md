# PRP: SeestarScope Observatory Deploy + Roof Control Integration

**Version**: 1.0
**Date**: 2026-05-05
**Owner**: John (operator)
**WARP Estimate**: 5 (~half day to 1 day)
**Dependencies**: SeestarScope Phase 3 (shipped), Jetson Orin Nano 8GB @ 192.168.0.234
**Project**: SEESTARSCOPE
**Resume context**: `memgraph_20260504_195041_440521`

## 1. Objective

Deploy the SeestarScope platform (Streamlit UI + FastAPI backend talking directly to the Seestar S50's native ALPACA REST at `192.168.0.132:32323`) to the Jetson Orin Nano 8GB at the observatory, and integrate observatory roof control via an eWeLink Sonoff switch (LAN mode, no cloud dependency). End state: a single browser tab on any LAN device drives slew, capture, gallery review, **and** opens/closes the observatory roof.

## 2. Background & Context

SeestarScope (Phase 3 complete, March 2026) is a Streamlit + FastAPI control plane for the ZWO Seestar S50 smart telescope. It currently runs on the dev box during scope sessions. The observatory is now physically ready to host the rig full-time, so the platform moves to a dedicated Jetson Orin Nano 8GB on-site.

The Jetson has been previously used for LedgerLLM/OpenClaw and is being repurposed (cleanup commands staged in `memgraph_20260504_195041_440521`). The Jetson sits on the same LAN as both the Seestar S50 (`192.168.0.132`) and the Sonoff roof switch.

The roof switch is a Sonoff/eWeLink basic on/off relay. The library `skydiver/ewelink-api` (JavaScript, actively maintained, 284★, last commit days ago) supports **LAN mode via zeroconf** — no cloud / internet dependency. This is critical: observatory internet is unreliable, and a roof that depends on a cloud round-trip is a liability when you need to close before weather hits.

## 3. Phase-0 Prerequisites

- ✅ Jetson reachable at 192.168.0.234 (verified 2026-05-04 via SSH)
- ✅ Node.js 22.22.0 + npm 10.9.4 already installed on Jetson
- ✅ Docker 29.1.3 already installed on Jetson
- ✅ JetPack R36.4.7 (L4T) base
- ✅ LedgerLLM artifacts archived to `/media/jmm2020/AIDrive1/UCIS-v1/data/archive/ledgerllm/`
- ✅ SeestarScope project at `/media/jmm2020/KnowledgeBase/seestar_scope/` (11 views, FastAPI backend, docker-compose.seestar.yml)
- ⏳ Jetson cleanup not yet executed (Phases 1-5 staged in resume memory)
- ⏳ eWeLink switch credentials (account email + password) — needed for first device discovery
- ⏳ eWeLink switch device ID — captured during first authenticated discovery, then LAN-mode lookups use it directly

## 4. Implementation Plan

### Step 1: Jetson cleanup (~5 minutes) — staged

Execute the Phase 1-5 commands from `memgraph_20260504_195041_440521`:
- Stop + disable `ledgerai-upload.service` and `ollama.service`
- `rm -rf ~/.ollama/models` (~32GB)
- Wipe LedgerAI/OpenClaw home-dir artifacts (`LedgerAI-Watch/`, `nano_llm_data/`, `jetson-containers/`, etc.)
- `docker rmi` the 57GB of unused ML images
- Verify: `df -h`, `free -h`, `ollama list` (empty), `docker images` (empty)

Expected end state: ~90GB freed, ~6GB RAM available, no extraneous services running.

### Step 2: Provision SeestarScope code on Jetson

- Files: `/opt/seestar_scope/` (rsync target on Jetson)
- Action:
  ```bash
  sshpass -p 2020 rsync -av --exclude='.pytest_cache' --exclude='__pycache__' --exclude='captures/' \
    /media/jmm2020/KnowledgeBase/seestar_scope/ \
    jmm2020@192.168.0.234:/opt/seestar_scope/
  ```
- ARM64 verification: SeestarScope is pure Python (Streamlit + FastAPI + httpx + astropy + Pillow) — all wheels exist for aarch64.
- Validation: `find /opt/seestar_scope -name "*.py" | wc -l` matches local count.

### Step 3: Build eWeLink Node sidecar container

- Files: `/opt/roof_control/` on Jetson (new directory)
- Action: Create a thin Node service wrapping `skydiver/ewelink-api`, run as a Docker container exposing 3 HTTP routes.
- Spec (target: `~80MB Node-Alpine container`):
  ```javascript
  // /opt/roof_control/server.js
  const express = require('express');
  const eWeLink = require('ewelink-api');
  const app = express();
  app.use(express.json());

  let connection;
  async function getConn() {
    if (!connection) {
      connection = new eWeLink({
        email: process.env.EWELINK_EMAIL,
        password: process.env.EWELINK_PASSWORD,
        region: 'us',
      });
      await connection.getCredentials();  // primes LAN mode
    }
    return connection;
  }

  app.post('/roof/open', async (req, res) => {
    try {
      const c = await getConn();
      await c.setDevicePowerState(process.env.ROOF_DEVICE_ID, 'on');
      res.json({ ok: true, state: 'open' });
    } catch (e) { res.status(500).json({ error: e.message }); }
  });

  app.post('/roof/close', async (req, res) => {
    try {
      const c = await getConn();
      await c.setDevicePowerState(process.env.ROOF_DEVICE_ID, 'off');
      res.json({ ok: true, state: 'closed' });
    } catch (e) { res.status(500).json({ error: e.message }); }
  });

  app.get('/roof/state', async (req, res) => {
    try {
      const c = await getConn();
      const status = await c.getDevicePowerState(process.env.ROOF_DEVICE_ID);
      res.json({ ok: true, state: status.state === 'on' ? 'open' : 'closed' });
    } catch (e) { res.status(500).json({ error: e.message }); }
  });

  app.get('/health', (req, res) => res.json({ ok: true }));
  app.listen(8504, '0.0.0.0', () => console.log('roof_control on :8504'));
  ```
- `Dockerfile`:
  ```Dockerfile
  FROM node:22-alpine
  WORKDIR /app
  COPY package.json .
  RUN npm install --omit=dev
  COPY server.js .
  EXPOSE 8504
  HEALTHCHECK --interval=30s --timeout=5s CMD wget -q -O - http://localhost:8504/health || exit 1
  CMD ["node", "server.js"]
  ```
- `package.json`:
  ```json
  { "name": "roof-control", "version": "1.0.0",
    "dependencies": { "express": "^4.21.0", "ewelink-api": "^4.4.0" } }
  ```
- One-time device discovery: run the container interactively first to capture `ROOF_DEVICE_ID` (will list all devices on the eWeLink account); persist into `.env`.
- Validation: `curl -X POST http://192.168.0.234:8504/roof/open` toggles the physical switch (and the roof). `GET /roof/state` reports `open`. Same for `close`.

### Step 4: Wire roof control into SeestarScope FastAPI backend

- Files: `seestar_scope/backend/routers/roof.py` (new), `seestar_scope/backend/main.py` (mount router)
- Action:
  ```python
  # backend/routers/roof.py
  from fastapi import APIRouter, HTTPException
  import httpx, os

  router = APIRouter(prefix="/roof", tags=["roof"])
  ROOF_URL = os.environ.get("ROOF_CONTROL_URL", "http://localhost:8504")

  @router.post("/open")
  async def open_roof():
      async with httpx.AsyncClient(timeout=10) as c:
          r = await c.post(f"{ROOF_URL}/roof/open")
          if r.status_code != 200:
              raise HTTPException(502, f"roof_control failed: {r.text}")
          return r.json()

  @router.post("/close")
  async def close_roof():
      async with httpx.AsyncClient(timeout=10) as c:
          r = await c.post(f"{ROOF_URL}/roof/close")
          if r.status_code != 200:
              raise HTTPException(502, f"roof_control failed: {r.text}")
          return r.json()

  @router.get("/state")
  async def roof_state():
      async with httpx.AsyncClient(timeout=5) as c:
          r = await c.get(f"{ROOF_URL}/roof/state")
          return r.json() if r.status_code == 200 else {"ok": False, "state": "unknown"}
  ```
- Validation: `curl http://192.168.0.234:8503/roof/state` returns the same value as direct call to `:8504`. Open/close round-trips toggle the switch.

### Step 5: Add roof control card to dashboard

- Files: `seestar_scope/views/dashboard.py` (modify) — add "Observatory Roof" card alongside existing telescope/mount controls
- Action: Two big buttons (Open / Close) plus a state indicator. Disabled-while-pending pattern. State auto-refreshes on dashboard render.
  ```python
  # In dashboard.py — add a new section
  st.markdown("### 🏠 Observatory Roof")
  col1, col2, col3 = st.columns([1, 1, 2])
  state = httpx.get(f"{API_BASE}/roof/state", timeout=5).json().get("state", "unknown")

  with col1:
      if st.button("🔓 Open Roof", disabled=(state == "open"), use_container_width=True):
          with st.spinner("Opening..."):
              r = httpx.post(f"{API_BASE}/roof/open", timeout=15).json()
              st.success(f"Roof: {r.get('state')}") if r.get("ok") else st.error(r)
              st.rerun()
  with col2:
      if st.button("🔒 Close Roof", disabled=(state == "closed"), use_container_width=True, type="primary"):
          with st.spinner("Closing..."):
              r = httpx.post(f"{API_BASE}/roof/close", timeout=15).json()
              st.success(f"Roof: {r.get('state')}") if r.get("ok") else st.error(r)
              st.rerun()
  with col3:
      icon = {"open": "🟢", "closed": "🔴", "unknown": "⚪"}[state]
      st.metric("State", f"{icon} {state.title()}")
  ```
- Validation: Render `dashboard.py` in browser; click Open → physical switch flips → state shows "Open" with green dot.

### Step 6: Compose stack for the observatory (single docker-compose)

- Files: `/opt/seestar_scope/docker-compose.observatory.yml` (new, on Jetson)
- Action: Single compose file that brings up all 4 services with restart policies:
  ```yaml
  services:
    seestar-backend:
      build:
        context: /opt/seestar_scope
        dockerfile: backend/Dockerfile
      network_mode: host        # FastAPI on :8503; talks to S50 native ALPACA at 192.168.0.132:32323
      restart: unless-stopped
      environment:
        - SEESTAR_IP=192.168.0.132
        - SEESTAR_PORT=32323
        - ROOF_CONTROL_URL=http://localhost:8504
      volumes:
        - /opt/seestar_scope/captures:/app/captures
        - seestar-data:/app/data

    roof-control:
      build: /opt/roof_control
      network_mode: host        # :8504, needs LAN access for zeroconf
      restart: unless-stopped
      env_file: /opt/roof_control/.env

    seestar-ui:
      build:
        context: /opt/seestar_scope
        dockerfile: Dockerfile
      ports: ["8501:8501"]
      depends_on: [seestar-backend]
      restart: unless-stopped
      environment:
        - API_BASE=http://localhost:8503

  volumes:
    seestar-data:
  ```
- Validation: `docker compose up -d` brings 4 healthy containers; `docker compose ps` shows all `healthy`.

### Step 7: Auto-start on boot

- Files: `/etc/systemd/system/seestar-observatory.service` (new, on Jetson)
- Action: systemd unit that runs `docker compose up -d` on boot, brings down on shutdown.
  ```ini
  [Unit]
  Description=SeestarScope Observatory Stack
  After=docker.service network-online.target
  Requires=docker.service

  [Service]
  Type=oneshot
  RemainAfterExit=yes
  WorkingDirectory=/opt/seestar_scope
  ExecStart=/usr/bin/docker compose -f docker-compose.observatory.yml up -d
  ExecStop=/usr/bin/docker compose -f docker-compose.observatory.yml down

  [Install]
  WantedBy=multi-user.target
  ```
- `sudo systemctl enable --now seestar-observatory.service`
- Validation: `sudo reboot` → after Jetson is back online, `curl http://192.168.0.234:8501` returns the Streamlit landing page without manual intervention.

### Step 8: Network + first-light validation

- Action: From a laptop on the LAN, open `http://192.168.0.234:8501`. Run the full session sequence:
  1. **Open roof** (eWeLink → physical switch → roof opens)
  2. **Connect telescope** (ALPACA `connected=true` to S50)
  3. **GoTo target** (e.g. M31 from Messier catalog)
  4. **Capture** (one frame, save to gallery)
  5. **Park scope**
  6. **Close roof**
- Time the full sequence end-to-end. Document any latency or failure points.
- Validation: All 6 steps complete without manual intervention. Captured frame visible in Gallery view.

### Step 9: Safety + auto-close on weather (deferred, separate PRP)

Out of scope for v1.0 — flagged for follow-up:
- Weather API integration (e.g. `wttr.in` or Open-Meteo) polled every N minutes
- Auto-close trigger when wind > threshold or precipitation imminent
- Manual override + confirm dialog
- Persistent log of auto-close events

## 5. Success Criteria

- [ ] Jetson cleanup complete; ~90GB freed; no Ollama/LedgerAI processes running
- [ ] All 3 containers (`seestar-backend`, `roof-control`, `seestar-ui`) healthy via `docker compose ps`
- [ ] systemd unit brings the stack up on Jetson reboot without manual intervention
- [ ] `http://192.168.0.234:8501` renders SeestarScope dashboard from any LAN device
- [ ] Roof control card shows current state, opens/closes the physical switch on click
- [ ] Full first-light sequence (open → connect → goto → capture → park → close) completes end-to-end
- [ ] eWeLink LAN mode confirmed: pull the Jetson off the public internet (firewall rule), roof control still works

## 6. Evidence Requirements

- `df -h` on Jetson before vs after cleanup (showing freed space)
- `docker compose ps` output showing all 4 containers healthy
- Browser screenshot of SeestarScope dashboard with Roof Control card visible
- Video or photo of physical roof opening/closing in response to UI click
- Captured FITS or PNG frame from a target acquired during first-light sequence
- systemd journalctl log showing successful boot-time stack startup

## 7. Test Plan

| Test | Input | Expected Output |
|------|-------|-----------------|
| Jetson cleanup | Phase 1-5 commands | Ollama removed, ~90GB freed, services stopped |
| ARM64 build | `docker compose build` | All 3 images build without errors |
| Backend health | `curl :8503/health` | 200 OK |
| Native ALPACA reach | `curl :8503/api/telescope/connected` (proxied to S50 :32323) | Returns telescope state |
| Roof sidecar health | `curl :8504/health` | 200 OK |
| Roof open | `POST :8504/roof/open` | Physical switch flips on, response `{ok:true, state:"open"}` |
| Roof close | `POST :8504/roof/close` | Physical switch flips off, response `{ok:true, state:"closed"}` |
| Backend → sidecar passthrough | `POST :8503/roof/open` | Same effect as direct |
| Dashboard UI | Click Open in browser | Roof opens, state indicator turns green |
| Reboot persistence | `sudo reboot` | Stack auto-starts within 60s of boot |
| LAN-mode verification | Block egress to `*.coolkit.cc` | Roof control still works |
| First-light sequence | UI walkthrough | All 6 steps complete; frame captured |

## 8. Rollback Plan

- **Stack rollback**: `sudo systemctl stop seestar-observatory; docker compose down` — Jetson is idle, no harm done.
- **Roof sidecar rollback**: `docker compose stop roof-control` — telescope still works, roof needs manual operation.
- **Total rollback**: Restore archived LedgerLLM artifacts from `/media/jmm2020/AIDrive1/UCIS-v1/data/archive/ledgerllm/` if Jetson needs to revert to LedgerAI duty.
- **Backend isolation**: each container has `restart: unless-stopped`, so a single-service crash doesn't take the rig down.
- **Manual roof operation**: physical switch on the eWeLink relay still works regardless of software state — no software lock-out.

## 9. Blast Radius

- **Telescope**: low — ALPACA is stateless REST, idempotent PUTs; running two clients (laptop dev + Jetson) was already proven safe in the March 2026 three-agent debate (`memgraph_20260302_094453_735677`).
- **Roof**: medium — software bug could leave the roof open during weather. Mitigation: physical switch is always available as manual override. Phase 9 (deferred) adds weather-based auto-close.
- **Network**: low — Jetson sits on the same subnet as S50 and eWeLink switch; no NAT, no port-forward, no external dependencies for runtime.
- **Power**: medium — observatory power loss kills everything including roof control. Out of scope; UPS sizing is a hardware question, not a PRP concern.
- **eWeLink account**: small operational risk — credentials stored in `.env` on the Jetson. If the eWeLink account is compromised, an attacker could open the roof. Mitigation: dedicated email + 2FA on the eWeLink account; rotate after deploy.

## 10. Strategic Alignment

This finishes the SeestarScope arc that started Feb 2026: dev-box prototype → on-rig deployment → headless observatory operation. The roof integration removes the last manual step in a session, enabling the longer-term goal of **scheduled unattended observation runs**. It also validates the Jetson as the right size of edge device for "small smart-instrument" duty — useful pattern for any future smart-rig project.

## 11. Operational Value

- **Sessions per week**: removing the "drive to the observatory to open the roof" friction enables casual short sessions on clear nights.
- **Imaging throughput**: combine with the existing Phase 3 imaging pipeline → automated multi-target sequences become realistic.
- **Reliability story**: eWeLink LAN mode means the roof works even when the cable internet is down (which it often is during the storms that are the main reason you'd want to close the roof).

## 12. Infrastructure Notes

- **Jetson @ 192.168.0.234**: JetPack R36.4.7, Docker 29.1.3, Node 22.22.0, 8GB unified RAM (~6GB available post-cleanup), 727GB free on /
- **Network shape**: Jetson on observatory LAN (192.168.0.0/24). Reaches S50 at 192.168.0.132:32323 (native ALPACA REST, firmware 7.34+). Reaches eWeLink switch via zeroconf on the same subnet.
- **Ports used**:
  - `:8501` — Streamlit UI (the one humans hit)
  - `:8503` — FastAPI backend (talks to S50 :32323 directly)
  - `:8504` — eWeLink Node sidecar (internal; backend proxies)
- **Secrets**: `EWELINK_EMAIL`, `EWELINK_PASSWORD`, `ROOF_DEVICE_ID` in `/opt/roof_control/.env`. Mode 600. Not committed.
- **Captures volume**: `/opt/seestar_scope/captures` on Jetson NVMe (727GB headroom — months of FITS frames before space matters).
- **Credentials reference**: Jetson SSH = `jmm2020` / `2020` (sudo same) per `memgraph_20251231_094637_073885`.

## 13. What's Deferred (separate PRPs)

- **Weather-aware auto-close** (Step 9 above) — own PRP. Wind/precipitation polling, threshold config, auto-close + alert.
- **Scheduled session runner** — overnight target-list executor that opens roof, runs N captures across M targets, closes roof at dawn or on weather alert.
- **Imaging Pipeline Phase 2** — picks up the three-agent-debate-locked PRP from `memgraph_20260302_094453_735677` (Phase 1 modules already delivered by Doctor/Lal/Lore).
- **Off-site monitoring** — if/when we want a dashboard view from outside the LAN, add Cloudflare Tunnel or Tailscale; out of scope for v1.0.
- **Re-register Jetson Bridge MCP** in Claude Code (`ucis_jetson_bridge_mcp.py` exists but isn't loaded) — small ops task, not a PRP.
