#!/usr/bin/env python3
"""
Sign a PoolAIssistant update tarball with an Ed25519 private key.

Usage:
    python sign_update.py --tarball path/to/update-v6.8.10.tar.gz \\
                           --key ~/.ssh/poolai_update_signing_key

Produces path/to/update-v6.8.10.tar.gz.sig (raw Ed25519 signature, 64 bytes).
The companion public key must already be committed to
pi-software/PoolDash_v6/trust/update_signing_key.pub for Pis to trust it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--tarball", required=True, type=Path, help="path to the update tarball")
    p.add_argument("--key", required=True, type=Path, help="path to the Ed25519 private key (OpenSSH format, unencrypted)")
    p.add_argument("--out", type=Path, default=None, help="signature output path (default: <tarball>.sig)")
    args = p.parse_args()

    if not args.tarball.is_file():
        sys.exit(f"[ERROR] tarball not found: {args.tarball}")
    if not args.key.is_file():
        sys.exit(f"[ERROR] key not found: {args.key}")

    try:
        from cryptography.hazmat.primitives.serialization import load_ssh_private_key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        sys.exit("[ERROR] missing dependency: pip install cryptography")

    key_bytes = args.key.read_bytes()
    try:
        privkey = load_ssh_private_key(key_bytes, password=None)
    except Exception as e:
        sys.exit(f"[ERROR] cannot load key (is it encrypted? ssh-keygen -p -N '' -f key): {e}")

    if not isinstance(privkey, Ed25519PrivateKey):
        sys.exit("[ERROR] key is not Ed25519")

    data = args.tarball.read_bytes()
    sig = privkey.sign(data)
    out = args.out or Path(str(args.tarball) + ".sig")
    out.write_bytes(sig)
    print(f"[OK] wrote {out} ({len(sig)} bytes)")
    print(f"      Upload alongside the tarball so Pis can fetch it at")
    print(f"      <download_url>.sig during update_check.download_update.")


if __name__ == "__main__":
    main()
