# Seestar Workstation → Jetson Orin Migration Runbook

> Structured cutover procedure for moving the seestar-scope stack from the development workstation to the Jetson Orin Nano.

## Pre-Flight Checklist

Run from the **workstation** before starting cutover:

- [ ] Jetson Orin reachable on LAN: `ping <jetson-ip>`
- [ ] Telescope reachable from Jetson: `ssh jetson curl -sf http://192.168.0.132:32323 || echo "check manually"`
- [ ] Workstation smoke test green:
  ```bash
  bash scripts/smoke_test.sh --host localhost --platform workstation
  ```
- [ ] `tests/baselines/workstation.json` committed to repo
- [ ] Jetson stack built and running (see [#297](https://github.com/jmm2020/UCIS-v1/issues/297) / `deployments/jetson/`)
- [ ] Jetson smoke test green:
  ```bash
  bash scripts/smoke_test.sh --host <jetson-ip> --platform jetson
  ```
- [ ] `tests/baselines/jetson.json` committed to repo
- [ ] Both baselines compared — differences reviewed (see [Acceptable Differences](#baseline-diff--acceptable-differences) below)

## Cutover Steps

1. **Redirect access** — Update browser bookmark / DNS / Tailscale/Cloudflare tunnel URL to point to `http://<jetson-ip>:8502`

2. **Stop workstation containers**:
   ```bash
   docker compose stop seestar-portal-ui seestar-portal-backend
   ```

3. **Run final smoke on Jetson**:
   ```bash
   bash scripts/smoke_test.sh --host <jetson-ip> --platform jetson
   ```

4. **Confirm exit 0** — all checks pass, baseline JSON updated

## Rollback Procedure

If Jetson deployment is not functioning correctly after cutover:

1. **Restart workstation containers**:
   ```bash
   docker compose start seestar-portal-ui seestar-portal-backend
   ```

2. **Revert access** — Point bookmark / DNS back to `http://localhost:8502`

3. **Run workstation smoke test**:
   ```bash
   bash scripts/smoke_test.sh --host localhost --platform workstation
   ```

4. Confirm exit 0 — workstation stack is healthy again

## Baseline Diff — Acceptable Differences

When comparing `tests/baselines/workstation.json` vs `tests/baselines/jetson.json`, these differences are **expected and acceptable**:

| Field | Workstation | Jetson | Why |
|-------|-------------|--------|-----|
| `platform` | `"workstation"` | `"jetson"` | By design — identifies deployment |
| `host` | `"localhost"` | `"<jetson-ip>"` | Different target hosts |
| `captured_at` | Timestamp A | Timestamp B | Different capture times |
| `services.*.status.response_time_ms` | Lower | Higher | ARM64 vs x86 performance difference |

**Unexpected differences** that should block cutover:
- Any service returning `{"error": ...}` on Jetson that returns healthy on workstation
- Missing endpoints (gallery, health, telescope status, sessions)
- WebSocket connection failures on Jetson when passing on workstation

## Execution Log

> Fill in when the runbook is actually executed.

| Date | Operator | Step | Result | Notes |
|------|----------|------|--------|-------|
| | | Pre-flight | | |
| | | Cutover | | |
| | | Post-cutover smoke | | |
