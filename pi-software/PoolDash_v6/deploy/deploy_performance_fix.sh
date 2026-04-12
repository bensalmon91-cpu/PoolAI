#!/bin/bash
# ========================================
# PoolAIssistant Performance Fix Deployment
# ========================================
# Deploys database optimization fixes for slow charts and settings page

set -e

TARGET="${1:-poolaissitant@10.0.30.80}"
APP_DIR="/opt/PoolAIssistant/app"
DATA_DIR="/opt/PoolAIssistant/data"

echo "========================================"
echo "PoolAIssistant Performance Fix"
echo "========================================"
echo
echo "Target: $TARGET"
echo "Issue: Slow charts/settings page with large database"
echo "Fix: Database indexes + optimized queries"
echo

# Upload files
echo "[1/6] Uploading fixed files..."
scp pooldash_app/blueprints/main_ui.py "$TARGET:$APP_DIR/pooldash_app/blueprints/"
scp optimize_database.py "$TARGET:$APP_DIR/"
echo "✓ Files uploaded"
echo

# Restart UI service to apply code fix
echo "[2/6] Restarting web UI service..."
ssh "$TARGET" "sudo systemctl restart poolaissistant_ui"
sleep 2
echo "✓ UI service restarted"
echo

# Backup database
echo "[3/6] Backing up database..."
ssh "$TARGET" "sudo cp $DATA_DIR/pool_readings.sqlite3 $DATA_DIR/pool_readings.sqlite3.backup_$(date +%Y%m%d_%H%M%S)"
echo "✓ Database backed up"
echo

# Run database optimization
echo "[4/6] Optimizing database (this may take a few minutes)..."
echo
ssh "$TARGET" "cd $APP_DIR && sudo python3 optimize_database.py --db-path $DATA_DIR/pool_readings.sqlite3" <<EOF
yes
EOF
echo "✓ Database optimized"
echo

# Verify services
echo "[5/6] Verifying services..."
ssh "$TARGET" "sudo systemctl status poolaissistant_ui --no-pager -l | head -20"
echo

# Test settings page
echo "[6/6] Testing settings page response..."
RESPONSE_CODE=$(ssh "$TARGET" "curl -o /dev/null -s -w '%{http_code}' http://localhost:8080/settings")
if [ "$RESPONSE_CODE" = "200" ]; then
    echo "✓ Settings page accessible (HTTP $RESPONSE_CODE)"
else
    echo "⚠ Settings page returned HTTP $RESPONSE_CODE"
fi
echo

echo "========================================"
echo "Performance Fix Deployment Complete!"
echo "========================================"
echo
echo "Changes applied:"
echo "  1. Optimized settings page query (scan recent data only)"
echo "  2. Added database indexes for charts queries"
echo "  3. Updated query planner statistics"
echo
echo "Next steps:"
echo "  1. Test settings page: http://10.0.30.80/settings"
echo "  2. Test charts: Click Chlorine or pH tabs"
echo "  3. Monitor performance: journalctl -u poolaissistant_ui -f"
echo
echo "If issues persist:"
echo "  - Run: ssh $TARGET 'cd $APP_DIR && python3 optimize_database.py --vacuum'"
echo "  - Or limit data: ssh $TARGET 'cd $APP_DIR && python3 optimize_database.py --cleanup-data 90'"
echo
