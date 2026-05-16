# Seestar S50 — Jetson Orin Deployment

One-command deployment of the SeestarScope portal on a Jetson Orin. The portal talks directly to the Seestar S50's native ALPACA endpoint at `192.168.0.132:32323` — no bridge container is required.

## Requirements

- **NVIDIA Jetson Orin** (Nano, NX, or AGX) with JetPack 6.x (Ubuntu 24.04)
- **Storage**: minimum 8 GB free (base images ~2 GB, captures/sessions volume ~2 GB)
- **Network**: LAN access to the Seestar S50 (default IP `192.168.0.132`)
- **Docker**: JetPack 6.x ships Docker 24.x with compose v2 built-in. Confirm with `docker compose version`

## One-Time Setup

### Option A: From cloned repo

```bash
cd ~/seestar-scope
bash deploy/jetson/setup.sh
```

### Option B: Standalone (fresh Jetson)

```bash
# Copy the setup script to the Jetson
scp deploy/jetson/setup.sh <user>@<jetson-ip>:~/setup.sh

# SSH in and run
ssh <user>@<jetson-ip>
bash ~/setup.sh
```

The script is **idempotent** — safe to re-run at any time.

### What `setup.sh` does

| Step | Action | Idempotent? |
|------|--------|-------------|
| 1 | Check prerequisites (git) | Yes |
| 2 | Install Docker (if missing via `get.docker.com`) | Yes — skips if present |
| 3 | Clone repo (or `git pull` if exists) | Yes |
| 4 | Create `.env` (interactive prompt for `SEESTAR_IP`) | Yes — skips if `.env` exists |
| 5 | `docker compose build` (ARM64 images) | Rebuilds each run |
| 6 | Install + enable `seestar-stack` systemd service | Yes — refreshes unit file |
| 7 | Print container status and portal URL | — |

## First-Boot Checklist

- [ ] Docker installed: `docker --version`
- [ ] Docker compose v2: `docker compose version`
- [ ] Images built: `docker images | grep seestar`
- [ ] Service enabled: `systemctl is-enabled seestar-stack`
- [ ] Containers running: `docker compose ps`
- [ ] Portal reachable: `curl -sf http://localhost:8502/_stcore/health`
- [ ] S50 IP confirmed: `grep SEESTAR_IP ~/seestar-scope/.env`

## Access

```
http://<jetson-ip>:8502
```

The portal is accessible from any device on the same LAN.

## Optional: Stellarium Integration

Stellarium Dashboard/GoTo/Sequence features require the Stellarium Remote Control plugin running at `STELLARIUM_HOST:STELLARIUM_PORT` (default: `localhost:8090`). Since the portal runs in Docker, `localhost` is the container — set `STELLARIUM_HOST=<workstation-ip>` in `.env` if Stellarium runs on your workstation.

See [README.md — Optional: Stellarium Integration](../../README.md#optional-stellarium-integration) for full setup steps.

## Remote Access via Cloudflare Tunnel

For deployments at remote sites, the compose file ships a `seestar-cloudflared`
sidecar behind the `tunnel` profile. It connects to the **existing** UCIS
Cloudflare tunnel (`831e21c1-a274-4f14-8b29-b91097f96c92`) as a second
connector — no new tunnel, no token wrangling.

### One-time setup on the Jetson

1. **Copy credentials from workstation** (where the tunnel is currently anchored):
   ```bash
   # From the workstation:
   scp /home/jmm2020/.cloudflared/831e21c1-a274-4f14-8b29-b91097f96c92.json \
       jmm2020@<jetson-ip>:~/seestar-scope/cloudflared/
   ```
   The JSON is gitignored (`cloudflared/*.json`) and never enters version
   control.

2. **Verify ingress rule** — `cloudflared/config.yml` already contains:
   ```yaml
   ingress:
     - hostname: s50.jmm2020ai.com
       service: http://seestar-portal-ui:8502
   ```
   Edit if you want a different hostname.

3. **Start with the tunnel profile**:
   ```bash
   cd ~/seestar-scope
   docker compose --profile tunnel up -d
   ```

The portal becomes reachable at `https://s50.jmm2020ai.com` from anywhere.

### Cutover (workstation → Jetson)

While both connectors are up, Cloudflare load-balances `s50.jmm2020ai.com`
between them — but the workstation still rewrites to its local
`http://localhost:8502`, while the Jetson rewrites to its container.
**Once you've verified the Jetson serves correctly**, remove the s50 rule
from the workstation tunnel:

```bash
# On the workstation:
sudo sed -i '/hostname: s50.jmm2020ai.com/,/service: http:\/\/localhost:8502/d' \
    /etc/cloudflared/config.yml
sudo systemctl reload cloudflared
```

After that, only the Jetson serves the route, and the workstation's
seestar containers can be stopped (`docker compose down` in the old
`KnowledgeBase/seestar_scope/`).

## Log Viewing

```bash
# systemd service logs
journalctl -u seestar-stack -f

# Docker container logs
cd ~/seestar-scope && docker compose logs -f

# Individual container
docker logs -f seestar-portal-ui
```

## Resource Baseline

Fill in after first deployment:

| Service | RSS Memory | CPU (idle) |
|---------|-----------|-----------|
| seestar-portal-backend | ~XXX MB | ~X% |
| seestar-portal-ui | ~XXX MB | ~X% |

Measure with: `docker stats --no-stream`

## Troubleshooting

### "permission denied" when running docker

You are not in the `docker` group. Run:

```bash
sudo usermod -aG docker $USER
# Log out and back in, then re-run setup.sh
```

### Submodule checkout fails

Network issue during clone. Re-run:

```bash
cd ~/seestar-scope
git submodule update --init --recursive
```

### Wrong SEESTAR_IP

Edit `~/seestar-scope/.env` and restart:

```bash
sudo systemctl restart seestar-stack
```

### Service won't start

```bash
systemctl status seestar-stack
journalctl -u seestar-stack --no-pager -n 50
```

Check that `WorkingDirectory` in `/etc/systemd/system/seestar-stack.service` points to the correct repo path.
