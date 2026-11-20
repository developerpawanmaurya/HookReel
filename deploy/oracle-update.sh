#!/bin/bash
# Update a HookReel server made with deploy/oracle-free.sh to the newest version, and turn on the YouTube helpers
# if they are not on yet. Run on the server:  curl -fsSL <raw url of this file> | sudo bash
set -euo pipefail
cd /opt/hookreel
git pull --ff-only
# ffmpeg (which fetches clip pieces) cannot use a SOCKS proxy: use the same WARP helper over HTTP
sed -i 's#^HOOKREEL_YT_PROXY=socks5://warp:1080#HOOKREEL_YT_PROXY=http://warp:1080#' .env
grep -q '^HOOKREEL_YT_PROXY=' .env || cat >> .env <<'ENV'
HOOKREEL_YT_PROXY=http://warp:1080
HOOKREEL_YT_POT_URL=http://pot:4416
ENV
grep -q '^COMPOSE_PROFILES=.*youtube' .env || sed -i 's/^COMPOSE_PROFILES=\(.*\)$/COMPOSE_PROFILES=\1,youtube/' .env
# "Update now" in HookReel: a helper on this server that runs deploy/self-update.sh when HookReel asks for it
mkdir -p hostctl
cat > /etc/systemd/system/hookreel-update.path <<'UNIT'
[Unit]
Description=Watch for HookReel's "Update now" button

[Path]
PathExists=/opt/hookreel/hostctl/update-requested
Unit=hookreel-update.service

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/hookreel-update.service <<'UNIT'
[Unit]
Description=Update HookReel to the newest version
After=docker.service

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'cp /opt/hookreel/deploy/self-update.sh /run/hookreel-self-update.sh && exec /bin/bash /run/hookreel-self-update.sh'
TimeoutStartSec=3600
UNIT
systemctl daemon-reload
systemctl enable --now hookreel-update.path >/dev/null 2>&1 || true
touch hostctl/updater
docker compose up -d --build
docker compose ps --format '{{.Service}}: {{.State}}'
echo "HookReel is updated."
