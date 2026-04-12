#!/bin/bash
# Quick script to enable SSH on Raspberry Pi
# Run with: sudo ./enable_ssh.sh

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

echo "Enabling SSH..."
systemctl enable ssh
systemctl start ssh

# Get IP address
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "SSH is now enabled!"
echo "Connect with: ssh poolai@$IP"
echo ""
