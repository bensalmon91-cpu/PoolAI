#!/usr/bin/env bash
# PoolAIssistant Pi SSH hardening.
#
# Run ONCE per Pi during a maintenance visit (or over current SSH before
# rotating). Converts the Pi from "shared poolai:12345678 + NOPASSWD-ALL"
# to "SSH key-only + narrowed NOPASSWD + unique local password".
#
# Idempotent: skips steps already applied.
#
# Usage:
#   sudo ./harden_ssh.sh --pubkey /path/to/your_dev_machine.pub
#   sudo ./harden_ssh.sh --pubkey /path/to/key.pub --password 'your-random-24-char'
#
# If --password is omitted, a random 24-char password is generated and
# printed at the end (record in your password manager).
#
# After this runs:
#   * poolai user can no longer log in with password over SSH
#   * only the provided pubkey can SSH in as 'poolai'
#   * sudo NOPASSWD is narrowed to systemctl/update_check.py
#   * old passwordless sudo-ALL is removed

set -euo pipefail

USER_NAME=poolai
PUBKEY=""
NEW_PASSWORD=""
DRY_RUN=0

usage() {
    grep '^# ' "$0" | sed 's/^# //'
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pubkey)   PUBKEY="$2"; shift 2 ;;
        --password) NEW_PASSWORD="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=1; shift ;;
        -h|--help)  usage ;;
        *) echo "unknown arg: $1"; usage ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: must run as root (sudo)." >&2
    exit 1
fi
if [[ -z "$PUBKEY" || ! -f "$PUBKEY" ]]; then
    echo "ERROR: --pubkey <path-to-public-key> is required and must exist." >&2
    exit 1
fi

run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "DRY: $*"
    else
        "$@"
    fi
}

if [[ -z "$NEW_PASSWORD" ]]; then
    NEW_PASSWORD=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
    GENERATED=1
fi

echo "[1/5] Setting new local password for $USER_NAME"
if [[ $DRY_RUN -eq 0 ]]; then
    echo "$USER_NAME:$NEW_PASSWORD" | chpasswd
fi

echo "[2/5] Installing authorized_keys for $USER_NAME"
HOME_DIR=$(getent passwd "$USER_NAME" | cut -d: -f6)
SSH_DIR="$HOME_DIR/.ssh"
AUTH_FILE="$SSH_DIR/authorized_keys"
run install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "$SSH_DIR"
PUBKEY_LINE=$(cat "$PUBKEY")
if [[ $DRY_RUN -eq 0 ]]; then
    touch "$AUTH_FILE"
    if ! grep -qF "$PUBKEY_LINE" "$AUTH_FILE"; then
        echo "$PUBKEY_LINE" >> "$AUTH_FILE"
    fi
    chown "$USER_NAME:$USER_NAME" "$AUTH_FILE"
    chmod 600 "$AUTH_FILE"
fi

echo "[3/5] Disabling password auth in /etc/ssh/sshd_config"
SSHD=/etc/ssh/sshd_config
if [[ $DRY_RUN -eq 0 ]]; then
    # Idempotent edits: set PasswordAuthentication no + PermitRootLogin no + UsePAM no for sshd only.
    sed -i -E \
        -e 's/^#?PasswordAuthentication\s+.*/PasswordAuthentication no/' \
        -e 's/^#?PermitRootLogin\s+.*/PermitRootLogin no/' \
        -e 's/^#?ChallengeResponseAuthentication\s+.*/ChallengeResponseAuthentication no/' \
        "$SSHD"
    grep -q '^PasswordAuthentication ' "$SSHD" || echo 'PasswordAuthentication no' >> "$SSHD"
    grep -q '^PermitRootLogin '        "$SSHD" || echo 'PermitRootLogin no'        >> "$SSHD"
    systemctl reload ssh || systemctl reload sshd || true
fi

echo "[4/5] Narrowing sudoers NOPASSWD scope"
SUDOERS_FILE=/etc/sudoers.d/010-poolai
TMP_SUDOERS=$(mktemp)
cat > "$TMP_SUDOERS" <<EOF
# PoolAIssistant - narrowed passwordless sudo.
# Only the commands PoolAIssistant services actually need run without prompt.
# Any other sudo action (including interactive login) requires a password.
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl restart poolaissistant_ui
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl restart poolaissistant_logger
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl reload ssh
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl reload sshd
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/python3 /opt/PoolAIssistant/app/scripts/update_check.py *
$USER_NAME ALL=(root) NOPASSWD: /opt/PoolAIssistant/app/deploy/clone_prep.sh
EOF
if [[ $DRY_RUN -eq 0 ]]; then
    # visudo -c validates before we commit it
    visudo -c -f "$TMP_SUDOERS" >/dev/null
    install -m 440 -o root -g root "$TMP_SUDOERS" "$SUDOERS_FILE"
    rm -f "$TMP_SUDOERS"
    # Drop any old blanket NOPASSWD files
    for old in /etc/sudoers.d/poolai /etc/sudoers.d/poolai-nopasswd /etc/sudoers.d/000-poolai; do
        [[ -f "$old" ]] && rm -f "$old"
    done
fi

echo "[5/5] Done"
echo ""
echo "===================================================================="
echo "Hardening complete for $(hostname) ($USER_NAME)"
echo ""
if [[ ${GENERATED:-0} -eq 1 ]]; then
    echo "  Generated local password (RECORD IN YOUR PASSWORD MANAGER):"
    echo "  $NEW_PASSWORD"
    echo ""
fi
echo "  SSH:    key-only; PasswordAuthentication disabled"
echo "  sudo:   NOPASSWD now only for: systemctl (ui/logger/ssh), update_check.py, clone_prep.sh"
echo ""
echo "Test BEFORE closing your current session:"
echo "  ssh -i <your-priv-key> $USER_NAME@$(hostname -I | awk '{print $1}')"
echo "===================================================================="
