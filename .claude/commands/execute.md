---
description: Execute a seestar-scope implementation plan file
argument-hint: <path-to-plan.md>
---

# Execute: Implement a seestar-scope Plan

## Objective

Read and execute every task in the plan file: **$ARGUMENTS**

Implement all tasks faithfully, following seestar-scope conventions, and report results.

---

## Step 1: Read the Entire Plan

Read the plan file at `$ARGUMENTS` from start to finish before writing a single line of code. Understand:

- All tasks and their dependencies
- Affected surfaces and files
- Architecture notes and prohibited patterns
- The validation steps at the end

Do NOT start implementing until you have the full picture.

---

## Step 2: Verify Current State

Check the working tree is clean before starting:

!`git status`

If there are uncommitted changes unrelated to this plan, flag them before proceeding.

Confirm the branch:

!`git branch --show-current`

If on `main`, consider creating a feature branch:
```bash
git checkout -b feat/<short-name>
```

---

## Step 3: Execute Tasks in Dependency Order

Work through each task in the plan sequentially (respect `Depends on:` ordering).

### For each task:

1. **Read** the target file(s) before modifying — never edit blindly.
2. **Implement** the change using Edit (preferred) or Write (only for new files).
3. **Verify** after each significant change:
   ```bash
   ruff check portal/<changed-area>
   ```
   Fix lint errors immediately — don't let them accumulate.

### seestar-scope conventions to follow

**Backend routers (thin) — THREE coexisting DI patterns:**

Newer routers (preferred for new code) use a **module-level lazy singleton**:

```python
# portal/backend/routers/stacking.py:32-37 — canonical lazy-singleton pattern
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stacking", tags=["stacking"])

_stacking_service: "StackingService | None" = None

def _get_stacking_service() -> "StackingService":
    """Lazy init — keeps test-time module import cheap (no scope I/O)."""
    global _stacking_service
    if _stacking_service is None:
        from ..services.stacking_service import StackingService
        _stacking_service = StackingService()
    return _stacking_service

@router.get("/status")
async def get_status():
    return _get_stacking_service().status()
```

Some routers use **`Depends(get_<thing>)` with an explicit getter** (e.g. `gallery.py` style with `Depends(get_db)`):

```python
@router.get("/items")
async def list_items(db: GalleryDatabase = Depends(get_db)):
    return db.list_items()
```

Older routers (`telescope.py`, `status_ws.py`) use **`request.app.state.<dep>`**:

```python
@router.get("/connected")
async def is_connected(request: Request) -> bool:
    return request.app.state.alpaca.is_connected("telescope")
```

For new code, pick the lazy-singleton pattern unless one of the others is already established in the file you're editing. Routers should not contain state machines, long loops, or scope I/O — push that to services.

**Backend services (own the state):**
```python
# portal/backend/services/<name>_service.py
class <Name>Service:
    def __init__(self, client: SomeClient): ...
    async def do_the_thing(self) -> Result: ...
```

**Clients (HTTP / ALPACA boundary):**

`backend/clients.py` is a **30-line factory** — the actual dual-channel logic lives in `portal/clients/alpaca_client.py` (shared by UI **and** backend; copied into the backend image at build time). On the `AlpacaClient`, `base_url` points at the native scope :32323 and `alp_base_url` points at the `seestar_alp` bridge :5555 — both coexist, and call sites pick per-method (e.g. telescope state goes via native, imaging actions go via the bridge).

```python
# portal/clients/alpaca_client.py
class AlpacaClient:
    def __init__(self, host: str, port: int = 32323, alp_host: str | None = None, alp_port: int = 5555):
        self.base_url = f"http://{host}:{port}"
        self.alp_base_url = f"http://{alp_host or host}:{alp_port}" if alp_host else None
    # state methods → self.base_url; actions / MJPEG control → self.alp_base_url
```

