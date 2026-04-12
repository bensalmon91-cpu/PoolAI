#!/bin/bash
#
# ensure_ports.sh - Ensure web UI ports are accessible
#
# This script makes sure port 80 is open for the web UI.
# It works with UFW, iptables, or no firewall at all.
# Run at boot and after updates to ensure accessibility.
#

set -u

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Required ports
WEB_PORT=80
SSH_PORT=22

# Function to check if a port is accessible locally
check_port() {
    local port=$1
    if command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | grep -q ":${port} "
    elif command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | grep -q ":${port} "
    else
        # Assume it's fine if we can't check
        return 0
    fi
}

# Function to configure UFW
configure_ufw() {
    if ! command -v ufw &>/dev/null; then
        return 1
    fi

    # Check if UFW is active
    if ! ufw status 2>/dev/null | grep -q "Status: active"; then
        log "UFW is not active, skipping UFW configuration"
        return 1
    fi

    log "Configuring UFW..."

    # Allow port 80 (HTTP)
    ufw allow 80/tcp 2>/dev/null && log "  UFW: Allowed port 80/tcp"

    # Allow port 22 (SSH)
    ufw allow 22/tcp 2>/dev/null && log "  UFW: Allowed port 22/tcp"

    # Remove old port 8080 rule if it exists
    ufw delete allow 8080/tcp 2>/dev/null && log "  UFW: Removed port 8080/tcp rule"

    # Reload UFW
    ufw reload 2>/dev/null

    return 0
}

# Function to configure iptables directly
configure_iptables() {
    if ! command -v iptables &>/dev/null; then
        log "iptables not found"
        return 1
    fi

    log "Configuring iptables..."

    # Check if there's an INPUT chain with DROP policy or any blocking rules
    local has_firewall=false
    if iptables -L INPUT -n 2>/dev/null | grep -qE "(DROP|REJECT)"; then
        has_firewall=true
    fi

    if [ "$has_firewall" = false ]; then
        log "  No blocking iptables rules found, skipping"
        return 0
    fi

    # Allow port 80 (HTTP) - insert at top of INPUT chain
    if ! iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
        iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT 2>/dev/null && log "  iptables: Allowed port 80"
    fi

    # Allow port 22 (SSH)
    if ! iptables -C INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null; then
        iptables -I INPUT 1 -p tcp --dport 22 -j ACCEPT 2>/dev/null && log "  iptables: Allowed port 22"
    fi

    # Allow established connections
    if ! iptables -C INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
        iptables -I INPUT 1 -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null
    fi

    # Save iptables rules if iptables-persistent is installed
    if command -v netfilter-persistent &>/dev/null; then
        netfilter-persistent save 2>/dev/null && log "  iptables: Rules saved"
    elif [ -f /etc/iptables/rules.v4 ]; then
        iptables-save > /etc/iptables/rules.v4 2>/dev/null && log "  iptables: Rules saved to /etc/iptables/rules.v4"
    fi

    return 0
}

# Function to configure nftables
configure_nftables() {
    if ! command -v nft &>/dev/null; then
        return 1
    fi

    # Check if nftables has any rules
    if ! nft list ruleset 2>/dev/null | grep -q "chain input"; then
        log "nftables not configured with input chain, skipping"
        return 1
    fi

    log "Configuring nftables..."

    # Add rules to allow ports (this is a simplified approach)
    # In practice, you'd need to know the table/chain structure
    nft add rule inet filter input tcp dport 80 accept 2>/dev/null && log "  nftables: Allowed port 80"
    nft add rule inet filter input tcp dport 22 accept 2>/dev/null && log "  nftables: Allowed port 22"

    return 0
}

# Function to disable any restrictive firewall
disable_restrictive_firewall() {
    log "Checking for restrictive firewall configurations..."

    # Check if UFW is blocking everything
    if command -v ufw &>/dev/null; then
        local default_policy=$(ufw status verbose 2>/dev/null | grep "Default:" | head -1)
        if echo "$default_policy" | grep -q "deny (incoming)"; then
            log "  UFW default policy is deny - ensuring ports are allowed"
            ufw allow 80/tcp 2>/dev/null
            ufw allow 22/tcp 2>/dev/null
        fi
    fi
}

# Main function
main() {
    log "======================================"
    log "PoolAIssistant Port Configuration"
    log "======================================"

    # Try UFW first (most common on Raspberry Pi OS)
    if configure_ufw; then
        log "UFW configuration complete"
    fi

    # Try iptables as fallback
    configure_iptables

    # Try nftables if available
    configure_nftables 2>/dev/null

    # Final check - disable restrictive defaults
    disable_restrictive_firewall

    # Verify ports are listening
    log "Verifying services..."
    sleep 2

    if check_port $WEB_PORT; then
        log "  Port $WEB_PORT: Service listening"
    else
        log "  Port $WEB_PORT: No service listening (Flask may not be started yet)"
    fi

    if check_port $SSH_PORT; then
        log "  Port $SSH_PORT: Service listening"
    else
        log "  Port $SSH_PORT: No service listening"
    fi

    log "Port configuration complete"
    log "======================================"
}

# Run main
main "$@"
