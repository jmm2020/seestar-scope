---
description: Diagnose the S50 ↔ portal stack — firmware 7.34 PEM auth, verify_injection, scope panel degradation.
---

# Debug Scope

Walk the diagnostic chain when the portal's scope panels are degraded or method_sync calls hang. **Read `AGENTS.md` §"Root cause of scope panels not working" first** — that's the canonical writeup of the 7.34 regression.

## Symptoms → Likely Cause

| Symptom | Likely cause |
|---|---|
| Scope panels show "degraded" warnings | `:4700` PEM-gated; `verify_injection = false` is doing its job |
| Goto / Unpark / mosaic / scheduling all broken | Same — needs PEM pairing |
| `method_sync` PUT to `:5555` hangs forever | `seestar_alp` waiting on `:4700`; scope dropping messages silently |
| `seestar_alp` logs `TypeError: string indices must be integers` at `seestar_device.py:1144` | `verify_injection = true` is back on; scope returned a string error envelope |
| MJPEG stream `:7556` works | Bridge is alive |
| ALPACA `:32323` returns RA/Dec/altitude | Native firmware ALPACA is healthy |
| Gallery (guest channel) works | `:4701` whitelist is intact |

## Process

1. **Confirm the scope is reachable**:
   ```bash
   curl -sf http://192.168.0.132:32323/management/apiversions
   curl -sf http://192.168.0.132/MyWorks/ 2>&1 | head -20
   ```

2. **Check seestar_alp config on the Jetson**:
   ```bash
   ssh jmm2020@192.168.0.234 'cat ~/seestar-scope/alp-config/config.toml | grep -A2 verify_injection'
   ```
   Should show `verify_injection = false`. If it's `true`, that's why the bridge is crash-looping.

3. **Tail seestar_alp logs** (the real log is inside the container, not `docker logs`):
   ```bash
   ssh jmm2020@192.168.0.234 'docker exec seestar-alp tail -100 /home/seestar/seestar_alp/alpyca.log'
   ```
   Look for `start_up_thread_fn` crashes or `TypeError: string indices must be integers`.

4. **Verify the in-container code matches what we expect** (line numbers can drift from `vendor/seestar_alp/`):
   ```bash
   ssh jmm2020@192.168.0.234 'docker exec seestar-alp sed -n "1140,1150p" /home/seestar/seestar_alp/device/seestar_device.py'
   ```

5. **Check the guest channel** (should still work even when `:4700` is dead):
   ```bash
   ssh jmm2020@192.168.0.234 'docker exec seestar-portal-backend curl -sf http://seestar-alp:5555/api/v1/telescope/0/connected'
   ```

6. **If the bridge has crash-looped**, restart it:
   ```bash
   ssh jmm2020@192.168.0.234 'docker restart seestar-alp'
   ```

## Open question (next session)

How does firmware 7.34 establish trust with a new client? Three avenues:
1. Reverse-engineer the iPad app pairing handshake (mitmproxy on iPad → scope)
2. Check `smart-underworld/seestar_alp` upstream for 7.34 support — issues/PRs
3. Look for a scope-side pairing UI or button combo to register a public key

Don't go down this rabbit hole on a normal session — it's a research thread, not a fix-the-bug-now task.
