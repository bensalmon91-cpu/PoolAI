# Per-device SSH hardening runbook

**Applies to:** every deployed PoolAIssistant Pi currently on `poolai:12345678` + `NOPASSWD ALL`.

**Goal:** switch the fleet to SSH key-only, unique local passwords, narrowed sudo.

## Before you start (one time)

1. Generate an Ed25519 keypair on your admin machine *if you don't already have one*:

    ```bash
    ssh-keygen -t ed25519 -f ~/.ssh/poolai_admin -C "poolai-admin"
    ```

2. Decide where the per-device local passwords are recorded. Options:
   - 1Password / Bitwarden vault, one entry per device keyed by `device_uuid` or site name.
   - A CSV maintained offline and encrypted.

## Per-device procedure

For each Pi (do **one at a time** and verify SSH works each time before moving to the next):

### 1. Current SSH session

Open a terminal and SSH in with the **old** credentials:

```bash
ssh poolai@<pi-ip>           # password: 12345678
```

**Keep this window open** until the new access is verified.

### 2. Copy the hardener script to the Pi

From your admin machine:

```bash
scp pi-software/PoolDash_v6/deploy/harden_ssh.sh poolai@<pi-ip>:/tmp/
scp ~/.ssh/poolai_admin.pub poolai@<pi-ip>:/tmp/admin_pub.key
```

### 3. Run the hardener

Back in the SSH session on the Pi:

```bash
sudo bash /tmp/harden_ssh.sh --pubkey /tmp/admin_pub.key
```

If you want to supply a specific password instead of auto-generating:

```bash
sudo bash /tmp/harden_ssh.sh --pubkey /tmp/admin_pub.key --password 'your-24-char-random'
```

The script:

- Sets a new local password for `poolai`.
- Installs your pubkey to `~poolai/.ssh/authorized_keys`.
- Disables password auth in `sshd_config` and reloads SSH.
- Replaces the blanket `NOPASSWD ALL` with a narrowed allowlist (only
  the systemctl reloads the Pi services need + `update_check.py` +
  `clone_prep.sh`).

Record the printed local password somewhere safe.

### 4. Verify **from a new terminal** — do not close the old one yet

```bash
ssh -i ~/.ssh/poolai_admin poolai@<pi-ip>
```

If it works: clean up the original session + delete `/tmp/admin_pub.key`:

```bash
rm /tmp/admin_pub.key /tmp/harden_ssh.sh
exit
```

### 5. If something goes wrong

Because you kept the original session open, you still have sudo there.
Possible fixes:

- Re-run `harden_ssh.sh` to re-apply.
- Revert via `sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config && systemctl reload ssh` and restore the old sudoers file from `/etc/sudoers.d/`.

If you **lose all access** (closed the old session before testing the new): physical keyboard + display on the Pi is the only recovery.

## Rollout ordering

- Do the least-important / test Pi first.
- Wait 24 hours; confirm auto-update, cloud uploads, and AI heartbeat still work with the narrowed NOPASSWD list.
- Then roll the rest.

## Post-rollout cleanup

When every deployed Pi has been hardened:

1. Update `pi-software/CLAUDE.md` and `pi-software/PoolDash_v6/CLAUDE.md` SSH
   blocks so they no longer mention the `12345678` password.
2. Bake `harden_ssh.sh` invocation into `clone_prep.sh` / first-boot so new
   Pis come up SSH-locked from day one (needs pubkey provisioned via a
   separate channel — e.g., cloud-init or the Pi's setup wizard).
