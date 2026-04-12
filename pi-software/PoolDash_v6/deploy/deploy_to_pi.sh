#!/bin/bash
# ========================================
# PoolAIssistant v6.1.1 - Deploy to Pi
# ========================================

# Accept target as parameter or environment variable
# Usage: ./deploy_to_pi.sh [user@host]
# Or set environment: DEPLOY_TARGET=poolaissistant@10.0.30.80 ./deploy_to_pi.sh

if [ -n "$1" ]; then
    TARGET="$1"
elif [ -n "$DEPLOY_TARGET" ]; then
    TARGET="$DEPLOY_TARGET"
else
    TARGET="poolai@poolai.local"
fi

# Parse user@host
if [[ "$TARGET" =~ ^([^@]+)@([^@]+)$ ]]; then
    PI_USER="${BASH_REMATCH[1]}"
    PI_HOST="${BASH_REMATCH[2]}"
else
    echo "ERROR: Invalid target format. Use: user@host"
    echo "Example: ./deploy_to_pi.sh poolai@poolai.local"
    exit 1
fi

PI_TARGET="/home/$PI_USER/PoolDash_v6"

echo "========================================"
echo "PoolAIssistant Deployment Script"
echo "========================================"
echo
echo "Target: $PI_USER@$PI_HOST:$PI_TARGET"
echo

# Test connection first
echo "[1/4] Testing connection to Pi..."
if ! ping -c 1 -W 2 "$PI_HOST" &>/dev/null; then
    echo "ERROR: Cannot reach Pi at $PI_HOST"
    echo "Please check network connection and try again"
    exit 1
fi
echo "OK - Pi is reachable"
echo

# Check SSH connectivity
echo "[2/4] Testing SSH connection..."
if ! ssh -o ConnectTimeout=5 "$PI_USER@$PI_HOST" "echo SSH OK" &>/dev/null; then
    echo "ERROR: Cannot SSH to $PI_USER@$PI_HOST"
    echo "Please check SSH keys or credentials"
    exit 1
fi
echo "OK - SSH connection working"
echo

# Transfer files
echo "[3/4] Transferring files to Pi..."
echo "This may take a moment..."
if ! scp -r \
    *.py \
    requirements.txt \
    README.md \
    OPTIMIZATION_SUMMARY.md \
    INSTALL.txt \
    setup_pooldash.sh \
    pooldash_app \
    scripts \
    "$PI_USER@$PI_HOST:$PI_TARGET/"; then
    echo "ERROR: File transfer failed"
    exit 1
fi
echo "OK - Files transferred"
echo

# Install on Pi
echo "[4/4] Installing on Pi..."
if ! ssh "$PI_USER@$PI_HOST" "cd $PI_TARGET && bash setup_pooldash.sh"; then
    echo "WARNING: Installation script returned an error"
    echo "Check the output above for details"
    echo
    echo "You may need to run manually:"
    echo "  ssh $PI_USER@$PI_HOST"
    echo "  cd $PI_TARGET"
    echo "  sudo bash setup_pooldash.sh"
    exit 1
fi

echo
echo "========================================"
echo "Deployment Complete!"
echo "========================================"
echo
echo "Next steps:"
echo "1. Check services are running:"
echo "   ssh $PI_USER@$PI_HOST \"sudo systemctl status poolaissistant_logger\""
echo "   ssh $PI_USER@$PI_HOST \"sudo systemctl status poolaissistant_ui\""
echo
echo "2. View logs:"
echo "   ssh $PI_USER@$PI_HOST \"journalctl -u poolaissistant_logger -f\""
echo
echo "3. Access web UI:"
echo "   http://$PI_HOST:8080"
echo
echo "4. Configure controllers in Settings if needed"
echo
