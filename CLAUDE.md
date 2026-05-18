# CLAUDE.md — seestar-scope

> **Project topology, hosts, ports, request flow, and operational facts live in `AGENTS.md`** (universal, agent-neutral). Read it first. This file is the Claude Code overlay.

@AGENTS.md

---

## What this repo is

The Seestar S50 control + imaging portal. Two-service stack (FastAPI backend + Streamlit UI) plus a vendored `seestar_alp` ALPACA bridge, deployed on a Jetson Orin. Source lives on the **workstation**; **nothing runs there**.

```
portal/                  ← Streamlit UI (port 8502)
portal/backend/          ← FastAPI REST + WebSocket (port 8503)
vendor/seestar_alp/      ← Upstream ALPACA bridge (submodule), runs on Jetson at :5555/:7556
deploy/jetson/           ← setup.sh + systemd unit for first-boot install
alp-config/config.toml   ← Bind-mounted into the seestar-alp container
docs/                    ← architecture.md, migration_runbook.md
.github/workflows/ci.yml ← Lint + docker build + pytest on push/PR to main
```

---

## NEVER ASSUME (read AGENTS.md "What I should NEVER assume again")

1. The portal **does not run on the workstation**. Backend at `:8503` means **Jetson `192.168.0.234`**, not localhost.
2. Containers on this machine are **UCIS**, not seestar-scope. `docker ps` here is irrelevant to this repo.
3. `vendor/seestar_alp/` is a **submodule checkout**, not necessarily what's running. The Jetson container has its own copy that may be newer. Diff inside the container before patching:
   ```bash
   ssh jmm2020@192.168.0.234 'docker exec seestar-alp sed -n "1140,1150p" /home/seestar/seestar_alp/device/seestar_device.py'
   ```
