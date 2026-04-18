# Update signing trust

This directory holds the **public** half of the Ed25519 keypair that signs
PoolAIssistant update tarballs. It is committed so every installed copy of
the Pi software ships with the key baked in - an attacker who controls the
update server alone cannot push code; they would also have to possess the
private signing key, which never lives on the server.

## Files

- `update_signing_key.pub` - Ed25519 public key in OpenSSH or PEM format.
  **This is the one the Pi trusts.** Checked in.
- `require_signature` (optional) - if this marker file exists, Pis refuse
  to install unsigned updates (overrides the `REQUIRE_SIGNATURE_DEFAULT`
  flag in `update_check.py`). Drop it in once every published update has
  been signed.
- `update_signing_key` - the **private** key. NEVER commit; keep offline
  (password manager, hardware token, offline laptop). Only needed on the
  machine that publishes updates.

## Generate the keypair (one-time)

```bash
# On your dev machine, once per signing-key rotation.
ssh-keygen -t ed25519 -f update_signing_key -C "poolai-update-signing-$(date +%Y%m%d)" -N ""
# Copy the public key into the repo:
cp update_signing_key.pub pi-software/PoolDash_v6/trust/update_signing_key.pub
# Move the private key somewhere safe (OUTSIDE the repo) and commit the pub:
git add pi-software/PoolDash_v6/trust/update_signing_key.pub
git commit -m "trust: rotate update-signing public key"
```

## Sign a new update tarball

See `../scripts/sign_update.py`. It accepts a tarball + path to the private
key and emits `<tarball>.sig` next to it; `deploy.py` then uploads both.

## Rotation

Rotating the key requires rolling out a new Pi release that contains the
new public key, before revoking the old one. The simplest safe path is:

1. Generate new keypair.
2. Ship a release that includes **both** old and new public keys - extend
   `update_check.py` to try each key.
3. Once fleet is on that release, sign new updates with the new key only.
4. A release later, drop the old key.

Do not simply swap the key in place - Pis on the old release would reject
the first signed update with the new key.
