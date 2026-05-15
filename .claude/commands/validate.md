---
description: Run seestar-scope's full validation suite with per-level reporting
---

# Validate: Comprehensive seestar-scope Validation

## Objective

Run all three validation levels and report pass/fail with actionable diagnostics. Mirrors what CI runs. All three must pass before claiming a code change is "done" or opening a PR.

---

## Level 1: Lint

```bash
ruff check portal/
```

**What to look for:**
- Unused imports / variables
- Import order issues (E402 — only allowed in `portal/backend/clients.py` per `pyproject.toml`)
- Line length > 100 chars
- Style violations (the ruleset is intentionally light — fix anything that fires)

Auto-fix safe issues:
```bash
ruff check portal/ --fix
```

---

## Level 2: Tests

```bash
PYTHONPATH=. pytest portal/tests/ -m "not hardware" -v \
  --deselect portal/tests/test_seestar_imager.py::test_stacked_frame_to_jpeg_bayer \
  --deselect portal/tests/test_seestar_imager.py::test_stacked_frame_to_jpeg_rgb16
```

- `PYTHONPATH=.` is a **local-only** requirement (CI sets it at the workflow env level so it doesn't need the prefix).
- `-m "not hardware"` skips tests that need a live S50. **Currently zero tests carry the `hardware` marker**, so the filter is a no-op today — it's a convention for any new S50-dependent test going forward.
- The two `--deselect` flags are **mandatory** — these tests pass on the Jetson container (real OpenCV) but fail in CI on `opencv-python-headless` where `cv2.imencode` returns an empty tuple. Documented in PR #43 and PR #45. **Do not "fix" these tests.**

**What to look for:**
- Failing assertions (fix the code, not the assertion)
- Flaky tests with network/timing dependencies (add proper mocking)
- Missing coverage for new code paths

Run a single file when iterating:
```bash
PYTHONPATH=. pytest portal/tests/test_<name>.py -v
```

Run a single test:
```bash
PYTHONPATH=. pytest portal/tests/test_<name>.py::test_<func> -v
```

---

## Level 3: Docker Build

```bash
SEESTAR_IP=192.168.4.1 SEESTAR_PORT=32323 TZ=America/New_York \
BACKEND_URL=http://seestar-portal-backend:8503 \
docker compose build
```

Slow (~3-5 min) but catches Dockerfile breakage that lint + tests miss (missing deps, wrong base image, ARG/ENV issues). Run before opening a PR; skip during tight iteration loops.

CI runs this with the same stub env vars (`.github/workflows/ci.yml`).

---

## Level 4 (optional): Post-deploy smoke

Run **after `/deploy`** against the Jetson stack. These verify the containers are actually live and serving the expected endpoints.

```bash
curl -sf http://192.168.0.234:8503/health
curl -sf http://192.168.0.234:8503/api/gallery/onboard/health   # proves :4701 guest channel works
curl -sf http://192.168.0.234:8502/_stcore/health
curl -sf http://192.168.0.234:5555/management/apiversions
```

Optional WebSocket smoke (proves the 4 broadcaster tasks start):

```bash
websocat -t 5 ws://192.168.0.234:8503/api/status/ws
```

**Conditional** — only if `--profile tunnel` is active (systemd start, or `up -d --profile tunnel`):

```bash
curl -sf https://s50.jmm2020ai.com/_stcore/health
```

A failure here usually means: stale image (forgot `docker compose build`), bad env (`/sync-env` to diagnose), or a crash-looping container (`docker ps` + `docker logs`).

---

## Output Report

After running all levels, provide this report:

```
## Validation Report

| Level | Command | Result | Details |
|-------|---------|--------|---------|
| 1 | ruff check portal/ | PASS / FAIL | N violations |
| 2 | pytest portal/tests/ | PASS / FAIL | N passed, N failed, N skipped, N deselected |
| 3 | docker compose build | PASS / FAIL / SKIPPED | — |

### Failures (if any)

#### Lint
{file:line — violation, with one-line fix suggestion}

#### Test Failures
{test name — assertion / error, with hypothesis on root cause}

#### Docker Build
{Dockerfile line + error, with what's likely missing}

### Recommended Fixes
{Prioritized list in order: lint first (always cheap), then tests, then docker}
```

**Tip:** Fix in this order — lint first (cheap, often clears type-y issues), then tests (where the real bugs live), then docker (slowest feedback loop).

**Done means all three green.** No exceptions.
