---
description: Prime agent with full seestar-scope project context
---

# Prime: Load seestar-scope Project Context

## Objective

Build a working mental model of seestar-scope before touching code. Orients you on hosts, ports, request flow, deploy model, and current state.

## Process

### 1. Project structure

!`ls -la`

!`ls portal/ portal/backend/ portal/views/ portal/backend/routers/ portal/backend/services/`

### 2. Read the canonical references

Read `AGENTS.md` in full — it's the authoritative project topology (hosts, ports, request flow, firmware 7.34 deep-dive, "what I should NEVER assume").

Read `CLAUDE.md` in full — the Claude Code overlay (test-then-done, deploy flow, architecture boundaries, conventions).

Skim `docs/architecture.md` — target architecture diagrams.

### 3. Current state

!`git status`

!`git log -10 --oneline`

!`git branch --show-current`

Check open PRs (if `gh` available):

!`gh pr list --state open 2>/dev/null || echo "(no gh or no remote)"`

### 4. Confirm hosts (CRITICAL — this trips agents up)

- **Workstation `192.168.0.36`** — source only. **Nothing runs here.**
- **Jetson `192.168.0.234`** — runs `seestar-portal-ui` :8502, `seestar-portal-backend` :8503, `seestar-alp` :5555/:7556.
- **Scope `192.168.0.132`** — Seestar S50 firmware 7.34. ALPACA on :32323 (works, no auth). JSON-RPC :4700 (PEM-gated, broken). JSON-RPC :4701 (guest channel, works). HTTP :80 (album content).

## Output Report

Give a concise summary (under 250 words) covering:

### Stack
- Python 3.11, FastAPI (`portal/backend/`), Streamlit (`portal/`), pytest, ruff
- Vendored `seestar_alp` ALPACA bridge (`vendor/seestar_alp/`, git submodule)
- Docker Compose (4 services) deployed to Jetson Orin

### Current State
- Branch, recent changes, uncommitted work
- Any in-flight PR
- Note anything in `tmp/` or `HANDOFF.md` from a prior session

### Open Issues (from AGENTS.md)
- Firmware 7.34 :4700 PEM auth — Goto/mosaics broken; `verify_injection=false` keeps the bridge alive
- Two CI-only test failures (cv2.imencode on opencv-python-headless) — deselected, don't touch
- **`setup.sh:96` writes `SEESTAR_PORT=11111` — production bug, fresh Jetson installs will fail until fixed manually.**
- `hardware` pytest marker is registered in `pyproject.toml` but **no tests currently use it**. The CI `-m "not hardware"` filter is a no-op today — it's a convention for future S50-dependent tests, not an active filter.

**Keep it scannable — bullets over prose.** Don't start coding until this report is in your context.
