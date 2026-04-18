#!/usr/bin/env python3
"""
PoolAIssistant unified deployer.

Replaces the accumulated ad-hoc deploy_*.php scripts with a single tool that:

 * reads a declarative manifest (deploy.manifest.json) listing every file to
   ship to each target (admin backend, customer portal, etc);
 * deploys via the right mechanism for each target (FTP direct upload for
   anything the FTP user can reach, or a generated nowdoc-installer PHP for
   paths that FTP is chrooted out of);
 * records SHA256 of every deployed file to deploy.lock.json;
 * exposes a `verify` subcommand that hits a server-side endpoint and reports
   drift so the "auth.php went stale without anyone noticing" failure mode
   cannot recur silently.

Zero-dependency: stdlib only (ftplib, urllib, hashlib, json, ssl).

Usage:
    python deploy.py list                    # show planned files
    python deploy.py deploy                  # deploy all targets
    python deploy.py deploy --target admin-backend
    python deploy.py deploy --dry-run
    python deploy.py verify                  # compare live vs lockfile
    python deploy.py verify --target admin-backend

Credentials (never in repo; read from env):
    POOLAI_FTP_HOST, POOLAI_FTP_USER, POOLAI_FTP_PASS
    POOLAI_ADMIN_SESSION  (mod_admin_session cookie value, for verify)
"""

from __future__ import annotations

import argparse
import ftplib
import glob
import hashlib
import io
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "deploy.manifest.json"
LOCKFILE = ROOT / "deploy.lock.json"
NOWDOC_MARKER = "POOLAI_DEPLOY_FILE_END_8F3N"


def fatal(msg: str, code: int = 1) -> "None":
    sys.stderr.write(f"[FATAL] {msg}\n")
    sys.exit(code)


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class FileSpec:
    src: Path
    dest: str  # relative path on server (no leading slash)

    @property
    def sha(self) -> str:
        return sha256_bytes(self.src.read_bytes())


def load_manifest() -> dict:
    if not MANIFEST.exists():
        fatal(f"{MANIFEST.name} not found. Create it from deploy.manifest.example.json.")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def expand_target(target_name: str, target: dict) -> list[FileSpec]:
    """Resolve a target's files/globs into concrete FileSpec entries."""
    files: list[FileSpec] = []
    entries = target.get("files", [])
    for entry in entries:
        if "glob" in entry:
            pattern = entry["glob"]
            dest_prefix = entry.get("dest_prefix", "").strip("/")
            src_prefix = entry.get("src_prefix", "").strip("/")
            matches = sorted(
                p for p in (ROOT / pattern).parent.glob(Path(pattern).name)
                if p.is_file()
            ) if "**" not in pattern and "*" not in pattern else sorted(
                p for p in ROOT.glob(pattern) if p.is_file()
            )
            for m in matches:
                rel = m.relative_to(ROOT)
                rel_in_src = str(rel.as_posix())
                if src_prefix and rel_in_src.startswith(src_prefix + "/"):
                    rel_in_src = rel_in_src[len(src_prefix) + 1:]
                dest = rel_in_src
                if dest_prefix:
                    dest = f"{dest_prefix}/{dest}"
                files.append(FileSpec(src=m, dest=dest))
        elif "src" in entry and "dest" in entry:
            src = ROOT / entry["src"]
            if not src.is_file():
                fatal(f"[{target_name}] missing source file: {entry['src']}")
            files.append(FileSpec(src=src, dest=entry["dest"].strip("/")))
        else:
            fatal(f"[{target_name}] manifest entry must have 'src'+'dest' or 'glob'")
    # de-dupe on dest, keeping first occurrence
    seen: set[str] = set()
    unique: list[FileSpec] = []
    for f in files:
        if f.dest in seen:
            continue
        seen.add(f.dest)
        unique.append(f)
    return unique


# --------------------------------------------------------------------------
# FTP helpers
# --------------------------------------------------------------------------