4. The S50 has **two ALPACA endpoints**: native firmware on `:32323` (works, no auth) and the seestar_alp bridge on `:5555` (works but degraded — JSON-RPC `:4700` is PEM-gated on firmware 7.34). Don't conflate them.
5. DeviceNumber is **0**, not 1.
6. **CORS is `allow_origins=["*"]`** with a `# TODO` at `portal/backend/main.py:90` to lock it down. The Cloudflare tunnel exposes :8503 to the internet — so this is currently a wide-open API surface. **Do NOT add new untrusted endpoints behind this CORS** without restricting origins first.
7. The **Streamlit auth gate** (PR #66) only protects the Streamlit UI at `:8502`. The FastAPI backend at `:8503` has **no equivalent guard** — CORS is still `allow_origins=["*"]` and all API endpoints are publicly reachable. Do not assume auth is "done" for the whole stack.

---

## TEST-THEN-DONE PROTOCOL (MANDATORY)

Before saying "done" on any code change:

1. **Lint**: `ruff check portal/` (matches CI)
2. **Run the tests**: `PYTHONPATH=. pytest portal/tests/ -m "not hardware" -v` (or the focused subset for the file you touched). `PYTHONPATH=.` is required — `validate.md` and `execute.md` both set it, and tests fail to import without it.
3. **Show passing output** in the response
4. **If tests fail**: fix the code and re-run. "Done without green tests" = not done.

**Known-failing tests** (do NOT try to fix unless explicitly asked):
- `portal/tests/test_seestar_imager.py::test_stacked_frame_to_jpeg_bayer`
- `portal/tests/test_seestar_imager.py::test_stacked_frame_to_jpeg_rgb16`

These pass on the Jetson container but fail in `ubuntu-latest` CI because `cv2.imencode` returns an empty tuple with the headless OpenCV wheel. Documented in PR #43, PR #45. CI deselects them; you should too.

**`hardware` marker — convention only, no active filter today.** The marker is *registered* in `conftest.py` and CI passes `-m "not hardware"`, but **zero tests in the suite currently carry `@pytest.mark.hardware`**. The CI filter is a no-op right now. Treat the marker as a convention for **future S50-dependent tests** — add it when you write a test that requires a live scope. Don't assume `-m "not hardware"` is actively filtering anything today.

---

## DEPLOY FLOW

The repo is **edit-on-workstation, run-on-Jetson**:

1. Edit on workstation (`/media/jmm2020/AIDrive1/code/seestar-scope/`)
2. Commit + push to `main`
3. On Jetson: `cd ~/seestar-scope && git pull && docker compose build && docker compose up -d`
4. For config-only changes to `alp-config/config.toml`: edit on Jetson host directly, then `docker restart seestar-alp` (the file is bind-mounted)

**Two boot paths — they produce different stacks.** `seestar-stack.service` (systemd, runs at boot) uses `docker compose --profile tunnel up` (foreground) and brings up **4 containers** including `seestar-cloudflared`. A manual SSH `docker compose up -d` (no profile flag) brings up **3 containers** — the tunnel sidecar is omitted. If you SSH-deploy and expect the public hostname to work, you also need `--profile tunnel` or a `docker start seestar-cloudflared`.

**`portal/clients/` is COPIED into the `seestar-portal-backend` image** (`portal/backend/Dockerfile` lines ~33-36). Touching `portal/clients/*.py` requires rebuilding **both** containers (`docker compose build` rebuilds both UI and backend), not just the UI. Skipping the backend rebuild produces stale-snapshot bugs — tracked in PRs #38/#39/#41.

First-boot install on a fresh Jetson: `bash deploy/jetson/setup.sh` (idempotent). See `deploy/jetson/README.md` and `docs/migration_runbook.md`.

---

## APPROACH VALIDATION (before coding)

1. **Read the full task** — restate the goal: "You want me to X, which will achieve Y."
2. **Check prior art** — grep for similar patterns in `portal/backend/routers/`, `portal/views/`, or existing tests. Match style.
3. **Scope lock** — if the task says "fix X", don't also refactor Y. Stay in scope or ask.
4. **Challenger mode** — before finalizing, ask: is there a simpler way? Could this be 20 lines instead of 200?

---

## FAIL FAST — CLARIFY, DON'T GUESS

If a task is ambiguous, **stop and ask**. Examples:

- "Task says 'fix the gallery' — which page? `views/gallery.py` (live view) or `views/imaging_stacked.py` (onboard archive)?"
- "Should the new endpoint go in `routers/imager.py` or `routers/stacking.py`?"
- "Are we targeting workstation dev (`streamlit run`) or Jetson (`docker compose`)?"

Never proceed with ambiguity.

---

## FIRMWARE 7.34 AUTHENTICATION (current open problem)

JSON-RPC `:4700` on the scope is PEM-gated. The portal degrades gracefully when `verify_injection = false` is set in `alp-config/config.toml` — Goto/Unpark/mosaics are broken until we figure out pairing. **What's still degraded**:

| Capability | Status |
|---|---|
| Telescope state (RA/Dec/altitude) via ALPACA :32323 | works |
| MJPEG stream :7556 | works — consumed **direct browser → `http://seestar-alp:7556`**, NOT proxied via the FastAPI backend |
| Onboard gallery (guest JSON-RPC :4701 + HTTP :80) | works |
| `get_device_state` / `get_view_state` via method_sync | degraded |
| `start_up_sequence`, Goto, mosaics | broken — needs PEM |

When debugging the scope panels, the failure mode is **silent**: `:4700` drops messages, `seestar_alp` returns a string-error envelope, the `start_up_thread_fn` crashes. See AGENTS.md §"Root cause of scope panels not working" for the diagnostic chain.

---

## ARCHITECTURE BOUNDARIES

**Dual UI architecture — there are TWO paths from views to the scope. Don't assume one.**

- **`portal/`** (Streamlit) — UI in `views/`. Views use TWO different channels:
  - **Legacy direct-ALPACA path** — `dashboard.py`, `focus.py`, `slew_helpers.py`, `live_status.py` call `AlpacaClient` directly (held in `st.session_state.alpaca`), **bypassing FastAPI** for telescope state, focus, slew, and device-status. Talks to scope native ALPACA `:32323` (and/or `seestar_alp` :5555) without going through `portal/backend/`.
  - **Backend-HTTP path** — gallery, sessions, stacking, conditions, autofocus, platesolve, postprocessing views call FastAPI via `requests.get/.post/.put` with a module-level `BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")` declared at the top of each view file.
  - Business logic in views is NOT prohibited. `utils/image_enhancement.py` (15KB of stretch/STF/GHS/star-detection numpy code) is called inline from `views/imaging.py:_render_enhancement_panel` — a real counter-example to any "thin views" claim.
- **`portal/backend/`** (FastAPI) — REST + WebSocket. Routers in `routers/`, business logic in `services/`. Talks to the S50 via ALPACA REST (`:32323`) or via `seestar_alp` (`http://seestar-alp:5555`).
- **`vendor/seestar_alp/`** — git submodule. Don't edit directly; if a bridge change is needed, fork upstream or override via `alp-config/config.toml`.
- **`portal/clients/`** — long-lived **stateful** socket/session client classes (`AlpacaClient`, `StellariumClient`, `SessionsClient`, `SeestarObserverClient`, `SeestarArchiveClient`, `SeestarImagerClient`) shared between UI and backend. Not "HTTP wrappers to the backend" — those live inline in each view as `requests.*` calls. **Also copied into the `seestar-portal-backend` Docker image** (`portal/backend/Dockerfile` lines ~33-36) — touching `portal/clients/` requires rebuilding both containers, not just the UI. Stale-snapshot bugs from skipping the backend rebuild were tracked in PRs #38/#39/#41.
- **`portal/auth/`** — Supabase auth layer: `AuthProvider` (SDK wrapper), `ProviderConfig` / `PROVIDERS` list, and `session.py` (`st.session_state` binding). `is_authenticated()` is the single source of truth for gate checks. Auth is **Streamlit-only** — FastAPI at `:8503` has no equivalent guard.
- **`portal/billing/`** — Stripe billing layer. `stripe_client.py` wraps the Stripe SDK (`StripeClient`: checkout sessions, customer portal, customer lookup — all return `None` on failure). `products.py` holds price ID constants from env and `is_first_watch_signup()` (queries `stripe.subscriptions` via Supabase). `webhook_handler.py` is a FastAPI `APIRouter` mounted at `/billing/webhook` — it validates Stripe signatures, deduplicates via `stripe_event_log`, and binds `stripe_customer_id` to Supabase users on `checkout.session.completed`. Imported by both FastAPI backend (`main.py`) and Streamlit checkout page.
- **`portal/pages/`** — Full-page views that live outside the main nav tab system: `account.py` is the login/signup/OAuth/account panel, reached when unauthenticated or via the Account nav entry; `checkout.py` is the Subscribe / Manage Billing page (renders Stripe Checkout and Customer Portal redirects).
- **`portal/catalog/`** — static Messier / NGC-IC catalogs. Pure data.

## JOB STATE — NO CONVENTION YET

Long-running backend jobs use **four different patterns**, none canonical:

- `routers/postprocessing.py` — `OrderedDict` capped at `_MAX_JOBS = 100` (FIFO evict on overflow)
- `routers/processing.py` — uncapped `Dict[str, ProcessingResult]` (memory grows unbounded)
- `routers/platesolve.py` — module-import `ASTAPService` with **hardcoded `/data/seestar`** (ignores `settings.data_dir`)
- `routers/stacking.py` — lazy-singleton service + `BackgroundTasks`

Any new long-running job should prefer the **`stacking.py` pattern** (lazy singleton + `BackgroundTasks`) unless there's a specific reason not to. Don't reinvent a fifth pattern.

---

## CONVENTIONS

- **Git commits**: `<type>(<scope>): <subject>`. Examples: `feat(gallery): add onboard archive view`, `fix(stacking): handle empty frame queue`. Never include "claude code" in messages.
  - **Scope = domain area or feature group**, NOT layer name. Real scopes used in `git log -30`: `gallery`, `imaging`, `alpaca`, `imager`, `observer`, `slew`, `seestar-alp`, `portal`, `autofocus`, `docker`, `sessions`, `conditions`. Layer-style scopes like `backend`, `ui`, `deploy`, `ci`, `alp`, `docs`, `ai` do **not** appear in real history — don't invent them.
- **Python**: 3.11, `ruff` for lint (line-length 100, see `pyproject.toml`), `pytest-asyncio` mode=auto.
- **PRs**: target `main`. CI must be green (lint + docker build + pytest). Don't bypass CI.
- **Submodules**: `vendor/seestar_alp` is a submodule — clone with `--recurse-submodules` or run `git submodule update --init --recursive` after pulling.

---

## SLASH COMMANDS

Available via `.claude/commands/` — start any non-trivial session with `/prime`:

**Context loaders** (load state into the conversation):
- `/prime` — full project context (hosts, ports, current state)
- `/prime-backend` — FastAPI backend orientation (`portal/backend/`)
- `/prime-frontend` — Streamlit UI orientation (`portal/`)
- `/prime-deploy` — Jetson + compose + CI + cloudflared orientation

**Workflow** (PIV — plan → implement → validate → commit):
- `/plan-feature <name>` — produces `.claude/plans/{name}.md`
- `/execute <plan-path>` — consumes a plan file, implements every task
- `/validate` — full validation suite (ruff + pytest + docker build)
- `/commit` — atomic commit with conventional tags

**Operational** (project-specific):
- `/deploy` — push to Jetson, rebuild containers, smoke-test
- `/debug-scope` — firmware 7.34 / PEM auth / verify_injection diagnostic chain

**Meta**:
- `/handoff` — write a `HANDOFF.md` session continuation doc
- `/create-command <name>` — generate a new slash command in the project's pattern

## REFERENCE

- `AGENTS.md` — hosts, ports, request flow, firmware 7.34 deep-dive
- `docs/architecture.md` — target architecture diagrams
- `docs/migration_runbook.md` — workstation → Jetson cutover procedure
- `deploy/jetson/README.md` — first-boot install checklist

**Legacy `portal/backend/app/` subpackage still exists** — `app/services/siril_service.py`, `app/routers/processing.py` live there from a partial reorg. Don't assume `portal/backend/services/` and `portal/backend/routers/` are exhaustive; there's a parallel `app/` hierarchy. When searching for a service or router by name, check both trees.
