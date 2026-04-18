# Git hooks

Optional local hooks. The authoritative checks live in
`.github/workflows/` — these are for faster feedback while you're editing.

## Install (once per clone)

```bash
git config core.hooksPath .githooks
chmod +x .githooks/*
```

Undo with:

```bash
git config --unset core.hooksPath
```

## What's here

- `pre-commit` — fails the commit if `PortalAuth.php` has diverged between
  `web-portal/php_deploy/includes/` and `web-portal/poolai_deploy/includes/`,
  but only when one of those copies is in the commit. Mirrors the CI check
  in `.github/workflows/drift-guard.yml`.
