#!/bin/bash
# Update a HookReel server made with deploy/oracle-free.sh to the newest version, and turn on the YouTube helpers
# if they are not on yet. Run on the server:  curl -fsSL <raw url of this file> | sudo bash
set -euo pipefail
cd /opt/hookreel
git pull --ff-only
grep -q '^HOOKREEL_YT_PROXY=' .env || cat >> .env <<'ENV'
HOOKREEL_YT_PROXY=socks5://warp:1080
HOOKREEL_YT_POT_URL=http://pot:4416
ENV
grep -q '^COMPOSE_PROFILES=.*youtube' .env || sed -i 's/^COMPOSE_PROFILES=\(.*\)$/COMPOSE_PROFILES=\1,youtube/' .env
docker compose up -d --build
docker compose ps --format '{{.Service}}: {{.State}}'
echo "HookReel is updated."
