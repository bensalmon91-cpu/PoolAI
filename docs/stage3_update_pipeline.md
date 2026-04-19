# PoolAIssistant — Stage 3: Software-Update Pipeline Test

Closes out two open issues from Stages 1–2:

- **T10 FAIL** — Pi reports `Unknown command type: apply_settings`
  because it's running v6.10.4, which pre-dates the handler.
- **T6 FAIL** — admin "Check Updates" completed with `status=failed`,
  meaning the Pi's own update path also broke.

The goal of Stage 3 is to get the Pi to v6.11.1 and prove both paths work
end-to-end, so the next fleet update goes cleanly.

Requires a terminal on the same LAN as the Pi (for SSH). Claude in
Chrome cannot SSH directly — the human runs SSH commands; Claude
observes via the admin / customer / Pi windows.

---

## Preconditions

- Stages 1 and 2 completed, reports captured.
- Admin trace instrumentation still installed (do not remove until end
  of Stage 3).
- Test device: Pi-d91cc979 (DB id=12).
- Admin + customer portals logged in in separate tabs.
- SSH reachable: `ssh poolai@10.0.30.106` (password `12345678`).

---

## Step 1 — Baseline version check (before touching anything)

Record in the report, from three sources, the version the Pi believes it
is running:

1. **Admin view** — `https://poolaissistant.modprojects.co.uk/admin/device.php?id=12`
   → "Device Information" section, field `software_version` / Firmware
   version. Expected: **6.10.4** (per Stage 2 report).
2. **Pi web UI** — navigate to `http://10.0.30.106/settings` or
   whatever the footer/about link shows. Record the version string.
3. **SSH** — run:
   ```
   cat /opt/PoolAIssistant/app/VERSION
   ```
   Record exact output.

If all three agree on 6.10.4, continue. If they disagree, flag it —
that's a reporting bug worth a note but not a Stage 3 blocker.

## Step 2 — Capture baseline logs

Before kicking anything off, grab the last 50 lines of the update log
so we have "before" state:

```
ssh poolai@10.0.30.106 'sudo tail -n 50 /var/log/poolaissistant/update_check.log 2>/dev/null || sudo tail -n 50 /opt/PoolAIssistant/logs/update_check.log 2>/dev/null || echo "NO LOG FOUND"'
```

Paste the output. If `NO LOG FOUND`, note that — the update path may
never have been exercised successfully.

Also grab the last 30 lines of health_reporter to see what the admin
"Check Updates" attempt actually did on the Pi:

```
ssh poolai@10.0.30.106 'sudo tail -n 30 /opt/PoolAIssistant/logs/health_reporter.log 2>/dev/null || sudo journalctl -u poolaissistant_health -n 30'
```

Specifically look for "update" or "Unknown command type" entries.

## Step 3 — Manual update attempt via SSH

Run the update checker in apply mode:

```
ssh poolai@10.0.30.106 'sudo python3 /opt/PoolAIssistant/app/scripts/update_check.py --apply'
```

Paste the **full output verbatim** into the report. It typically prints:

- current version
- server-advertised latest version
- checksum / signature verification state
- download progress
- apply / rollback result

Expected outcomes:

- **Success:** log shows download OK, verification OK, service restart
  OK, reported version bump to 6.11.1.
- **Signature rejection:** log mentions Ed25519 signature missing or
  invalid, refuses to apply. Capture the exact message.
- **HTTP error:** download URL returns 404/403/500. Capture the URL
  and the status code.
- **Checksum mismatch:** download succeeds but SHA256 doesn't match
  what the server published. Capture both values.
- **Rollback:** install started but the post-install smoke test failed
  and rolled back. Capture rollback reason.

Whichever path is hit dictates the next step.

## Step 4 — Verify update took effect

Re-run all three version checks from Step 1. Expected: **all three now
show v6.11.1**.

Also confirm the services restarted cleanly:

```
ssh poolai@10.0.30.106 'sudo systemctl status poolaissistant_ui poolaissistant_health.timer --no-pager | head -40'
```

Record any services in `failed` state.

## Step 5 — Smoke test the Pi UI after update

Open the Pi UI (`http://10.0.30.106/`). Verify the main pool page
renders, settings page loads, no 500s. Record any visible regressions.

## Step 6 — Rerun the tri-window Stage 2 push

Now repeat **only the theme round-trip** from Stage 2:

1. **W-Admin** → device.php?id=12 → Remote Settings →
   `appearance_theme` → flip to the opposite of current.
2. Capture `command_id` from the POST response.
3. SSH-trigger an immediate heartbeat:
   ```
   ssh poolai@10.0.30.106 'sudo systemctl start poolaissistant_health.service'
   ```
4. Wait ~15 s. Refresh **W-Admin** Command History for this device.

**Expected now:** the apply_settings row shows `status=completed` and
the `result` field says something like
`Applied: ['appearance_theme']` (was previously `Unknown command
type: apply_settings`).

Also refresh the Pi UI — theme should visibly change.

Flip it back once. Same verification.

Report the `result` text for **both** apply_settings rows. That's the
pass/fail signal.

## Step 7 — Server-side trace dump

Navigate **W-Admin** to
`https://poolaissistant.modprojects.co.uk/admin/trace_view.php`. Paste
everything. Expect the two new `admin_update_setting` entries with
`auth`.

## Step 8 — Admin trigger retest of "Check Updates"

Now that we know manual SSH update works, confirm admin's button also
works when there's nothing to update (Pi is current):

1. **W-Admin** → device.php?id=12 → click **Check Updates** → confirm.
2. SSH-trigger a heartbeat again so the Pi picks it up quickly.
3. Wait ~15 s, refresh. Command History should show the update row.

Possible outcomes:

- `status=completed` with result "No update available" (or similar) →
  update path is healthy.
- `status=failed` with same error as before → the admin-triggered path
  has a separate bug from the SSH path. Capture the `result` text.

---

## Report format

For each step, record: what was run / observed, verbatim output for SSH
steps, screenshot or text for UI steps. At the end:

- Exit version on the Pi
- Whether T10 (apply_settings) now passes
- Whether T6 (admin Check Updates) now passes
- Anything unexpected in the logs

## Stop conditions

Stop and flag — do **not** keep retrying — if any of these happen:

- Step 3 output includes "signature verification failed" or "refusing
  to apply unsigned update": capture the exact line. A signing /
  rollout config fix is needed; don't force-apply.
- Update install partially succeeds then rolls back: capture the
  rollback reason. Do not retry.
- Any service enters a crash loop after update.

In any of those, the human should decide next steps before rerunning.
