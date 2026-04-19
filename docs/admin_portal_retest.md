# PoolAIssistant — Retest + Customer Portal Plan

Autonomous browser test. Run every step, record results in the same
format as the previous report. Keep Chrome DevTools → Network tab
visible.

## Credentials and URLs

- Admin portal: `https://poolaissistant.modprojects.co.uk/admin/`
- Admin username: **{FILL IN}**
- Admin password: **{FILL IN}**
- Customer portal: `https://poolai.modprojects.co.uk/`
- Customer test email: **{FILL IN}**
- Customer test password: **{FILL IN}**
- Test device ID: **12** (Pi-d91cc979 — reactivated for this run)
- Admin trace viewer:
  `https://poolaissistant.modprojects.co.uk/admin/trace_view.php`

---

## Part A — Admin retests

### A1 — T10 retest: Remote Settings change (previously FAILED)

1. Log in to admin. Navigate to `/admin/device.php?id=12`.
2. Scroll to the **Remote Settings** panel.
3. In the **Cloud sync** section, flip `cloud_upload_enabled` to the
   opposite of its current value (if "(no change)" then pick `false`).
4. Click the submit/apply button.
5. **Expected (fixed):** HTTP 200, JSON `{"ok":true, ...}`, green
   success banner on the page mentioning a `command_id` and "will apply
   on the device's next heartbeat". The "proposed" column for the
   changed key should now show the new value.
6. Capture from Network tab: request URL, status, full response JSON.
7. If it still fails, stop and paste the exact error + request/response.

### A2 — T8 retest: Queue Test Question

The Test AI button lives on the **dashboard** (`/admin/`), not the
device detail page. Look in the device row, Actions column.

1. Return to `/admin/`.
2. On the Pi-d91cc979 row, click **Test AI**.
3. Expected: alert with something like "Test question queued!"
   listing the device + the question text.
4. Capture: Network POST to `/api/queue_test_question.php` → status +
   JSON response.

### A3 — T12 retest: Clients pages (not linked from nav)

The clients admin pages are deployed but there's no nav link. Navigate
to them directly by URL.

1. Navigate to `https://poolaissistant.modprojects.co.uk/admin/clients.php`.
2. Expected: table of portal customers renders, or an empty-state
   message, with no PHP errors. Status 200.
3. Note the ID of any client listed (or say "none").
4. If any client exists, click through / navigate to
   `https://poolaissistant.modprojects.co.uk/admin/client_detail.php?id=<id>`.
5. Expected: detail page renders, linked devices visible. Status 200.
6. Report: status codes, any errors, column headings shown.

### A4 — Trace retrieval (admin)

1. Navigate to `/admin/trace_view.php`.
2. Copy the full output into the report.
3. Expected: every request from this retest shows **`auth`** (not
   NOAUTH) — that was a logger-placement bug fixed after the previous
   run.

---

## Part B — Customer portal tests

End-user-facing portal at `https://poolai.modprojects.co.uk/`. Logged
in as the customer account (not admin). If the test device is not yet
linked to the customer account, say so and skip the device-view tests.

### B1 — Customer login

1. Navigate to `https://poolai.modprojects.co.uk/login.php`.
2. Log in with the customer test email + password.
3. Expected: redirect to dashboard, no errors, user menu visible.
4. Report: final URL, page title, whether any devices are listed for
   this customer.

### B2 — Customer dashboard renders

1. On the dashboard, scroll through the page.
2. Expected: no red errors, no PHP notices in body, no Network 500s.
3. Report: number of devices listed, any status/health summary visible,
   any banners.

### B3 — Customer device view

1. Click into the Pi-d91cc979 device (or navigate to
   `https://poolai.modprojects.co.uk/device.php?id=12` if that id
   matches the customer's link).
2. Expected: device detail page renders with readings (pH, chlorine,
   ORP, temperature if available), health, last-updated timestamp.
3. Check each visible section for rendering errors or "N/A" placeholders
   that suggest the data pipeline isn't flowing.
4. Capture any AI suggestions panel contents.
5. Report: readings shown, last-updated time, any broken panels.

### B4 — Customer account page

1. Click into account settings (or `/account.php`).
2. Expected: account details page renders. No test of password
   changes — read-only inspection only.
3. Report: fields visible, linked devices count.

### B5 — Customer logout

1. Log out.
2. Expected: redirect to login or public page.

---

## Reporting

Return one section per test in the same format as before
(result/http/response/alert/notes). At the end, paste the full
A4 trace dump verbatim.

If anything fails with a 500, capture the complete response body —
Hostinger often echoes the fatal-error message which pinpoints the
broken line.
