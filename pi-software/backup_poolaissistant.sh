#!/bin/bash
# PoolAIssistant Backup Script - Lightweight Version

BACKUP_DIR="${1:-/home/poolaissistant/backups}"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_NAME="poolaissistant_backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "=== PoolAIssistant Backup ==="
echo ""

echo "[1/4] Creating backup archive..."
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}" \
    --exclude="venv" \
    --exclude="*.pyc" \
    --exclude="__pycache__" \
    --exclude="logs/*.log" \
    --exclude="data/chunks/*.gz" \
    --exclude="data/pool_readings.sqlite3*" \
    --exclude="data/*.sqlite3-wal" \
    --exclude="data/*.sqlite3-shm" \
    -C /opt PoolAIssistant \
    -C /home/poolaissistant chunk_manager.py health_reporter.py backup_poolaissistant.sh 2>/dev/null

echo "[2/4] Saving crontab..."
crontab -l > "${BACKUP_DIR}/crontab_${TIMESTAMP}.txt" 2>/dev/null || true

echo "[3/4] Saving system info..."
cat > "${BACKUP_DIR}/sysinfo_${TIMESTAMP}.txt" << EOF
Backup: $(date)
Host: $(hostname)
IP: $(hostname -I | awk "{print \$1}")
OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d\" -f2)
DB Size: $(du -sh /opt/PoolAIssistant/data/pool_readings.sqlite3 2>/dev/null | cut -f1)
EOF

echo "[4/4] Cleanup old backups..."
ls -t "${BACKUP_DIR}"/poolaissistant_backup_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm -f

SIZE=$(ls -lh "${BACKUP_DIR}/${BACKUP_NAME}" | awk "{print \$5}")
echo ""
echo "=== Backup Complete ==="
echo "File: ${BACKUP_DIR}/${BACKUP_NAME}"
echo "Size: ${SIZE}"
echo ""
echo "Note: Main database (15GB) excluded - synced via chunk uploads"