def _ftp_creds() -> tuple[str, str, str]:
    host = os.environ.get("POOLAI_FTP_HOST", "").strip()
    user = os.environ.get("POOLAI_FTP_USER", "").strip()
    pw = os.environ.get("POOLAI_FTP_PASS", "").strip()
    if not host or not user or not pw:
        fatal("FTP credentials missing. Set POOLAI_FTP_HOST / POOLAI_FTP_USER / POOLAI_FTP_PASS.")
    return host, user, pw


def ftp_connect() -> ftplib.FTP_TLS:
    host, user, pw = _ftp_creds()
    ctx = ssl.create_default_context()
    # Hostinger's cert hostname doesn't always match the FTP host - skip match
    # since we authenticate with user/password and are uploading, not reading
    # untrusted data. This matches the existing deploy scripts' behaviour.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ftp = ftplib.FTP_TLS(host, user, pw, context=ctx, timeout=60)
    ftp.prot_p()
    return ftp


def ftp_ensure_dir(ftp: ftplib.FTP_TLS, path: str) -> None:
    """Create nested directories, tolerating 'already exists'."""
    parts = [p for p in path.split("/") if p]
    cur = ""
    for p in parts:
        cur = f"{cur}/{p}" if cur else p
        try:
            ftp.mkd(cur)
        except ftplib.error_perm as e:
            if "exists" in str(e).lower() or "550" in str(e):
                continue
            raise


def ftp_put(ftp: ftplib.FTP_TLS, local: Path, remote: str) -> None:
    remote_dir = "/".join(remote.split("/")[:-1])
    if remote_dir:
        ftp_ensure_dir(ftp, remote_dir)
    with local.open("rb") as f:
        ftp.storbinary(f"STOR {remote}", f)


# --------------------------------------------------------------------------
# PHP installer (nowdoc bundle) - mirrors build_staff_installer.py
# --------------------------------------------------------------------------

PHP_INSTALLER_PRELUDE = r"""<?php
/**
 * PoolAIssistant unified deploy bundle (generated by deploy.py).
 *
 * This file is uploaded to the customer portal FTP root and then invoked via
 * HTTPS. It writes bundled files to the admin backend path and self-deletes.
 * Do not commit the generated bundle to the repo - it is disposable.
 */
error_reporting(E_ALL);
ini_set('display_errors', 1);
set_time_limit(300);
header('Content-Type: text/plain; charset=utf-8');

$targetBase = '__SERVER_BASE_PATH__';

echo "PoolAIssistant deploy bundle\n";
echo "============================\n\n";

if (!is_dir($targetBase)) {
    if (!mkdir($targetBase, 0755, true)) {
        die("[ERROR] Cannot create $targetBase\n");
    }
    echo "[OK] Created target base\n";
}

$files = [];
"""

PHP_INSTALLER_POSTLUDE = r"""
$written = 0;
$failed = [];
foreach ($files as $rel => $content) {
    $full = rtrim($targetBase, '/') . '/' . ltrim($rel, '/');
    $dir = dirname($full);
    if (!is_dir($dir) && !mkdir($dir, 0755, true)) {
        $failed[] = "$rel (mkdir)";
        continue;
    }
    $bytes = file_put_contents($full, $content);
    if ($bytes === false) { $failed[] = $rel; continue; }
    @chmod($full, 0644);
    echo sprintf("[OK] %-48s %7d bytes\n", $rel, $bytes);
    $written++;
}

echo "\nDeployed $written file(s); " . count($failed) . " failure(s).\n";
if ($failed) { echo "Failed: " . implode(', ', $failed) . "\n"; }
else {
    echo "Cleaning up bundle...\n";
    @unlink(__FILE__);
    echo "[OK] Bundle self-deleted.\n";
}
"""


