#!/bin/bash
# Create a free HookReel server on Oracle Cloud, from Oracle's own Cloud Shell (the >_ button in the console).
#
#   curl -fsSL https://raw.githubusercontent.com/developerpawanmaurya/HookReel/main/deploy/oracle-provision.sh | OWNER=you@example.com bash
#
# It makes a network that lets the web in (ports 80 and 443, plus SSH), then an Always Free Arm server
# (2 cores, 12 GB memory) that installs HookReel by itself on first boot (deploy/oracle-free.sh). Running it again
# reuses what is already there. When Oracle has no free Arm capacity at the moment, it keeps retrying for a while.
set -euo pipefail
: "${OWNER:?run it with OWNER=your@email}"
T="${OCI_TENANCY:?run this in Oracle Cloud Shell}"
NAME=hookreel
q() { oci "$@" --raw-output 2>/dev/null; }

echo "== network"
VCN=$(q network vcn list -c "$T" --display-name "$NAME-vcn" --lifecycle-state AVAILABLE --query 'data[0].id' || true)
if [ -z "$VCN" ] || [ "$VCN" = "null" ]; then
  VCN=$(q network vcn create -c "$T" --cidr-block 10.0.0.0/16 --display-name "$NAME-vcn" --dns-label "$NAME" \
        --wait-for-state AVAILABLE --query data.id)
fi
IGW=$(q network internet-gateway list -c "$T" --vcn-id "$VCN" --query 'data[0].id' || true)
if [ -z "$IGW" ] || [ "$IGW" = "null" ]; then
  IGW=$(q network internet-gateway create -c "$T" --vcn-id "$VCN" --is-enabled true --display-name "$NAME-igw" \
        --wait-for-state AVAILABLE --query data.id)
fi
RT=$(q network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"')
SL=$(q network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"')
oci network route-table update --rt-id "$RT" --force \
  --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
rule() { echo "{\"source\":\"0.0.0.0/0\",\"protocol\":\"6\",\"isStateless\":false,\"tcpOptions\":{\"destinationPortRange\":{\"min\":$1,\"max\":$1}}}"; }
oci network security-list update --security-list-id "$SL" --force \
  --ingress-security-rules "[$(rule 22),$(rule 80),$(rule 443),{\"source\":\"0.0.0.0/0\",\"protocol\":\"1\",\"isStateless\":false,\"icmpOptions\":{\"type\":3,\"code\":4}}]" >/dev/null
SUBNET=$(q network subnet list -c "$T" --vcn-id "$VCN" --display-name "$NAME-public" --query 'data[0].id' || true)
if [ -z "$SUBNET" ] || [ "$SUBNET" = "null" ]; then
  SUBNET=$(q network subnet create -c "$T" --vcn-id "$VCN" --cidr-block 10.0.0.0/24 --display-name "$NAME-public" \
           --dns-label pub --wait-for-state AVAILABLE --query data.id)
fi
echo "   ports 22, 80 and 443 are open"

echo "== server"
INST=$(q compute instance list -c "$T" --display-name "$NAME" --lifecycle-state RUNNING --query 'data[0].id' || true)
if [ -z "$INST" ] || [ "$INST" = "null" ]; then
  IMAGE=$(q compute image list -c "$T" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
          --shape VM.Standard.A1.Flex --sort-by TIMECREATED --sort-order DESC --query 'data[0].id')
  [ -f ~/.ssh/id_rsa ] || ssh-keygen -q -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
  UD=$(mktemp)
  cat > "$UD" <<EOF
#!/bin/bash
export HOOKREEL_OWNER=$OWNER
curl -fsSL https://raw.githubusercontent.com/developerpawanmaurya/HookReel/main/deploy/oracle-free.sh | bash
EOF
  ADS=$(q iam availability-domain list -c "$T" --query 'join(`" "`, data[*].name)')
  for attempt in $(seq 1 30); do
    for AD in $ADS; do
      echo "   asking for an Arm server in $AD (try $attempt)"
      if INST=$(oci --raw-output compute instance launch -c "$T" --availability-domain "$AD" --display-name "$NAME" \
           --shape VM.Standard.A1.Flex --shape-config '{"ocpus":2,"memoryInGBs":12}' \
           --image-id "$IMAGE" --subnet-id "$SUBNET" --assign-public-ip true --boot-volume-size-in-gbs 150 \
           --ssh-authorized-keys-file ~/.ssh/id_rsa.pub --user-data-file "$UD" \
           --wait-for-state RUNNING --query data.id 2>/tmp/hookreel-launch.err); then
        break 2
      fi
      INST=""
      grep -o '"message": "[^"]*"' /tmp/hookreel-launch.err | head -1 | sed 's/^/   Oracle says: /' || true
    done
    echo "   no free Arm capacity right now; trying again in 60 seconds"
    sleep 60
  done
  [ -n "$INST" ] || { echo "Oracle had no free Arm capacity. Run this again later."; exit 1; }
fi
IP=$(q compute instance list-vnics --instance-id "$INST" --query 'data[0]."public-ip"')
echo
echo "== done. The server is $IP"
echo "   HookReel installs itself now (10 to 15 minutes), then opens at:"
echo "   https://${IP//./-}.sslip.io"
echo "   Sign up there with $OWNER. Watch the setup: ssh ubuntu@$IP tail -f /var/log/hookreel-setup.log"
