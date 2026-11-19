#!/bin/bash
# HookReel on an Oracle Cloud "Always Free" server (Ampere A1, Ubuntu 22.04 or 24.04), with no domain of your own.
#
# Paste this as the server's "cloud-init script" when you create it, with your email filled in:
#
#   #!/bin/bash
#   export HOOKREEL_OWNER=you@example.com
#   curl -fsSL https://raw.githubusercontent.com/developerpawanmaurya/HookReel/main/deploy/oracle-free.sh | bash
#
# What it does, once, on first boot (about 10 minutes):
#   - installs Docker and opens the web ports in the server's own firewall
#   - gives the site a free https address from sslip.io, built from the server's public IP (1-2-3-4.sslip.io)
#   - closes sign-up to everyone except HOOKREEL_OWNER, so nobody else can use your server or your AI key
#   - starts HookReel, and makes HOOKREEL_OWNER an admin as soon as that account signs up
# The cloud's own firewall (the VCN security list) must also allow TCP 80 and 443 from anywhere; see DEPLOY.md.
# Progress is written to /var/log/hookreel-setup.log.
set -euo pipefail
exec > >(tee -a /var/log/hookreel-setup.log) 2>&1
: "${HOOKREEL_OWNER:?set HOOKREEL_OWNER to your email address}"
REPO="${HOOKREEL_REPO:-https://github.com/developerpawanmaurya/HookReel.git}"
DIR=/opt/hookreel
export DEBIAN_FRONTEND=noninteractive

echo "== $(date) HookReel setup starting"
apt-get update -y
apt-get install -y ca-certificates curl git openssl iptables-persistent
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

# Oracle's Ubuntu images reject everything but SSH in iptables: let the web in, before that reject rule
for port in 80 443; do
  iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
    || iptables -I INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT
done
netfilter-persistent save || true

# A little swap, so a long video can't run the server out of memory
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

[ -d "$DIR/.git" ] || git clone --depth 50 "$REPO" "$DIR"
cd "$DIR"

IP="$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me)"
DOMAIN="${HOOKREEL_DOMAIN:-${IP//./-}.sslip.io}"
if [ ! -f .env ]; then
  cat > .env <<EOF
HOOKREEL_DOMAIN=$DOMAIN
POSTGRES_PASSWORD=$(openssl rand -hex 24)
COMPOSE_PROFILES=own-https,youtube
# Cloud addresses are often refused by YouTube: fetch YouTube through Cloudflare WARP, with a PO token
HOOKREEL_YT_PROXY=http://warp:1080
HOOKREEL_YT_POT_URL=http://pot:4416
HOOKREEL_ALLOWED_EMAILS=$HOOKREEL_OWNER
# Two cores: one video at a time keeps the site responsive
HOOKREEL_JOB_WORKERS=1
HOOKREEL_MAX_LIVE=1
EOF
  chmod 600 .env
fi
mkdir -p secrets

docker compose up -d --build

# Make the owner an admin as soon as they have signed up (tries every 30 seconds for up to 3 days)
cat > /usr/local/bin/hookreel-grant-owner <<EOF
#!/bin/bash
cd $DIR
for i in \$(seq 1 8640); do
  docker compose exec -T app python -m studio.admin grant "$HOOKREEL_OWNER" && exit 0
  sleep 30
done
EOF
chmod +x /usr/local/bin/hookreel-grant-owner
systemd-run --unit=hookreel-grant-owner --collect /usr/local/bin/hookreel-grant-owner || true

echo "== $(date) HookReel is starting at https://$DOMAIN"
echo "   The first start downloads the speech model (about 480 MB). Sign up there with $HOOKREEL_OWNER."
