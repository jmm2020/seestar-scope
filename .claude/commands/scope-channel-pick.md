---
description: Pick the right scope channel for a given operation
argument-hint: <operation description, e.g. "read telescope RA/Dec" or "start stacking">
---

# Scope Channel Picker

## Objective

Help the agent route an operation to the correct scope channel (or escalate if no channel works). The S50 firmware 7.34 exposes 6 distinct endpoints with different auth, reliability, and capability profiles.

## The 6 channels

| Channel | Port | Auth | Status | Use for |
|---|---|---|---|---|
| Native ALPACA | 32323 (`SEESTAR_IP`) | None | **Works** | Telescope state (RA/Dec/altitude/connected), management API, device introspection |
| seestar_alp bridge REST | 5555 (ALP container) | None | **Works** (proxies most of the above + MJPEG control) | Imaging actions, MJPEG control, general ALPACA proxy when going through the bridge |
| seestar_alp bridge MJPEG | 7556 (ALP container) | None | **Works** | Live video stream — consumed **direct browser → container**, not via FastAPI |
| Scope JSON-RPC `:4700` | 4700 | **PEM-signed** verify token | **BROKEN on 7.34** — silent drop without PEM | (None currently — Goto / Unpark / mosaics / start_up_sequence all need this) |
| Scope JSON-RPC `:4701` (guest) | 4701 | None (whitelist) | **Works**, limited methods | `get_albums` for onboard archive |
| Scope HTTP static | 80 | None | **Works** | Onboard album content — JPEG thumbnails, full-res, MP4 timelapses under `/MyWorks/` |
| Scope imager TCP | 4800 | None | **Works** | Raw stacked frames (single-frame JPEG poll, not MJPEG) |

## Decision tree

1. **Reading telescope state** (RA/Dec/altitude/connected/atpark) → **Native ALPACA :32323**. Use `AlpacaClient.get_telescope_status()` or `_get()`.
2. **Imaging actions** (start expose, set gain/filter, MJPEG control) → **seestar_alp :5555**. Use `AlpacaClient.seestar_action()`.
3. **Live MJPEG video** → **seestar_alp :7556**, consumed direct browser → container. Don't proxy through FastAPI.
4. **Onboard archive browse** (gallery, thumbnails, full-res, timelapses):
   - Album list / metadata → **guest JSON-RPC :4701** via `SeestarObserverClient` (`portal/clients/seestar_observer.py`)
   - Image / video bytes → **HTTP :80** via `SeestarArchiveClient` (`portal/clients/seestar_archive.py`)
5. **Live stacked frame** (single-frame JPEG, not MJPEG) → **TCP :4800** via `SeestarImagerClient` (`portal/clients/seestar_imager.py`).
6. **Goto / Unpark / mosaics / scheduling / `start_up_sequence`** → **needs :4700, currently BROKEN on 7.34**. Don't promise. Either degrade gracefully or block with a clear "requires firmware pairing" error.

## How to verify the operation will work

1. From the workstation:
   ```bash
   curl -sf http://192.168.0.132:32323/management/apiversions  # native ALPACA alive
   curl -sf http://192.168.0.132/MyWorks/ | head -5             # HTTP :80 alive
   ```
2. From the Jetson:
   ```bash
   docker exec seestar-portal-backend curl -sf http://seestar-alp:5555/management/apiversions
   ```
3. For :4701: requires a real JSON-RPC client; use the test harness in `portal/tests/test_seestar_observer.py::FakeScopeServer` as a reference.

## Output

For the operation: `$ARGUMENTS`

Recommend:
1. Channel: ____
2. Client class (in `portal/clients/`): ____
3. Likely router (in `portal/backend/routers/` or `portal/views/`): ____
4. Known status: works / degraded / broken (with reason)
5. If broken — what's the graceful degradation? What does the UI show?
