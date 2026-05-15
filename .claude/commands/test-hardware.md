---
description: Run S50-hardware-dependent tests against the live scope at 192.168.0.132
---

# Test Hardware

## Objective

Run tests marked `@pytest.mark.hardware` against the live S50 (network reachable, ALPACA :32323 responding). These tests are skipped in CI via `-m "not hardware"` and on every `/validate` run.

**Currently zero tests carry the marker** — the marker is registered (`portal/tests/conftest.py:3`) and the CI filter is honored, but no tests use it. Use this command as part of the convention for any new test that needs a live scope.

## Pre-flight

### 1. Confirm the scope is reachable

!`curl -sf http://192.168.0.132:32323/management/apiversions | head -5 || echo "❌ scope unreachable"`

Abort if not reachable. Check:
- Scope powered on and on the same LAN
- IP correct (`SEESTAR_IP` env)
- Firewall not blocking :32323

### 2. Confirm the Jetson stack is in the desired state (if testing against the Jetson, not workstation Python)

```bash
ssh jmm2020@192.168.0.234 'docker ps --filter name=seestar- --format "{{.Names}} {{.Status}}"'
```

## Run the tests

From the workstation (with workstation Python pointed at the live scope):

```bash
PYTHONPATH=. SEESTAR_IP=192.168.0.132 SEESTAR_PORT=32323 \
  pytest portal/tests/ -m "hardware" -v
```

If you want to run a focused subset:

```bash
PYTHONPATH=. SEESTAR_IP=192.168.0.132 SEESTAR_PORT=32323 \
  pytest portal/tests/test_<name>.py -m "hardware" -v
```

## Report

Output:

```
## Hardware Test Report

| Test | Result | Notes |
|---|---|---|
| test_xxx | PASS | |
| test_yyy | FAIL | scope returned 503 — :4700 PEM-gated as expected |

### Scope state at run
- ALPACA :32323: reachable / not
- Time: ...
- Firmware: 7.34 (from `/management/apiversions`)

### Conclusion
{pass/fail summary, any flakes, follow-up}
```

If zero tests carry the `hardware` marker today, this command will run nothing — report that and suggest adding the marker to S50-dependent tests as they're written. Do not fail.
