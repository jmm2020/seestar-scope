---
description: Prime agent with seestar-scope FastAPI backend context
---

# Prime Backend: portal-backend Orientation

## Objective

Orient on the FastAPI backend (`portal/backend/`) before working on routers, services, ALPACA/seestar_alp clients, WebSocket streams, or persistence.

## Process

### 1. Backend structure

!`ls portal/backend/`

!`ls portal/backend/routers/ portal/backend/services/ portal/backend/models/ 2>/dev/null`

### 2. Entry point

Read `portal/backend/main.py` in full — FastAPI app, mounted routers, startup/shutdown hooks, CORS, health endpoint.

Read `portal/backend/config.py` — env var handling. The real pydantic settings are: `seestar_ip`, `seestar_port`, `stellarium_host`, `stellarium_port`, `site_latitude`, `site_longitude`, `site_elevation_m`, `site_name`, `data_dir`, `siril_cli_path`, `auto_connect`. **There is no `ALP_HOST` / `ALP_PORT`** — don't search for it. Two more env vars (`SIRIL_BIN`, `SIRIL_TIMEOUT`) are read separately via `os.environ` in `services/stacking_service.py:97-99`, NOT through pydantic settings.

### 3. Client patterns

Read `portal/backend/clients.py` — it's a **30-line factory only**. The actual dual-channel ALPACA logic lives in `portal/clients/alpaca_client.py` (shared between UI and backend — and COPIED into the backend Docker image, so touching `portal/clients/` requires rebuilding both UI + backend images).

On a single `AlpacaClient` instance, two base URLs coexist:
- `base_url` → scope-native ALPACA :32323 (telescope state, focuser, camera, filterwheel, switch — works, no auth)
- `alp_base_url` → seestar_alp bridge :5555 (actions like goto/park/mosaic — wraps the broken :4700 channel)

Call sites pick the channel per-method — e.g. `get_telescope_status()` uses `base_url` (native), `seestar_action()` uses `alp_base_url` (bridge).

`pyproject.toml:6` exempts `portal/backend/clients.py` from E402 globally (per-file ignore). The exemption is **vestigial** — no E402-triggering imports currently in the file, may be removable.

### 4. Routers (the URL surface)

Skim each router file. Each one mounts a `/api/*` path group:

- `routers/telescope.py` — RA/Dec/altitude/connected via ALPACA :32323
- `routers/imager.py` — MJPEG stream control via seestar_alp :5555
- `routers/stacking.py` — live-stack lifecycle (start/stop/status)
- `routers/sessions.py` — session list / detail
- `routers/gallery.py` + `routers/gallery_onboard.py` — local thumbnails + scope onboard archive (guest channel :4701 + HTTP :80)
- `routers/conditions.py` — weather / seeing
- `routers/autofocus.py`, `routers/platesolve.py`, `routers/postprocessing.py`, `routers/processing.py` — long-running jobs
- `routers/status_ws.py` — WebSocket for live status (browser ↔ backend, port 8503 published to host for direct WS). Has **4 broadcaster tasks** running in parallel:
  - `telescope_status` — 2s poll
  - `processing_status` — 1s on-change
  - `heartbeat` — 30s
  - `stack_progress` — 3s on-change; **persists `request.app.state.live_stack_state` for reconnect recovery**. The reconnect bootstrap endpoint is GET `/api/status/live-stack` — clients reconnecting after a disconnect should hit this first to rehydrate state, then resume the WebSocket.

### 4a. Routers (DI patterns)

Three DI patterns coexist in `portal/backend/routers/` — newer routers should follow pattern (3):

1. **`request.app.state.<dep>`** — `telescope.py` and `status_ws.py` pull `alpaca`, `stellarium`, `live_stack_state` off `request.app.state` (wired in `backend/main.py` startup). Legacy pattern; fine for app-lifetime singletons that the startup hook owns.
2. **`Depends(get_<thing>)` with explicit getter** — `gallery.py` uses `Depends(get_db)`, `sessions.py` uses `Depends(get_sessions_db)`. **Never bare `Depends(<Class>)`** — always go through an explicit getter function.
3. **Module-level lazy singleton** — newer routers (`imager.py`, `stacking.py`, `gallery_onboard.py`, `postprocessing.py`) define a `_<name>_client` or `_<name>_service` at module top with a `_get_<name>()` accessor that does lazy init on first call. Reason: keeps test-time module import cheap (no scope I/O on import) and lets `dependency_overrides` swap the dep cleanly.