def build_php_bundle(server_base_path: str, files: list[FileSpec]) -> bytes:
    pieces = [PHP_INSTALLER_PRELUDE.replace("__SERVER_BASE_PATH__", server_base_path)]
    for fs in files:
        content = fs.src.read_text(encoding="utf-8", errors="replace") \
            if _looks_text(fs.src) else ""
        if not _looks_text(fs.src):
            # Binary files: inline as base64-decoded write instead of heredoc.
            raw = fs.src.read_bytes()
            b64 = _b64(raw)
            rel_php = _php_str(fs.dest)
            pieces.append(f"$files[{rel_php}] = base64_decode({_php_str(b64)});\n")
            continue
        if NOWDOC_MARKER in content:
            fatal(f"nowdoc marker collision in {fs.src}")
        rel_php = _php_str(fs.dest)
        pieces.append(f"$files[{rel_php}] = <<<'{NOWDOC_MARKER}'\n{content}\n{NOWDOC_MARKER};\n\n")
    pieces.append(PHP_INSTALLER_POSTLUDE)
    return "".join(pieces).encode("utf-8")


def _looks_text(path: Path) -> bool:
    suffix = path.suffix.lower()
    text_exts = {
        ".php", ".html", ".htm", ".css", ".js", ".json", ".md", ".txt",
        ".yml", ".yaml", ".sql", ".env", ".example", ".sh", ".py",
    }
    if suffix in text_exts:
        return True
    try:
        chunk = path.read_bytes()[:1024]
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    return True


def _b64(raw: bytes) -> str:
    import base64
    return base64.b64encode(raw).decode("ascii")


def _php_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


# --------------------------------------------------------------------------
# Deploy per target
# --------------------------------------------------------------------------

def deploy_ftp_target(target_name: str, target: dict, files: list[FileSpec], dry_run: bool) -> dict:
    """Direct FTP upload; FTP user must have access to the target path."""
    ftp_base_subdir = target.get("ftp_base_subdir", "").strip("/")
    if dry_run:
        print(f"[DRY] {target_name}: FTP {len(files)} file(s) to /{ftp_base_subdir}/")
        for fs in files:
            rel = f"{ftp_base_subdir}/{fs.dest}" if ftp_base_subdir else fs.dest
            print(f"       {fs.src.relative_to(ROOT)} -> {rel}")
        return {f.dest: f.sha for f in files}
    ftp = ftp_connect()
    try:
        for fs in files:
            remote = f"{ftp_base_subdir}/{fs.dest}" if ftp_base_subdir else fs.dest
            ftp_put(ftp, fs.src, remote)
            ok(f"{target_name}: uploaded {fs.dest}")
    finally:
        try: ftp.quit()
        except Exception: ftp.close()
    return {f.dest: f.sha for f in files}


def deploy_php_installer_target(target_name: str, target: dict, files: list[FileSpec], dry_run: bool) -> dict:
    """Write a PHP installer, FTP it to the installer-host, HTTPS run it."""
    server_base = target["server_base_path"].rstrip("/")
    bundle = build_php_bundle(server_base, files)
    bundle_name = target.get("installer_filename", "_deploy_bundle.php")
    run_url = target["installer_run_url"]
    ftp_filename = target.get("installer_ftp_path", bundle_name)

    if dry_run:
        print(f"[DRY] {target_name}: would write {len(bundle)}-byte PHP installer to FTP /{ftp_filename}, run {run_url}, deploy {len(files)} file(s)")
        for fs in files:
            print(f"       {fs.src.relative_to(ROOT)} -> {server_base}/{fs.dest}")
        return {f.dest: f.sha for f in files}

    # FTP upload the installer
    ftp = ftp_connect()
    try:
        ftp_ensure_dir(ftp, "/".join(ftp_filename.split("/")[:-1]))
        ftp.storbinary(f"STOR {ftp_filename}", io.BytesIO(bundle))
        ok(f"{target_name}: uploaded installer ({len(bundle)} bytes)")
    finally:
        try: ftp.quit()
        except Exception: ftp.close()

    # Execute via HTTPS GET
    print(f"[..] {target_name}: running {run_url}")
    req = urllib.request.Request(run_url)
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    print(body)
    if "Bundle self-deleted" not in body and "self-deleted" not in body:
        fatal(f"{target_name}: installer did not self-delete; check manually: {run_url}")
    ok(f"{target_name}: deployed {len(files)} file(s)")
    return {f.dest: f.sha for f in files}


