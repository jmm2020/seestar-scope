---
description: Create a comprehensive implementation plan for a seestar-scope feature
argument-hint: <feature-name-or-description>
---

# Plan Feature: seestar-scope Implementation Planning

## Objective

Produce a detailed, actionable implementation plan for: **$ARGUMENTS**

The plan will be saved to `.claude/plans/{kebab-case-name}.md` and is designed to be consumed by the `/execute` command.

---

## Phase 1: Feature Understanding

Restate the feature request in your own words. Identify:

1. **Problem being solved** — What user pain point or capability gap does this address?
2. **Success criteria** — What does "done" look like? How will we verify it works?
3. **Scope boundaries** — What is explicitly in scope vs. out of scope?
4. **Surface impact** — Which surfaces are affected?
   - `portal/backend/` (FastAPI — routers / services / clients / models)
   - `portal/` (Streamlit views / clients / catalog)
   - `vendor/seestar_alp/` (don't touch — fork upstream or override via `alp-config/`)
   - `alp-config/config.toml` (seestar_alp config, bind-mounted on Jetson)
   - `deploy/jetson/` (setup script, systemd unit)
   - `.github/workflows/ci.yml` (CI)
5. **Hardware dependence** — Does this need a live S50 (`-m hardware` tests) or can it run in CI?

---

## Phase 2: Codebase Intelligence

Spawn subagents in parallel for targeted research. Pick the subset that applies:

**Subagent A — Affected files deep-dive:**
Read every relevant file in the affected surface. Map current data flow. Identify every file that will need to change.

**Subagent B — Wire format / contracts:**
- For backend changes: read pydantic models **inline in each router file** — that's where most request/response schemas live. `portal/backend/models/` only holds shared cross-router schemas (`gallery.py`, `sessions.py`). Match response shapes in similar routers.
- For UI changes: read the per-view `BACKEND_URL = os.environ.get(...)` + inline `requests.get(...)` calls — request/response types must match the backend. Some views also call `AlpacaClient` directly (`dashboard.py`, `focus.py`, `slew_helpers.py`, `live_status.py`); confirm which path applies before designing the contract.

**Subagent C — Test patterns:**
!`find portal/tests/ -name "test_*.py" | head -20`

Read 2-3 representative test files near the area of change. Note the `pytest-asyncio` style (auto mode per `pyproject.toml`), fixtures in `conftest.py`, and how router tests mock the ALPACA/seestar_alp clients.

**Subagent D — Related prior work:**
!`git log --oneline -30`

Read recent commits touching affected files.

Synthesize findings: current state, gaps, constraints.

---

## Phase 3: External Research (if needed)

If the feature involves:
- Seestar firmware behavior — check the `smart-underworld/seestar_alp` upstream for issues/PRs
- A new astronomy library — check PyPI, read the README, note version pinning
- ALPACA spec questions — reference the Alpaca / ASCOM standard docs

---

## Phase 4: Strategic Thinking

Before writing tasks, reason through:

**Architecture:**
- Does business logic belong in a router or a service? (Rule: routers are thin; services own state machines)
- Does this need a new background task / queue? Where does that lifecycle hook in?
- Does this need a new pydantic model, or extend an existing one?
- Will views call a new client method or reuse existing ones?

**Boundaries to respect:**
- Decide which path the view takes — **direct `AlpacaClient` from `st.session_state.alpaca`** (telescope state — RA/Dec, focus, slew, live_status) vs **`requests` to FastAPI** (gallery / sessions / stacking / conditions / postprocessing). Both are real, established paths.
- Don't edit `vendor/seestar_alp/` source — fork upstream if needed
- Workstation is source-only — don't add scripts that assume the stack is running locally

**Deploy / runtime:**
- Will this need a new env var? Update `.env.example`, `docker-compose.yml`, `deploy/jetson/setup.sh`, and CI stubs.
- Does it change container behavior? Note the rebuild step in the plan.
- Config-only change (alp-config/config.toml)? Note the bind-mount + `docker restart seestar-alp` flow.

**Firmware 7.34 reality:**
- Will this work without the PEM-gated :4700? If it needs :4700, it's broken until pairing is solved — flag this.
- Can it use the guest channel :4701 or native ALPACA :32323 instead?

**Rollback:**
- Blast radius if this goes wrong?
- Reversible without data loss?

---

## Phase 5: Plan Generation

Generate the implementation plan at `.claude/plans/{kebab-case-feature-name}.md`:

```markdown
# Plan: {Feature Name}

## Overview
{1-2 sentence summary: what this implements and why.}

## Success Criteria
- [ ] {Verifiable criterion 1}
- [ ] {Verifiable criterion 2}
- [ ] `ruff check portal/` passes
- [ ] `pytest portal/tests/ -m "not hardware"` passes (with the two known deselects)
- [ ] `docker compose build` succeeds

## Affected Surfaces
- `portal/backend/<path>` — {what changes}
- `portal/<path>` — {what changes}

## Architecture Notes
{Key decisions, tradeoffs, contract changes. Why this design, not alternatives.}

## Implementation Tasks

### Task 1: {descriptive name}
**File:** `portal/backend/routers/{file}.py`
**Type:** Create | Modify | Delete
**Description:** {What this task does and why.}
**Depends on:** {Task N, or "none"}

### Task 2: ...

## Validation Steps
1. `ruff check portal/` — must exit 0
2. `PYTHONPATH=. pytest portal/tests/ -m "not hardware" -v` (with the two deselects from validate.md) — all pass
3. `docker compose build` — succeeds (run before opening a PR)
4. Manual test: {specific curl or UI steps to verify the feature against the Jetson stack}

## Rollback Notes
{How to safely revert. Include any DB / config file revert steps.}
```

### Task Ordering Rules
- Order by dependency. Blocked tasks come after their dependencies.
- pydantic models / contracts before the routers / clients that use them.
- Backend before frontend.
- Tests after implementation (don't gold-plate tests for code that may still pivot).
- Config / env var changes (`docker-compose.yml`, `.env.example`, CI) before code that reads them.

### Prohibited Patterns (flag in plan if at risk)
- Editing `vendor/seestar_alp/` source (fork upstream instead)
- Adding new tests that pass on Jetson but fail on `opencv-python-headless` without deselecting in CI
- Hardcoding scope IP/port (must come from `SEESTAR_IP` / `SEESTAR_PORT` env)
- Long-running blocking work in a router (offload to a service / background task)
- Bare `except Exception as e: raise HTTPException(500, str(e))` with no logging — this is the `routers/telescope.py` antipattern; new code must `logger.error(..., exc_info=True)` at minimum

---

## Output

1. Save the plan to `.claude/plans/{kebab-case-name}.md`
2. Print the plan to the conversation
3. Summarize: number of tasks, surfaces touched, estimated complexity (low/medium/high), open questions