Touching `portal/clients/` requires rebuilding the backend image (it's COPIED, not bind-mounted — Dockerfile lines 33-36).

**Pydantic models:**

Most request/response models are defined **inline in the router file**. Only `portal/backend/models/gallery.py` and `portal/backend/models/sessions.py` exist, and they hold schemas shared across multiple routers. Default to inline; move into `models/` only if a schema is genuinely shared.

```python
# portal/backend/routers/<name>.py — inline pydantic is the norm
from pydantic import BaseModel, Field

class StartRequest(BaseModel):
    exposure_s: float = Field(..., gt=0)

class StatusResponse(BaseModel):
    running: bool
    progress: float | None = None
```

**Streamlit views — pragmatic, NOT logic-free:**

The codebase has a **dual UI architecture**. Both are real and load-bearing:

1. **Direct-`requests` to FastAPI** (dominant pattern — gallery / sessions / stacking / conditions / postprocessing). Each view defines `BACKEND_URL` at module top and calls FastAPI inline:
   ```python
   # portal/views/<name>.py — the real, dominant pattern
   import os
   import requests
   import streamlit as st

   BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")

   def render():
       r = requests.get(f"{BACKEND_URL}/api/<group>/something", timeout=5)
       r.raise_for_status()
       st.write(r.json())
   ```

2. **Direct `AlpacaClient` from `st.session_state.alpaca`** — bypasses FastAPI entirely. Used by `dashboard.py`, `focus.py`, `slew_helpers.py`, `live_status.py` for telescope state (RA/Dec, altitude, connected, focus position).
   ```python
   # portal/views/dashboard.py — bypass FastAPI for telescope state
   import streamlit as st

   def render():
       alpaca = st.session_state.alpaca
       status = alpaca.get_telescope_status()
       st.metric("RA", status["ra"])
   ```

Views CAN have business logic — `utils/image_enhancement.py` (15KB of stretch/STF/GHS code) is called inline from `views/imaging.py:_render_enhancement_panel`. Keep it pragmatic.

**UI HTTP client (per-view env-var pattern):**
```python
# At module top of every backend-calling view
import os
BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")

# In render functions
import requests
r = requests.get(f"{BACKEND_URL}/api/gallery/list", timeout=5)
r.raise_for_status()
```

There is **no** `config_loader.get_backend_url()` helper — each view reads the env var directly.

**Logging:**
```python
import logging

logger = logging.getLogger(__name__)  # ALWAYS `logger`, never `log`

# f-strings are the dominant style
logger.info(f"Session {session_id} started")

# %s printf-style is also accepted
logger.info("loaded %s frames", len(frames))
```

**Zero usage of `extra={...}` exists in `portal/`.** Don't introduce it — match the convention.

**Error handling — never swallow silently:**
```python
try:
    result = await risky_op()
except HTTPException:
    raise  # let FastAPI handle it
except Exception:
    logger.error("operation failed", exc_info=True)  # not log.exception
    raise HTTPException(status_code=500, detail="Operation failed")
```

**ANTIPATTERN to avoid — DO NOT IMITATE:** `routers/telescope.py` has **31 instances** of:
```python
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```
…with **no logging at all**. This silently leaks internal error messages to clients and gives operators nothing to debug. New routers must at least `logger.error("...", exc_info=True)` before re-raising, and should not put `str(e)` in the response body.

**ALPACA vs seestar_alp:**
- Telescope state (RA/Dec/altitude/connected) → native ALPACA :32323 (works, no auth)
- Imaging / live-stack actions → seestar_alp :5555 (degraded but alive)
- MJPEG stream :7556 → consumed **direct browser → `seestar-alp:7556`**, not proxied through FastAPI
- Goto / Unpark / mosaics / scheduling / `start_up_sequence` → :4700 (PEM-gated, **broken** — don't promise these will work)
- Onboard gallery → guest JSON-RPC :4701 + HTTP :80 (works)

Note: Streamlit views also call `AlpacaClient` at :32323 directly for telescope state (`dashboard.py`, `focus.py`, `slew_helpers.py`, `live_status.py`). FastAPI is on the gallery / sessions / stacking / conditions / postprocessing path.

**Hardware tests:**
- The `@pytest.mark.hardware` marker is registered in `portal/tests/conftest.py:3` and CI filters with `-m 'not hardware'`.
- **Zero tests currently use the marker** — it's a convention going forward, not an active filter. New S50-dependent tests should carry it.
- Use the new `/test-hardware` command to run S50-dependent tests against `.132`.

---

## Step 4: Run Incremental Validation

After completing related tasks (e.g., all backend changes), run:

```bash
ruff check portal/
```

Then focused tests for the area you changed:

```bash
PYTHONPATH=. pytest portal/tests/test_<area>.py -v
```

Fix any failures before moving to the next group.

---

## Step 5: Run Full Validation

After all tasks are complete, run the full suite (mirrors `/validate`):

```bash
ruff check portal/
```

```bash
PYTHONPATH=. pytest portal/tests/ -m "not hardware" -v \
  --deselect portal/tests/test_seestar_imager.py::test_stacked_frame_to_jpeg_bayer \
  --deselect portal/tests/test_seestar_imager.py::test_stacked_frame_to_jpeg_rgb16
```

```bash
docker compose build  # only if you touched Dockerfiles, requirements, or env handling
```

All must pass before reporting completion.

---

## Step 6: Output Report

Provide a structured completion report:

```
## Execution Report: {Plan Name}

### Tasks Completed
- [x] Task 1: {description} — {files changed}
- [x] Task 2: {description} — {files changed}

### Files Created
- `portal/backend/<path>` — {purpose}

### Files Modified
- `portal/<path>` — {what changed}

### Validation Results
- ruff check: PASS / FAIL ({N} violations)
- pytest (not hardware): PASS / FAIL ({N} passed, {N} failed, {N} deselected)
- docker compose build: PASS / FAIL / SKIPPED

### Manual Verification
{curl commands or UI steps to verify against the Jetson stack at 192.168.0.234}

### Deploy notes
{Anything special for /deploy — env var changes, config file updates, container rebuild required}

### Notes
{Deviations from the plan, unexpected findings, follow-up work}
```

If anything is still red, **do not claim "done"**. Fix or document why it's blocked.
