# Seestar S50 — Jetson Orin Deployment

One-command deployment of the Seestar portal + ALP backend on a Jetson Orin.

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
| 3 | Clone repo with submodules (or `git pull` if exists) | Yes |
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

## Remote Access via Cloudflare Tunnel

For deployments at remote sites (no LAN access from the workstation), the
compose file ships a `seestar-cloudflared` service behind the `tunnel` profile.

### One-time setup (Cloudflare Zero Trust dashboard)

1. **Create a tunnel** — Networks → Tunnels → Create a tunnel → name `seestar-jetson`.
2. **Copy the token** — shown once during setup. Add to `.env`:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...
   ```
3. **Configure ingress** — Public Hostname → Add:
   - Subdomain: `s50` (or your choice)
   - Domain: `jmm2020ai.com`
   - Service: `http://seestar-portal-ui:8502`

### Start with tunnel

```bash
docker compose --profile tunnel up -d
```

The portal becomes reachable at `https://s50.jmm2020ai.com` from anywhere.

### Cutover note (workstation → Jetson)

If `s50.jmm2020ai.com` was previously routed to the workstation's tunnel,
remove that hostname from the workstation's `/etc/cloudflared/config.yml`
*after* confirming the Jetson tunnel works. DNS at the Cloudflare side
takes effect within seconds.

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
| seestar-alp | ~XXX MB | ~X% |
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
