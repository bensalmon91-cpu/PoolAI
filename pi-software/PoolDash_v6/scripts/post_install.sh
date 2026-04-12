#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/PoolAIssistant/app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="/etc/PoolAIssistant/poolaissistant.env"

if [ ! -d "$APP_DIR" ]; then
  echo "ERROR: $APP_DIR not found."
  echo "Copy this repo to $APP_DIR before running post_install.sh."
  exit 1
fi

echo "== PoolAIssistant post-install =="

sudo chmod +x "$SCRIPT_DIR/setup_pi.sh" "$SCRIPT_DIR/poolaissistant_ap_manager.sh"

echo "Running setup_pi.sh..."
sudo bash "$SCRIPT_DIR/setup_pi.sh"

if [ ! -f "$ENV_FILE" ]; then
  sudo cp "$APP_DIR/scripts/poolaissistant.env.example" "$ENV_FILE"
fi

if ! grep -q '^POOLS_JSON=' "$ENV_FILE"; then
  echo "POOLS_JSON is not set."
  read -r -p "Configure pools now? (y/N): " do_setup
  if [[ "$do_setup" =~ ^[Yy]$ ]]; then
    read -r -p "How many pools? " pool_count
    if [[ ! "$pool_count" =~ ^[0-9]+$ ]] || [ "$pool_count" -le 0 ]; then
      echo "Invalid pool count. Skipping POOLS_JSON setup."
    else
      tmp_file="$(mktemp)"
      read -r -p "Verify connectivity (ping + Modbus TCP connect)? (y/N): " do_check
      for i in $(seq 1 "$pool_count"); do
        read -r -p "Pool $i name: " pool_name
        read -r -p "Pool $i host (IP or hostname): " pool_host
        read -r -p "Pool $i port [502]: " pool_port
        read -r -p "Pool $i unit [1]: " pool_unit
        pool_port="${pool_port:-502}"
        pool_unit="${pool_unit:-1}"
        echo "$pool_name|$pool_host|$pool_port|$pool_unit" >> "$tmp_file"
        if [[ "$do_check" =~ ^[Yy]$ ]]; then
          if ping -c 1 -W 2 "$pool_host" >/dev/null 2>&1; then
            echo "Ping OK: $pool_host"
          else
            echo "Ping FAILED: $pool_host"
          fi
          if timeout 3 bash -lc ">/dev/tcp/$pool_host/$pool_port" >/dev/null 2>&1; then
            echo "Modbus TCP OK: $pool_host:$pool_port"
          else
            echo "Modbus TCP FAILED: $pool_host:$pool_port"
          fi
        fi
      done
      pools_json="$(python3 - <<'PY'
import json, sys
items = {}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    name, host, port, unit = line.split("|", 3)
    if not name or not host:
        continue
    try:
        port = int(port)
    except Exception:
        port = 502
    try:
        unit = int(unit)
    except Exception:
        unit = 1
    items[name] = {"host": host, "port": port, "unit": unit}
print(json.dumps(items, separators=(",", ":")))
PY
      < "$tmp_file")"
      rm -f "$tmp_file"
      if [ -n "$pools_json" ] && [ "$pools_json" != "{}" ]; then
        echo "POOLS_JSON=$pools_json" | sudo tee -a "$ENV_FILE" >/dev/null
      else
        echo "WARNING: POOLS_JSON not set (no valid pools entered)."
      fi
    fi
  else
    echo "WARNING: POOLS_JSON is still not set in $ENV_FILE (logger will not start)."
  fi
fi

echo "Starting services..."
sudo systemctl start poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager

echo "Post-install complete."
