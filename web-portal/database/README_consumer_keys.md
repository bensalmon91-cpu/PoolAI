# Consumer Keys — deployment guide

This file documents the **manual server-side steps** to roll out the
`consumer_keys` auth model (B2 in `brain/IMPROVEMENTS.md`).

The repo-side artifacts are already in place:

| File | What it is |
|---|---|
| `web-portal/database/schema_consumer_keys.sql` | Idempotent DDL for the new table |
| `web-portal/php_deploy/includes/api_helpers.php` | New `authenticateConsumerKey($pdo, $perm)` function |
| `.env.example` | `CONSUMER_KEY` placeholder for clients that opt in |

The reason these rollout steps are manual is that **the existing chunks-API
PHP files** (`api/list_chunks.php`, `api/chunks_status.php`,
`api/download_chunks.php`, `api/upload_chunk.php`) are **not in this repo**.
They live only on the live server, copied between domains via the
one-shot script at `brain/deploy/install_chunks_api.php`. To finish B2,
those files need to be pulled into the repo so the auth swap can be
reviewed in version control.

---

## Step 1 — Create the table on Hostinger MySQL

```sql
-- Run from phpMyAdmin or via the MySQL CLI on the Hostinger box.
SOURCE schema_consumer_keys.sql;
-- ...or paste the contents directly.
```

Verify:

```sql
SHOW CREATE TABLE consumer_keys;
SELECT COUNT(*) FROM consumer_keys;   -- should be 0 on first run
```

The schema uses `CREATE TABLE IF NOT EXISTS`, so re-running is safe.

## Step 2 — Generate a key for `brain`

```sql
INSERT INTO consumer_keys (name, api_key, permissions, notes)
VALUES (
  'brain',
  -- Generate locally — DO NOT type a memorable string. Example:
  --   python -c "import secrets; print(secrets.token_hex(32))"
  '<paste 64-char hex token here>',
  JSON_ARRAY('read_chunks', 'read_health'),
  'Analytics box — Swanwood. Created 2026-05-04 to retire pi-key reuse.'
);
```

Save the plaintext token in `PoolAIssistant-Project/.env` as `CONSUMER_KEY=...`
(and propagate to the brain machine if it's running anywhere else).

## Step 3 — Pull the live chunks-API PHP files into the repo

This is the one-time hygiene fix that the original `install_chunks_api.php`
should have done but didn't. From any FTP client, download these files
from `poolai.modprojects.co.uk:/api/`:

- `list_chunks.php`
- `chunks_status.php`
- `download_chunks.php`
- `upload_chunk.php`

Place them in `web-portal/poolai_deploy/api/` (their canonical home, since
that's the FTP-deploy target) and commit. Now they're version-controlled
and edits below are reviewable as a diff.

## Step 4 — Swap the auth check in each consumer endpoint

For `list_chunks.php`, `chunks_status.php`, `download_chunks.php` — anywhere
that currently does:

```php
$stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE api_key = ? AND is_active = 1");
$stmt->execute([$api_key]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$device) {
    errorResponse('Invalid API key', 401);
}
```

…replace with:

```php
require_once __DIR__ . '/../includes/api_helpers.php';
$caller = authenticateConsumerKey(db(), 'read_chunks');
// $caller['name'] is e.g. 'brain'; $caller['id'] for audit logging.
```

Endpoints that need to remain Pi-only (e.g. `upload_chunk.php` — Pis upload,
analytics consumers don't) keep the existing pi_devices check.

## Step 5 — Deploy + verify

1. FTP the updated PHP files to BOTH `poolai_deploy/` and `php_deploy/` (the
   server-side `copy()` logic in `install_chunks_api.php` mirrors them
   between the two domains; that runs from `poolai` to `poolaissistant`).
2. From the brain machine, smoke-test:
   ```bash
   curl -H "X-API-Key: $CONSUMER_KEY" \
     https://poolaissistant.modprojects.co.uk/api/chunks_status.php
   ```
   Should return `{"ok": true, ...}`. If it returns `{"ok": false, "error":
   "Invalid API key"}` re-check Step 2 and that the row's `is_active = 1`.

## Step 6 — Optional: re-add the HTTP path to brain/db_sync.py

`brain/db_sync.py` currently uses FTP exclusively. If/when chunks-API access
is desired again (HTTPS is friendlier than FTP for restrictive networks
and gives proper status codes), gate the HTTP listing behind an env check:

```python
consumer_key = os.getenv('CONSUMER_KEY', '').strip()
if consumer_key:
    chunks = self._fetch_chunk_list_http(consumer_key)
    if chunks is None:
        chunks = self._fetch_chunks_for_device_ftp(...)  # fallback
```

That's a separate, scope-creep-aware change. The auth model lands first;
the brain integration follows when needed.

---

## Operational notes

- **Rotation:** to retire a key, set `is_active = 0`. The row stays for audit
  history. Never `DELETE` a key that's been used — `last_used_at` is the
  paper trail.
- **Permissions:** they're stored as a JSON array. Add new permission
  strings as you add endpoints; keep them lowercase-snake for consistency.
- **Per-key rate limiting:** not implemented. If it becomes needed, the
  `id`-based audit columns (and a separate `consumer_key_usage` table)
  are the natural foundation.
