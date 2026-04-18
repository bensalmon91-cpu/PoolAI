#!/usr/bin/env bash
# Migrate the bootstrap secret from the per-device settings file into
# /etc/poolai/bootstrap.secret so the updated persist.py (which no longer
# bakes the secret into source) can continue to load it.
#
# Run ONCE per Pi during the rollout of the secret-out-of-source change.
# Idempotent: safe to re-run.
#
# Usage:
#   sudo /opt/PoolAIssistant/app/scripts/migrate_bootstrap_secret.sh

set -euo pipefail

SETTINGS=/opt/PoolAIssistant/data/pooldash_settings.json
SECRET_DIR=/etc/poolai
SECRET_FILE="$SECRET_DIR/bootstrap.secret"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: must run as root (need to write $SECRET_FILE)" >&2
    exit 1
fi

if [[ ! -f "$SETTINGS" ]]; then
    echo "ERROR: $SETTINGS not found; cannot extract existing secret" >&2
    exit 1
fi

# Extract bootstrap_secret with a tiny Python one-liner so we don't depend
# on jq being installed.
SECRET=$(python3 -c "
import json, sys
try:
    data = json.load(open('$SETTINGS'))
except Exception as e:
    sys.stderr.write(f'read error: {e}\n'); sys.exit(2)
print((data.get('bootstrap_secret') or '').strip())
")

if [[ -z "$SECRET" ]]; then
    echo "ERROR: bootstrap_secret not present in $SETTINGS" >&2
    echo "Set POOLAI_BOOTSTRAP_SECRET=<value> or write $SECRET_FILE manually." >&2
    exit 3
fi

install -d -m 700 -o root -g root "$SECRET_DIR"
umask 177
printf '%s\n' "$SECRET" > "$SECRET_FILE"
chown root:root "$SECRET_FILE"
chmod 600 "$SECRET_FILE"

echo "[OK] Wrote $SECRET_FILE (mode 600, root-owned)"
echo "[OK] Length: ${#SECRET} chars"
