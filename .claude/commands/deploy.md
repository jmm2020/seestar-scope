---
description: Deploy current main to the Jetson (git pull + docker compose rebuild + restart).
---

# Deploy

Deploy whatever is on `main` to the Jetson at `192.168.0.234`. **Workstation is source-only; nothing runs here.**

## Process

1. **Verify workstation state is clean and pushed**:
   ```bash
   git status                              # should be clean
   git log @{upstream}..HEAD --oneline     # should be empty (everything pushed)
   ```
   If not clean, commit + push first.

2. **Pre-flight on Jetson** (read-only, safe to run):
   ```bash
   ssh jmm2020@192.168.0.234 'cd ~/seestar-scope && git status && git log --oneline -5'
   ```

3. **Pre-flight env check** — run `/sync-env` first to catch env-var drift (especially the `setup.sh:96` `SEESTAR_PORT=11111` bug). A fresh Jetson install with that bug will silently fail to reach the scope.

4. **Pull, build, restart** (the actual deploy):
   ```bash
   ssh jmm2020@192.168.0.234 'cd ~/seestar-scope && \
     git pull --recurse-submodules && \
     docker compose build && \
     docker compose up -d'
   ```

   **Note on container count:** vanilla `docker compose up -d` brings up **3 containers** — `seestar-portal-ui`, `seestar-portal-backend`, `seestar-alp` — and skips `seestar-cloudflared`. The systemd unit (`seestar-stack.service`) instead runs `docker compose --profile tunnel up` (foreground, 4 containers). If you want the cloudflared tunnel sidecar during an SSH deploy, use:

   ```bash
   docker compose --profile tunnel up -d
   ```

5. **Verify the stack is healthy**:
   ```bash
   ssh jmm2020@192.168.0.234 'docker ps --filter name=seestar- --format "table {{.Names}}\t{{.Status}}"'
   ```
   Expect **3 containers** from a vanilla `up -d`, or **4** if you used `--profile tunnel` (or if systemd started the stack). All should be `Up` and (where applicable) `healthy`.

6. **Smoke test** (mirror of `/validate` Level 4):
   ```bash
   curl -sf http://192.168.0.234:8503/health
   curl -sf http://192.168.0.234:8503/api/gallery/onboard/health
   curl -sf http://192.168.0.234:8502/_stcore/health
   curl -sf http://192.168.0.234:5555/management/apiversions
   ```
   If `--profile tunnel` is active: `curl -sf https://s50.jmm2020ai.com/_stcore/health`.

## Config-only changes

If only `alp-config/config.toml` changed: edit on the **Jetson host** directly (not workstation), then:
```bash
ssh jmm2020@192.168.0.234 'docker restart seestar-alp'
```
The file is bind-mounted, no rebuild needed.

## Rollback

See `docs/migration_runbook.md` §Rollback. The short version:
```bash
ssh jmm2020@192.168.0.234 'cd ~/seestar-scope && git reset --hard <last-good-sha> && docker compose build && docker compose up -d'
```