# --------------------------------------------------------------------------
# Verify (drift detection)
# --------------------------------------------------------------------------

def verify_target(target_name: str, target: dict, files: list[FileSpec]) -> int:
    verify_url = target.get("verify_url")
    if not verify_url:
        warn(f"{target_name}: no verify_url configured, skipping")
        return 0
    session_cookie = os.environ.get("POOLAI_ADMIN_SESSION", "").strip()
    if not session_cookie:
        fatal("POOLAI_ADMIN_SESSION env var required for verify (the mod_admin_session cookie value)")
    cookie_name = target.get("session_cookie_name", "mod_admin_session")

    payload = json.dumps({"paths": [fs.dest for fs in files]}).encode("utf-8")
    req = urllib.request.Request(
        verify_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cookie": f"{cookie_name}={session_cookie}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        fatal(f"{target_name}: verify HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}")

    server_sha = body.get("sha256", {}) if isinstance(body, dict) else {}
    if not server_sha:
        fatal(f"{target_name}: verify endpoint returned no sha256 map: {body}")

    drifted = 0
    missing = 0
    for fs in files:
        s = server_sha.get(fs.dest)
        if s is None:
            print(f"[MISSING] {target_name}: {fs.dest}")
            missing += 1
        elif s != fs.sha:
            print(f"[DRIFT]   {target_name}: {fs.dest}")
            print(f"            local={fs.sha}")
            print(f"            server={s}")
            drifted += 1
    if drifted == 0 and missing == 0:
        ok(f"{target_name}: {len(files)} file(s) match (no drift)")
    else:
        print(f"[!!] {target_name}: {drifted} drifted, {missing} missing")
    return drifted + missing


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    for name, target in manifest["targets"].items():
        if args.target and name != args.target:
            continue
        files = expand_target(name, target)
        print(f"\n=== {name} ({len(files)} file{'s' if len(files) != 1 else ''}) ===")
        print(f"  method: {target.get('deploy_method')}")
        print(f"  base:   {target.get('server_base_path', '-')}")
        for fs in files:
            print(f"    {fs.src.relative_to(ROOT)}  ->  {fs.dest}")


def cmd_deploy(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    lock: dict = {}
    if LOCKFILE.exists():
        lock = json.loads(LOCKFILE.read_text(encoding="utf-8"))

    for name, target in manifest["targets"].items():
        if args.target and name != args.target:
            continue
        files = expand_target(name, target)
        method = target.get("deploy_method")
        print(f"\n>>> Deploying target: {name}  ({method}, {len(files)} files)")
        if method == "ftp":
            result = deploy_ftp_target(name, target, files, args.dry_run)
        elif method == "php_installer":
            result = deploy_php_installer_target(name, target, files, args.dry_run)
        else:
            fatal(f"unknown deploy_method '{method}' for target {name}")
        lock[name] = {
            "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": result,
        }

    if not args.dry_run:
        LOCKFILE.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        ok(f"lockfile updated: {LOCKFILE.name}")


def cmd_verify(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    total = 0
    for name, target in manifest["targets"].items():
        if args.target and name != args.target:
            continue
        files = expand_target(name, target)
        total += verify_target(name, target, files)
    if total:
        sys.exit(2)


def main() -> None:
    p = argparse.ArgumentParser(prog="deploy.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s_list = sub.add_parser("list", help="show planned files per target")
    s_list.add_argument("--target", help="only this target")
    s_list.set_defaults(func=cmd_list)

    s_deploy = sub.add_parser("deploy", help="deploy all targets")
    s_deploy.add_argument("--target", help="deploy only this target")
    s_deploy.add_argument("--dry-run", action="store_true", help="show plan without uploading")
    s_deploy.set_defaults(func=cmd_deploy)

    s_verify = sub.add_parser("verify", help="compare deployed files vs local")
    s_verify.add_argument("--target", help="verify only this target")
    s_verify.set_defaults(func=cmd_verify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
