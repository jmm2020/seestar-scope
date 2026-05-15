# AGENTS.md — seestar-scope

Canonical project topology and operational facts for any coding agent (Claude Code, Cursor, Codex, etc.). Read this FIRST before assuming where anything runs.

---

## Hosts & Ports (CRITICAL — check this FIRST)

| Host | IP | Role | Listens on |
|---|---|---|---|
| Workstation | 192.168.0.36 | Dev box (this machine). Source lives here. **Nothing runs here.** | — |
| **Jetson** | **192.168.0.234** | Runs the portal stack via docker compose. Hostname `john-ubuntu-24-04`. SSH: `ssh jmm2020@192.168.0.234` (key-based, no config alias yet) | 22 (ssh), 5555 (seestar_alp action), 7556 (MJPEG), 8502 (portal-ui), 8503 (portal-backend) |
| **Scope (S50)** | **192.168.0.132** | Seestar S50, firmware 7.34. Runs its own ALPACA server. | 32323 (ALPACA — works), 4700 (JSON-RPC — PEM-gated on 7.34), 4701 (JSON-RPC guest channel — works; no PEM for whitelisted methods), 4720 (UDP intro — silent), 4800/4801 (imaging streams), 80 (HTTP static file server — serves MyWorks/ album content) |

## Request Flow

```
browser → portal-backend (.234:8503) → seestar_alp action PUT (.234:5555)
                                      → scope JSON-RPC (.132:4700)  ← BLOCKED on 7.34
```

Independent path (works without auth):
```
browser → ALPACA (.132:32323) ← scope firmware native
```

## Guest JSON-RPC Channel (:4701)

Firmware 7.34 exposes a second TCP JSON-RPC listener on :4701 that does **not** require the signed `verify` token. Some methods are whitelisted for guest access:

| Method | Returns | Verified |
|--------|---------|---------|
| `get_albums` | `{path: "MyWorks", list: [{group_name, files: [{name, thn, count, type}]}]}` | firmware 7.34, 2026-05-14 |

The scope's HTTP server on :80 serves the album content directly:
- `http://{scope_ip}/MyWorks/{thn}` — thumbnail JPEG
- `http://{scope_ip}/MyWorks/{thn_stripped}.jpg` — full-res JPEG
- `http://{scope_ip}/MyWorks/{thn_stripped}.mp4` — timelapse MP4 (when `name.endswith("_video")`)

The portal backend proxies thumbnails through `/api/gallery/onboard/thumbnail?path=...` for browser caching; full-res images/videos are served directly from the scope to the browser.

## Jetson container names

`docker ps` on Jetson shows:
- `seestar-portal-ui` (port 8502)
- `seestar-portal-backend` (port 8503)
- `seestar-alp` (ports 5555, 7556)
- `seestar-cloudflared` (tunnel)

Logs:
- seestar-alp internal log: `/home/seestar/seestar_alp/alpyca.log` (set `log_to_stdout = true` in config.toml to also get `docker logs` output)

## Config

- seestar_alp config.toml on Jetson host: `/home/jmm2020/seestar-scope/alp-config/config.toml`
- Bind-mounted into container at `/home/seestar/seestar_alp/device/config.toml`
- Edit on host, then `docker restart seestar-alp` to apply

## Root cause of "scope panels not working" (2026-05-12)

**The real bug isn't a timeout — it's authentication.** Firmware 7.34's :4700 channel requires every JSON-RPC message to carry a *signed* `verify` token. Without the matching PEM, the scope drops messages silently (or with a bogus auth-error string envelope, depending on what we send).

Diagnostic chain that got us there:
1. `method_sync` PUT on :5555 hangs → seestar_alp is waiting on :4700 → scope doesn't reply
2. `seestar_alp` log shows `TypeError: string indices must be integers, not 'str'` at `device/seestar_device.py:1144` — happens because `response["result"]` is a STRING (an auth-error envelope), not the expected dict
3. With `verify_injection = true` (default) + no PEM → seestar_alp appends literal `"verify"` to every call → scope returns string error → `start_up_thread_fn` crashes → state machine stuck → all subsequent `method_sync` calls hang because nothing's alive to dispatch the reply
4. UDP intro on :4720 also silent — guest mode does NOT establish on 7.34 even with the correct payload

What's been applied (config edits live on Jetson):
- `verify_injection = false` — stops the crash loop in `start_up_thread_fn`. **Does not** unlock :4700 — :4700 stays silent because firmware 7.34 needs signed verify. But the portal no longer crash-loops; it degrades gracefully via the try/except guards already in the portal-backend code.

## What's still broken (and what's not)

| Capability | Path | Status |
|---|---|---|
| Telescope state read (RA/Dec/altitude/atpark/connected) | ALPACA :32323 → scope native | **works** |
| Image stream | MJPEG :7556 from seestar-alp | **works** |
| Portal backend routing | :8503 → :5555 | **works** (returns degraded data) |
| Device-health panel | needs `get_device_state` via method_sync | **degraded** — shows warning |
| Session-status / stacking panel | needs `get_view_state` via method_sync | **degraded** — shows warning |
| Goto / Unpark | needs `start_up_sequence` via :4700 | **broken** — requires PEM |
| Mosaics, scheduling, stacking control | needs :4700 | **broken** — requires PEM |
| Onboard archive browsing (gallery) | guest JSON-RPC :4701 → `get_albums` + HTTP :80 | **works** — no PEM needed |

## Operational Notes

- Source code at `/media/jmm2020/AIDrive1/code/seestar-scope/` (this repo)
- Deploy: edit on workstation → push → pull/restart on Jetson
- ALPACA on scope ≠ ALPACA on seestar_alp — scope has its own at :32323 (Alpyca 1.2.0-3 fingerprint)
- DeviceNumber is **0**, not 1 (ALPACA management API confirms)
- Useful: `vendor/seestar_alp/` is a checkout but the Jetson container has a NEWER copy — line numbers may not match. When debugging, check inside container with `docker exec seestar-alp sed -n 'Np' /home/seestar/seestar_alp/device/seestar_device.py`
- **Cloudflared tunnel `831e21c1-a274-4f14-8b29-b91097f96c92` is SHARED with the workstation UCIS-constellation tunnel.** Defined in `cloudflared/config.yml`. If the credentials are rotated on the workstation (or the tunnel is deleted/recreated there), seestar-scope's tunnel breaks silently — `seestar-cloudflared` will keep running but lose its route. Coordinate any rotation across both projects.

## What I should NEVER assume again

- The portal does NOT run on the workstation
- seestar_alp does NOT run on the workstation
- Containers on this machine are UCIS, not seestar-scope
- "Backend on :8503" means **Jetson .234**, not localhost
- `vendor/seestar_alp/` source ≠ what's actually running on Jetson — diff before patching
- **`deploy/jetson/setup.sh:96` writes `SEESTAR_PORT=11111`** instead of the correct `32323`. This is a real production bug — a fresh Jetson install via `bash deploy/jetson/setup.sh` will land with the wrong port, and the portal backend will silently fail to reach the scope. Either edit the generated `.env` manually after running setup, or fix `setup.sh` before running it. Tracked separately from the AI Layer reconciliation — needs its own commit.

## Open question for next session

How does firmware 7.34 establish trust with a new client? Three avenues to investigate:
1. Reverse-engineer iPad app pairing handshake (mitmproxy on iPad traffic to scope)
2. Check seestar_alp upstream (smart-underworld/seestar_alp) for 7.34 support — recent issues/PRs
3. Look for a scope-side pairing UI or button combo that lets a new client register its public key