### 4b. Background jobs

`BackgroundTasks` is used for long-running work in:
- `routers/stacking.py:165` (live-stack lifecycle)
- `routers/processing.py` (frame processing pipeline)
- `routers/autofocus.py` (autofocus sweep)

Four different job-state patterns coexist — pick deliberately when adding a new long-running endpoint:
- `postprocessing.py` — **capped `OrderedDict(_MAX_JOBS=100)`**, evicts oldest
- `processing.py` — **uncapped dict** (memory leak risk on long sessions)
- `platesolve.py` — **module-import `ASTAPService`** with hardcoded `/data/seestar` path
- `stacking.py` — **lazy singleton service** owns the state machine

### 4c. Stellarium integration

Three endpoints under `/api/telescope/stellarium/*` in `routers/telescope.py:329-395`. Client lives in `portal/clients/stellarium_client.py` (shared with UI). Env vars: `STELLARIUM_HOST`, `STELLARIUM_PORT` (default `localhost:8091`). Used by `views/goto.py`, `views/sequence.py`, `views/settings.py`.

### 4d. Legacy `portal/backend/app/` subpackage

> **Warning** — `portal/backend/app/services/siril_service.py` and `portal/backend/app/routers/processing.py` exist alongside the canonical `services/` and `routers/`. When searching for siril logic or processing routes, look in `app/services/` and `app/routers/` too — `grep` for `siril` in `services/` alone will miss the canonical implementation.

### 5. Services (the business logic)

- `services/stacking_service.py` — stacking state machine + job queue
- `services/conditions_service.py` — weather provider integration
- `services/autofocus_service.py`, `services/platesolve_service.py`, `services/postprocessing_service.py`

Routers should stay thin; services own the state machines and long-running work.

### 6. Persistence model

Two SQLite databases share `data_dir/seestar_gallery.db`. `GalleryDatabase` (`database.py:32`) and `SessionDatabase` (`database.py:82`) open **separate connections to the same file**. There are no migrations — schemas are managed in-Python via `init_database()` and `init_sessions_database()` called at startup. If you add a column, you do it in the init function and accept that fresh databases get the new schema while existing ones don't (no migration framework).

### 7. Test patterns

!`ls portal/tests/ | grep -E "(router|service)" | head -20`

The canonical conventions to match:

- **`FakeScopeServer`** — in-process threaded TCP harness in `test_seestar_observer.py` (also copy-pasted to `test_seestar_archive.py`). Use this for scope-protocol tests that need a stand-in TCP endpoint on a free port.
- **In-memory SQLite + `dependency_overrides`** for FastAPI router tests. Canonical example: `test_sessions_router.py:24-30` — open an in-memory SQLite DB in the fixture, init schema, then `app.dependency_overrides[get_sessions_db] = lambda: db` for the test's lifetime.
- **`pytest-asyncio` mode is `auto`** in `pyproject.toml`. Some tests still carry explicit `@pytest.mark.asyncio` decorators — redundant but harmless. Don't add the decorator on new tests; the auto mode covers it.
- **No coverage tooling** — `pytest-cov` is not installed and there are no coverage thresholds. Aim for behavior coverage, not %.

Read 2-3 representative router tests (`test_imager_router.py`, `test_conditions_router.py`) and one service test (`test_conditions_service.py`) before writing new ones.

## Output Report

In under 200 words:

- The 4-5 router groups and what each owns
- The split between scope-native ALPACA (:32323) and seestar_alp bridge (:5555) — which routers go through which path
- WebSocket endpoint(s) and what they stream
- Persistence model (SQLite via `gallery-db` volume? In-memory state? Where session data lives)
- Any background tasks / job queues spotted

Don't start coding until this is in your context.
