# PoolAIssistant Admin Portal — Browser Test Plan

You are an autonomous browser agent (Claude in Chrome). Run through every
step below in order, in a single Chrome session. After each step, record
the observed result in your final report. Do **not** skip steps, and do
**not** perform destructive actions on any device other than the one
nominated as the TEST DEVICE.

---

## Credentials and URLs

- Admin portal root: `https://poolaissistant.modprojects.co.uk/admin/`
- Login page: `https://poolaissistant.modprojects.co.uk/admin/login.php`
- Admin username: **{FILL IN BEFORE RUNNING}**
- Admin password: **{FILL IN BEFORE RUNNING}**
- Diagnostic trace viewer (admin-authenticated):
  `https://poolaissistant.modprojects.co.uk/admin/trace_view.php`
- TEST DEVICE ID: **{FILL IN — use an inactive or disposable device only}**

Before you begin, open Chrome DevTools → Network tab and keep it visible
throughout the session so you can capture request/response status codes
and response bodies.

---

## Test cases

For each test case: perform the action, observe the on-page result, then
read the last request in DevTools Network panel. Record:

- HTTP status code
- `ok` field of the JSON response (`true` / `false`)
- If `ok: false`, the full `error` string
- Any visible alert text or red banner on the page

### T1 — Login

1. Navigate to the login page.
2. Enter admin username and password, submit.
3. Expected: redirected to `/admin/`, dashboard renders, device list
   visible.
4. Report: page title, presence of logout link, number of devices listed.

### T2 — Dashboard renders cleanly

1. On `/admin/`, scroll through the full page.
2. Expected: no red error banners, no PHP warnings in page body, no 500s
   in Network tab.
3. Report: any HTTP status ≥ 400 or PHP notices seen.

### T3 — Open the TEST DEVICE detail page

1. Click the TEST DEVICE row in the device list, or navigate to
   `/admin/device.php?id={TEST_DEVICE_ID}`.
2. Expected: page renders, shows device name, health, Remote Commands
   panel with buttons (Request Upload, Restart Services, Check Updates),
   Remote Settings panel.
3. Report: status code of the page load, section headings visible.

### T4 — Request Upload (direct, no confirm modal)

1. In the Remote Commands panel, click **Request Upload**.
2. Expected: an alert appears with text like *"Upload requested. Device
   will upload on next heartbeat."*
3. Dismiss the alert. Page reloads.
4. Report: exact alert text, and from Network tab the POST to
   `/api/admin_device_command.php` → status code + JSON `ok` +
   `command_type` echoed in response.

### T5 — Restart Services (goes through confirm modal)

1. Click **Restart Services**.
2. A confirmation modal appears. Click **Confirm**.
3. Expected: alert appears with the success message from the server.
4. Report: alert text, Network POST body you captured (should contain
   `"command":"restart"` — **not** `"command":null`), status code, and
   JSON response.

### T6 — Check Updates (goes through confirm modal)

1. Click **Check Updates**.
2. Click **Confirm** in the modal.
3. Expected: alert with a success message.
4. Report: same fields as T5, but for `"command":"update"`.

**Critical:** if either T5 or T6 fails with *"Missing command type"* or
the request body contains `"command":null`, stop and flag it — that
regression is exactly what this test exists to catch.

### T7 — Clear Issues (if the button is shown on this device)

1. If **Clear Issues** button is visible, click it and confirm the
   standard `confirm()` prompt.
2. Expected: page reloads, issue indicator clears.
3. Report: status code of the POST to `/api/clear_device_issues.php`,
   JSON response.

### T8 — Queue test question (if control is exposed on device page)

1. Locate any control for sending a test AI question to the device. If
   not present on this page, skip and note "no UI exposed".
2. Otherwise send a sample question.
3. Report: status of POST to `/api/queue_test_question.php`, JSON
   response.

### T9 — Remote Settings: read current

1. Scroll to the Remote Settings panel on the device page.
2. Expected: form renders grouped sections with current values pulled
   from the last heartbeat.
3. Report: list of visible setting keys and their current values.

### T10 — Remote Settings: change one safe value

1. Pick a safe boolean or enum setting (e.g. `cloud_upload_enabled` or
   `logging_interval_minutes` — **do not change anything that affects
   device identity or backend URLs**).
2. Flip the value, submit the form.
3. Expected: success banner; the "proposed" column for that key should
   now show the new value awaiting device ack.
4. Report: Network POST to `/api/admin_update_setting.php` → status +
   JSON response. If the response contains per-key errors, record them.

### T11 — Delete device (soft)

**Only run this on the nominated TEST DEVICE.** Do not click × on any
other row.

1. Return to `/admin/`.
2. Click the × button on the TEST DEVICE row.
3. Confirm the browser `confirm()` prompt.
4. Expected: row is removed or greyed out.
5. Report: status code + JSON response for POST to
   `/api/delete_device.php`. Expected `{ok: true, deleted: true}`.

### T12 — Clients page (if linked from navigation)

1. Look for a "Clients" link in the admin navigation. If present,
   navigate to it.
2. Expected: table of portal customers renders without errors.
3. If not present, skip.

### T13 — Logout

1. Click logout.
2. Expected: redirected to login page.
3. Report: final URL, session cookie cleared.

### T14 — Retrieve server-side trace

1. Log back in.
2. Navigate to
   `https://poolaissistant.modprojects.co.uk/admin/trace_view.php`.
3. Expected: plain-text dump of up to the last 50 instrumented admin
   requests, one per line, showing timestamp, endpoint, auth state,
   method, and raw body.
4. Copy the full contents into your report.

---

## Final report format

Return a single report with one section per test, each containing:

```
T<n> — <name>
  result: PASS | FAIL | SKIPPED
  http: <status>
  response: <json or summary>
  alert: <text if any>
  notes: <anything unexpected>
```

At the end, include the full T14 trace dump verbatim.

If any test fails, do not retry more than once — record the failure and
move on so the trace captures it. We'll debug from the report.
