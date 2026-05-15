---
description: Prime agent with seestar-scope Streamlit UI context
---

# Prime Frontend: portal Streamlit UI Orientation

## Objective

Orient on the Streamlit UI (`portal/`) before working on views, theming, the multi-page layout, or the HTTP clients that talk to the FastAPI backend.

## Process

### 1. UI structure

!`ls portal/`

!`ls portal/views/ portal/clients/ portal/utils/ 2>/dev/null`

### 2. Entry point + multi-page layout

Read `portal/app.py` — Streamlit entry, page router, sidebar, session state init, theme bootstrap.

Read `portal/config_loader.py` and `portal/config.toml` — how UI config is loaded (timezone, backend URL, scope IP/port).

### 3. Views (each = one page)

Skim each view's top 30 lines:

- `views/dashboard.py` — main control panel (state + thumbnails)
- `views/imaging.py` — **1191-line god-file**. Renders MJPEG live view (`_render_live_view`, `_resolve_stream_host`), session status table, live-stack progress panel with embedded WebSocket JS, camera controls, capture flow, exposure poll loop, **and a full PixInsight-style enhancement panel** (`_render_enhancement_panel`) that calls `utils/image_enhancement.py` (15KB of stretch/STF/GHS/star-detection numpy). Also has a layering wart: `from backend.config import settings as _backend_settings` at line 37 — UI imports backend module (wrapped in try/except).
- `views/imaging_stacked.py` — stacked frame view
- `views/live_status.py` — telescope state widget (RA/Dec/altitude)
- `views/goto.py` + `views/slew_helpers.py` — target selection from catalog
- `views/skymap.py` — sky visualization
- `views/sequence.py` — multi-target session planning
- `views/gallery.py` — onboard archive browser
- `views/sessions.py` — session history
- `views/conditions.py` — weather/seeing display
- `views/focus.py` + `views/autofocus.py` — focusing UI
- `views/platesolve.py` — platesolve trigger
- `views/stacking.py` — live-stack controls
- `views/settings.py` — preferences
- `views/theme.py` — Streamlit theming helpers

### 4. HTTP clients (the boundary) — **DUAL ARCHITECTURE**

> The "no `requests.get` in views" claim that appeared in earlier docs is **wrong**. This codebase has a dual UI architecture; understand both paths before touching any view.

**Path A — direct `requests` to FastAPI (the dominant pattern for the new surface):**

8 of 18 views import `requests` and call FastAPI directly. Each defines its own module-level `BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")`. Views that do this:

- `imaging.py`, `gallery.py`, `conditions.py`, `stacking.py`, `autofocus.py`, `platesolve.py`, `live_status.py`, `settings.py`

Plus `goto.py` is special — it calls `seestar_alp` **directly** (bypassing the backend entirely) via `requests.put` to `http://{seestar_alp_host}:{port}/api/v1/telescope/1/action`.

**Path B — direct AlpacaClient calls (the legacy surface for telescope state):**

Streamlit views call `AlpacaClient` DIRECTLY for telescope state, bypassing FastAPI. Views on this path: `dashboard.py`, `focus.py`, `slew_helpers.py`, `live_status.py`. They pull the client off `st.session_state["alpaca"]`.

**`portal/clients/` is NOT thin HTTP wrappers.** It holds **stateful socket/session clients** shared between UI and backend:

- `AlpacaClient`, `StellariumClient`, `SessionsClient`, `SeestarObserverClient`, `SeestarArchiveClient`, `SeestarImagerClient`

Only `sessions_client.py` looks like a thin HTTP wrapper. When adding a new view, decide deliberately: stateful client (add to `portal/clients/`) vs ad-hoc HTTP (inline `requests` + per-view `BACKEND_URL`).

### 4a. MJPEG embed pattern

The live-view stream is **direct browser → `http://seestar-alp:7556`**, NOT proxied through `:8503`. `_resolve_stream_host` (`imaging.py:47-65`) picks the host from a 3-tier priority:

1. `st.context.headers["host"]` (use whatever host the browser hit Streamlit on)
2. `SEESTAR_PUBLIC_HOST` env (operator-set override)
3. `alpaca._alp_host` (fallback to the internal Docker DNS name)

Stream is injected via `st.html("<img src='http://{host}:7556/...'>")`. The browser must be able to reach `:7556` on the chosen host directly.

### 4b. Stacked frame pattern

Browser-polled JS to `http://{window.location.hostname}:{BACKEND_PORT}/api/imager/stacked.jpg?ts=...` every 15s. `BACKEND_PORT` is read at module-top from `backend.config.settings.port` (fallback 8503) — yes, the UI cross-imports backend config to derive this. **Browser must reach `:8503` directly** — there is no Streamlit proxy.

