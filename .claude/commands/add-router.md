---
description: Scaffold a new FastAPI router + service pair following the lazy-singleton pattern
argument-hint: <router-name>
---

# Add Router

## Objective

Create a new FastAPI router at `portal/backend/routers/<name>.py` and (optionally) a paired service at `portal/backend/services/<name>_service.py` following the established **lazy-singleton + BackgroundTasks + inline pydantic** pattern that newer routers (`stacking`, `imager`, `gallery_onboard`, `postprocessing`, `autofocus`) share.

## Pattern

### routers/<name>.py

```python
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/<name>", tags=["<name>"])

# ─── Inline pydantic models ──────────────────────────────────────────
class <Name>Config(BaseModel):
    foo: str = Field(..., description="...")

class <Name>StatusResponse(BaseModel):
    running: bool
    progress: float | None = None

# ─── Lazy singleton ──────────────────────────────────────────────────
_<name>_service: "<Name>Service | None" = None

def _get_<name>_service() -> "<Name>Service":
    """Lazy init — keeps test-time module import cheap (no scope I/O)."""
    global _<name>_service
    if _<name>_service is None:
        from ..services.<name>_service import <Name>Service
        _<name>_service = <Name>Service()
    return _<name>_service

# ─── Endpoints ───────────────────────────────────────────────────────
@router.get("/status", response_model=<Name>StatusResponse)
async def get_status() -> <Name>StatusResponse:
    svc = _get_<name>_service()
    return <Name>StatusResponse(running=svc.is_running(), progress=svc.progress())

@router.post("/start")
async def start(cfg: <Name>Config, background_tasks: BackgroundTasks) -> dict:
    svc = _get_<name>_service()
    if svc.is_running():
        raise HTTPException(status_code=409, detail="<Name> already running")
    background_tasks.add_task(svc.run, cfg)
    logger.info(f"<name>.start_queued cfg={cfg}")
    return {"status": "queued"}

@router.post("/abort")
async def abort() -> dict:
    svc = _get_<name>_service()
    if not svc.is_running():
        return {"status": "not_running"}
    try:
        svc.abort()
        logger.info("<name>.abort_signalled")
        return {"status": "aborting"}
    except Exception:
        logger.error("<name>.abort_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="abort failed")
```

### services/<name>_service.py

```python
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class <Name>Config:
    foo: str

class <Name>Service:
    def __init__(self) -> None:
        self._running = False
        self._progress: float | None = None
        self._abort_flag = False

    def is_running(self) -> bool:
        return self._running

    def progress(self) -> float | None:
        return self._progress

    def abort(self) -> None:
        self._abort_flag = True

    async def run(self, cfg: <Name>Config) -> None:
        if self._running:
            return
        self._running = True
        self._abort_flag = False
        self._progress = 0.0
        try:
            # do the work, updating self._progress and checking self._abort_flag
            ...
        except Exception:
            logger.error("<name>_service.run_failed", exc_info=True)
            raise
        finally:
            self._running = False
            self._progress = None
```

### Register in main.py

```python
from .routers import <name>
app.include_router(<name>.router)  # router already declares its own prefix
```

### Test file: tests/test_<name>_router.py

```python
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Stub heavy deps BEFORE importing the app/router
sys.modules.setdefault("streamlit", MagicMock())

from backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_status_returns_default(client):
    r = client.get("/api/<name>/status")
    assert r.status_code == 200
    assert r.json()["running"] is False
```

## Process

1. Confirm `$ARGUMENTS` is kebab-case (router name)
2. Create `portal/backend/routers/<name>.py` from the template
3. Create `portal/backend/services/<name>_service.py` from the template (if state is needed; otherwise skip)
4. Edit `portal/backend/main.py` to `include_router(<name>.router)`
5. Create `portal/tests/test_<name>_router.py` from the test template
6. Run `/validate` (`ruff check portal/` + focused pytest on the new file)
7. Suggest `/commit` with scope `(<name>)`
