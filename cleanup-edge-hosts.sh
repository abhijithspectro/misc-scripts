#!/usr/bin/env bash
# Clean Portworx host leftovers on Kairos/edge nodes.
#
# Usage:
#   ./cleanup-edge-hosts.sh <ip> [ip...]
#   SSH_USER=kairos SSH_PASS=kairos ./cleanup-edge-hosts.sh 10.10.141.177
#
# Requires: sshpass
set -euo pipefail

SSH_USER="${SSH_USER:-kairos}"
SSH_PASS="${SSH_PASS:-kairos}"
SSH_OPTS=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=20
  -o ServerAliveInterval=5
  -o LogLevel=ERROR
)

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <ip> [ip...]" >&2
  exit 1
fi

if ! command -v sshpass >/dev/null 2>&1; then
  echo "sshpass is required (brew install sshpass / apt install sshpass)" >&2
  exit 1
fi

# Remote cleanup body (run as root via sudo -i).
# shellcheck disable=SC2016
REMOTE_SCRIPT=$(cat <<'EOF'
set -euo pipefail

echo "=== host: $(hostname) ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

echo "--- before ---"
ls -lad /etc/pwx /opt/pwx /var/lib/osd /var/lib/portworx 2>/dev/null || true
blkid 2>/dev/null | grep -iE 'pxpool|portworx|PX_' || echo "(no px blkid labels)"
systemctl is-active portworx 2>/dev/null || true

# Stop / disable Portworx systemd units if present.
if systemctl list-unit-files 'portworx*' 2>/dev/null | grep -q portworx; then
  systemctl stop portworx 2>/dev/null || true
  systemctl disable portworx 2>/dev/null || true
fi
rm -f /etc/systemd/system/portworx* /usr/lib/systemd/system/portworx* 2>/dev/null || true
systemctl daemon-reload 2>/dev/null || true

# Unmount OCI rootfs if still mounted.
if grep -q '/opt/pwx/oci /opt/pwx/oci' /proc/self/mountinfo 2>/dev/null; then
  umount /opt/pwx/oci || umount -l /opt/pwx/oci || true
fi

# Prefer pxctl node-wipe when binaries remain.
if [[ -x /opt/pwx/bin/pxctl ]]; then
  echo "Running pxctl service node-wipe --all"
  /opt/pwx/bin/pxctl service node-wipe --all || true
fi

# Wipe Portworx filesystem signatures from local disks (pxpool metadata).
mapfile -t PX_DEVS < <(blkid 2>/dev/null | grep -iE 'pxpool|PX_' | cut -d: -f1 | sort -u || true)
if [[ ${#PX_DEVS[@]} -gt 0 ]]; then
  for dev in "${PX_DEVS[@]}"; do
    echo "wipefs -af $dev"
    wipefs -af "$dev"
  done
else
  echo "(no pxpool devices to wipe)"
fi

# Remove install trees. On Kairos, /etc/pwx and /var/lib/osd are OEM bind
# mounts from /usr/local/.state — remove contents; keep the mountpoints.
rm -rf /opt/pwx /var/lib/portworx
if [[ -d /etc/pwx ]]; then
  find /etc/pwx -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi
if [[ -d /var/lib/osd ]]; then
  find /var/lib/osd -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi
# Also clear Kairos persistent state dirs if present.
if [[ -d /usr/local/.state/etc-pwx.bind ]]; then
  find /usr/local/.state/etc-pwx.bind -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi
if [[ -d /usr/local/.state/var-lib-osd.bind ]]; then
  find /usr/local/.state/var-lib-osd.bind -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi
if [[ -d /usr/local/.state/var-cores.bind ]]; then
  find /usr/local/.state/var-cores.bind -mindepth 1 -maxdepth 1 -name 'px*' -exec rm -rf {} + 2>/dev/null || true
fi

# Drop any leftover px kernel modules / devices (best-effort).
rmmod px 2>/dev/null || true
rm -f /dev/pxd* 2>/dev/null || true

echo "--- after ---"
ls -lad /etc/pwx /opt/pwx /var/lib/osd /var/lib/portworx 2>/dev/null || true
ls -la /etc/pwx /var/lib/osd 2>/dev/null || true
blkid 2>/dev/null | grep -iE 'pxpool|portworx|PX_' || echo "(no px blkid labels)"
echo "=== cleanup complete on $(hostname) ==="
EOF
)

REMOTE_B64="$(printf '%s' "$REMOTE_SCRIPT" | base64 | tr -d '\n')"

cleanup_host() {
  local ip="$1"
  echo
  echo "######## cleaning $ip ########"
  # Gain root with sudo -i; password auth via sshpass + stdin to sudo.
  sshpass -p "$SSH_PASS" ssh "${SSH_OPTS[@]}" "${SSH_USER}@${ip}" \
    "echo '$SSH_PASS' | sudo -S -i bash -c 'echo $REMOTE_B64 | base64 -d | bash'"
}

failed=0
for ip in "$@"; do
  if ! cleanup_host "$ip"; then
    echo "FAILED: $ip" >&2
    failed=1
  fi
done

if [[ "$failed" -ne 0 ]]; then
  echo "One or more hosts failed." >&2
  exit 1
fi

echo
echo "All hosts cleaned."