### 4c. `st.session_state` keys (registry)

~30 stable keys, grouped by origin:

- **Init in `app.py:35-56`**: `config`, `alpaca`, `stellarium`, `connected`
- **Imaging**: `exposing`, `exposure_start`, `exposure_duration`, `image_ready`, `last_image`, `enhanced_image`, `enhance_params`, `enhance_params_key`, `gain_slider`, `filter_select`, `img_exposure`, `active_session_id`, `loop_frames`
- **Sequence**: `sequence_targets`, `sequence_running`, `sequence_current_idx`, `sequence_current_frame`, `seq_session_id`, `seq_step`, `seq_stell_obj`, `show_load_dialog`, `seq_manual_*`
- **Sessions / goto**: `selected_session_id`, `slewing_target`, `reopen_ra`, `reopen_dec`
- **Autofocus / stacking / platesolve**: `autofocus_config`, `stacking_config`, `latest_solve_result`

Reuse the existing key before inventing a new one.

### 4d. `auto_connect` on startup

`app.py:63-72` calls `alpaca.connect_all()` for **5 devices** (telescope, camera, focuser, filterwheel, switch) if `config.auto_connect` is true (default `true` in `config.toml:10`). The `seestar_alp` bridge availability is probed separately via `alpaca.is_alp_available()` — **any view that uses bridge features (goto, mosaic, park) must call this gate first** and degrade gracefully if it returns false.

### 4e. Stellarium

`clients/stellarium_client.py` is constructed in `app.py:49-53` from env `STELLARIUM_HOST` / `STELLARIUM_PORT` (default `localhost:8091`). Pulled off `st.session_state["stellarium"]` in: `views/goto.py`, `views/sequence.py`, `views/settings.py`.

### 4f. View utils

`views/slew_helpers.py` is the only view-util module — exposes `ensure_unparked`, `format_slew_error`, `poll_state_transition`. Used by `views/goto.py`. It's the closest thing to a UI service layer; if you find yourself reaching for similar helpers, add them here rather than inventing a new helper module.

### 4g. Frontend business logic (counter to "UI only")

Two utils modules hold real image-processing logic that views call inline:

- `utils/image_enhancement.py` — 15KB / 530+ lines. Percentile stretch, STF, GHS, MTF, hot pixel removal, noise reduction, star detection via `sep`, star-mask overlay.
- `utils/image_processing.py` — `alpaca_imagearray_to_image`, `save_image`.

**There IS frontend business logic in this project**, contrary to any AI Layer claim that the UI is "presentation only". When refactoring image flows, weigh whether to lift logic to backend services or accept the UI-side compute.

### 4h. Theme

Streamlit theme is injected via **`portal/Dockerfile` CLI flags** (`--theme.base=dark --theme.primaryColor=#00ff88`). There is **no `.streamlit/config.toml`** — don't add one and expect it to take effect. Custom CSS is in `views/theme.py:inject_cosmic_css()` (~458 lines), injected via `st.markdown(unsafe_allow_html=True)`.

### 5. Static catalogs

!`ls portal/catalog/`

`catalog/messier.py` and `catalog/ngc_ic.py` — pure data, no logic.

### 6. Test patterns

!`ls portal/tests/ | grep -E "view|dashboard" | head -10`

**Zero tests use `AppTest`** — ignore any AI Layer claim that they do. The real pattern is the **module-stub pattern**:

1. Stub `streamlit` and heavy deps **before** importing the view under test (so the import doesn't trigger Streamlit's runtime). Canonical example: `test_dashboard.py:9-23`. Use `sys.modules.setdefault("streamlit", MagicMock())` for `streamlit`, plus the same trick for: `numpy`, `PIL`, `cv2`, `sep`, `photutils`, `astroalign`, `lacosmic`.
2. Then `monkeypatch.setattr("views.X.st", st_mock)` (or `patch.object(st, ...)`) inside each test to control the streamlit surface the view sees.

A different second pattern exists in `test_imaging_view.py` — it imports `streamlit` directly and uses `patch.object(st, ...)`. Both patterns work; the stub-pattern is dominant. Match the surrounding tests in whatever file you're touching.

Read `test_dashboard.py` and `test_gallery_view.py` to see the dominant pattern in action.

## Output Report

In under 200 words:

- Page list with one-line "what it does"
- Which views talk to which backend router (via `clients/`)
- Where session state lives (`st.session_state` keys to know about)
- Theme entry point + any custom CSS
- MJPEG embedding pattern — how does the browser get the stream? (Direct to Jetson :7556 vs proxied)

Don't start coding until this is in your context.
