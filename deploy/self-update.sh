#!/bin/bash
# Run by the hookreel-update service on the server when HookReel's "Update now" button asks for it.
# It pulls the newest HookReel from GitHub and rebuilds, then writes how it went where HookReel can read it.
set -uo pipefail
D=/opt/hookreel/hostctl
rm -f "$D/update-requested"
echo "{\"state\":\"running\",\"at\":$(date +%s)}" > "$D/update-status"
{
  echo "Update started $(date -u '+%Y-%m-%d %H:%M UTC')"
  cd /opt/hookreel && git pull --ff-only && cp deploy/oracle-update.sh /run/hookreel-oracle-update.sh \
    && bash /run/hookreel-oracle-update.sh
} > "$D/update.log" 2>&1
code=$?
state=$([ $code -eq 0 ] && echo done || echo failed)
echo "{\"state\":\"$state\",\"at\":$(date +%s),\"code\":$code}" > "$D/update-status"
