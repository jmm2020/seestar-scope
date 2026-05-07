#!/usr/bin/env bash
# setup.sh — Idempotent Seestar S50 stack installer for Jetson Orin
#
# Usage:
#   bash setup.sh
#   SEESTAR_REPO_DIR=/opt/seestar-scope bash setup.sh
#
# Run from the repo root or copy to a standalone Jetson and run directly.
# Requires: git, internet access for Docker install and repo clone.

set -euo pipefail

REPO_URL="https://github.com/jmm2020/seestar-scope.git"
REPO_DIR="${SEESTAR_REPO_DIR:-/home/$(whoami)/seestar-scope}"
SERVICE_NAME="seestar-stack"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/seestar-stack.service"
DEFAULT_SEESTAR_IP="192.168.0.132"

pass() { echo "    [OK] $1"; }
fail() { echo "    [FAIL] $1"; }

# ── 1. Prerequisites ────────────────────────────────────────────────────────
echo "==> [1/7] Checking prerequisites"

if command -v git &>/dev/null; then
  pass "git $(git --version | awk '{print $3}')"
else
  fail "git not found — install with: sudo apt-get install -y git"
  exit 1
fi

# ── 2. Docker install (idempotent) ───────────────────────────────────────────
echo "==> [2/7] Checking Docker"

if command -v docker &>/dev/null; then
  pass "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
else
  echo "    Docker not found — installing via get.docker.com ..."
  curl -fsSL https://get.docker.com | sudo sh
  pass "Docker installed"
fi

# Ensure docker compose v2 is available
if docker compose version &>/dev/null; then
  pass "docker compose $(docker compose version --short)"
else
  fail "docker compose v2 not available — JetPack 6.x should include it"
  exit 1
fi

# Ensure current user is in docker group
if groups | grep -qw docker; then
  pass "User $(whoami) is in docker group"
else
  echo "    Adding $(whoami) to docker group ..."
  sudo usermod -aG docker "$(whoami)"
  echo ""
  echo "    *** You were added to the docker group. ***"
  echo "    *** Log out and back in, then re-run this script. ***"
  exit 0
fi

# ── 3. Clone repo (idempotent) ───────────────────────────────────────────────
echo "==> [3/7] Cloning repository"

if [ -d "$REPO_DIR/.git" ]; then
  pass "Repo already exists at $REPO_DIR — pulling latest"
  if ! git -C "$REPO_DIR" pull --ff-only 2>&1 | sed 's/^/    /'; then
    echo "    [WARN] git pull failed — continuing with existing checkout"
  fi
  git -C "$REPO_DIR" submodule update --init --recursive
else
  echo "    Cloning $REPO_URL → $REPO_DIR (this may take a few minutes) ..."
  git clone --recurse-submodules "$REPO_URL" "$REPO_DIR"
  pass "Clone complete"
fi

# ── 4. Configure .env (idempotent) ──────────────────────────────────────────
echo "==> [4/7] Configuring .env"

if [ -f "$REPO_DIR/.env" ]; then
  pass ".env already exists — skipping (edit $REPO_DIR/.env to change settings)"
else
  SEESTAR_IP="$DEFAULT_SEESTAR_IP"
  if [ -t 0 ]; then
    read -r -p "    Enter Seestar S50 IP [$DEFAULT_SEESTAR_IP]: " -t 30 USER_IP || true
    [ -n "${USER_IP:-}" ] && SEESTAR_IP="$USER_IP"
  else
    echo "    Non-interactive mode — using default SEESTAR_IP=$DEFAULT_SEESTAR_IP"
  fi

  cat > "$REPO_DIR/.env" <<EOF
# Seestar S50 — Jetson Orin defaults
SEESTAR_IP=$SEESTAR_IP
SEESTAR_PORT=11111
TZ=America/New_York
BACKEND_URL=http://seestar-portal-backend:8503
EOF
  pass ".env created (SEESTAR_IP=$SEESTAR_IP)"
fi

# ── 5. Build Docker images ──────────────────────────────────────────────────
echo "==> [5/7] Building Docker images (first run may take several minutes)"

cd "$REPO_DIR"
docker compose build
pass "Images built"

# ── 6. Install + enable systemd unit ────────────────────────────────────────
echo "==> [6/7] Installing systemd service"

# Resolve service file: prefer adjacent copy, fall back to cloned repo
if [ ! -f "$SERVICE_FILE" ]; then
  SERVICE_FILE="$REPO_DIR/deploy/jetson/seestar-stack.service"
fi
if [ ! -f "$SERVICE_FILE" ]; then
  fail "seestar-stack.service not found — cannot install systemd unit"
  exit 1
fi

# Patch WorkingDirectory and User to match actual REPO_DIR and current user
sed -e "s|WorkingDirectory=.*|WorkingDirectory=$REPO_DIR|" \
    -e "s|User=.*|User=$(whoami)|" \
    "$SERVICE_FILE" \
  | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
pass "$SERVICE_NAME enabled and started"

# ── 7. Verification ─────────────────────────────────────────────────────────
echo "==> [7/7] Verification"

echo "    Waiting for containers to become healthy (up to 60s) ..."
for i in {1..12}; do
  sleep 5
  RUNNING=$(docker compose ps --status running --quiet 2>/dev/null | grep -c . || true)
  if [ "$RUNNING" -ge 3 ]; then
    break
  fi
  echo "    ... ($((i * 5))s — $RUNNING/3 containers running)"
done
if [ "${RUNNING:-0}" -lt 3 ]; then
  echo ""
  echo "    [ERROR] Only ${RUNNING:-0}/3 containers running after 60s"
  echo "    Run: cd $REPO_DIR && docker compose ps"
  echo "    Run: docker compose logs"
  exit 1
fi

docker compose ps
echo ""

# First routable LAN IP — skips Docker bridge (172.*) and loopback (127.*)
JETSON_IP=$(hostname -I | awk '{for(i=1;i<=NF;i++) if($i !~ /^(172\.|127\.)/) {print $i; exit}}')
JETSON_IP="${JETSON_IP:-<jetson-ip>}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  Portal:  http://${JETSON_IP}:8502"
echo "  Logs:    journalctl -u $SERVICE_NAME -f"
echo "  Status:  systemctl status $SERVICE_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
