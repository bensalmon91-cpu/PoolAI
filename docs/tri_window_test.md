# PoolAIssistant — Tri-Window Round-Trip Test

Tests the full data path end-to-end:

```
Admin pushes change  -->  Pi receives on heartbeat  -->  Pi applies it
        ^                                                     |
        |                                                     v
        +-------  Heartbeat snapshot back to admin + portal --+
```

Run this as an autonomous browser agent with THREE tabs/windows open
side-by-side. The user will run one SSH command at a designated step
to force an immediate heartbeat (heartbeat is otherwise ~1h on this Pi).

---

## Windows

| Label    | URL                                                          |
|----------|--------------------------------------------------------------|
| W-Admin  | `https://poolaissistant.modprojects.co.uk/admin/device.php?id=12` |
| W-Client | `https://poolai.modprojects.co.uk/device.php?id=12` (login first via `/login.php`) |
| W-Pi     | `http://10.0.30.106/` or `http://PoolAI.local/` (LAN only) |

Open all three before starting. Log in to admin + customer portals.

## Credentials to supply

- Admin user / password: **{FILL IN}**
- Customer email / password: **{FILL IN}**
- SSH host: `poolai@10.0.30.106` (or `poolai@PoolAI.local`), password `12345678`

---

## Setting under test

- Key: `appearance_theme`
- Allowed values: `light` / `dark` / `system`
- Default: `light`
- Visual indicator on Pi: page background + UI chrome change colour
  (light ≈ near-white, dark ≈ near-black). If current value is `light`
  we'll push `dark`, and vice versa. At the end we push it back.

---

## Steps

### Step 0 — Snapshot current state across all three windows

Record before doing anything:

- **W-Pi**: visit `/settings`, find the Appearance / Theme setting,
  note the current value. Also note general page background colour.
- **W-Admin** (`device.php?id=12`): scroll to Remote Settings →
  Appearance section → note **current** value of `appearance_theme` (the
  heartbeat-reported value). If the banner says "no snapshot yet", note
  that too.
- **W-Client**: on customer device view, note any "Last updated" /
  "Last heartbeat" timestamp on screen.

Call this the **baseline**. Report each value.

### Step 1 — Push the change from admin

- In **W-Admin** Remote Settings, change `appearance_theme`:
  - if baseline was `light` → set to `dark`
  - if baseline was `dark` or `system` → set to `light`
- Click apply.
- Expected: HTTP 200, JSON `{ok: true, command_id: N, applied_keys: ["appearance_theme"], ...}`.
- Capture `command_id` and the full response body from the Network tab.
- On the page, the "proposed" column for `appearance_theme` should now
  show the new target value awaiting device ack.

### Step 2 — Force an immediate heartbeat (USER ACTION)

**Pause and tell the user to run this from their terminal:**

```bash
ssh poolai@10.0.30.106 'sudo systemctl start poolaissistant_health.service'
# password: 12345678
```

Or, if PoolAI.local resolves:

```bash
ssh poolai@PoolAI.local 'sudo systemctl start poolaissistant_health.service'
```

Wait ~10 seconds for it to complete. The script is oneshot — it sends
one heartbeat, fetches pending commands, applies them, and exits.

If the user cannot SSH right now, fall back: wait the configured
heartbeat interval (~1 hour on this Pi) and come back. Skip to Step 3
once the wait is done.

### Step 3 — Verify propagation

After the heartbeat has run, do the following IN ORDER:

**W-Pi** (hard-refresh, Ctrl+Shift+R):
- Navigate to `/settings`. Expected: Theme value now matches the pushed
  value (e.g. `dark`).
- Navigate to the home/pool page. Expected: page colours now reflect
  the new theme (e.g. dark background if pushed `dark`).
- Report: observed Theme value, and whether the visual change is
  visible.

**W-Admin** (hard-refresh `device.php?id=12`):
- Remote Settings → Appearance → `appearance_theme`. Expected:
  "current" column now shows the new value (heartbeat has reported it
  back). "proposed" column should clear.
- Command History panel: expected to show the `apply_settings` command
  with status `completed`.
- Report: current + proposed value, command history row text.

**W-Client** (hard-refresh):
- Expected: "Last updated" / "Last heartbeat" timestamp has advanced
  to a few seconds/minutes ago. Readings should render normally.
- If the customer portal exposes any appearance / theme indicator,
  check that too (most portals don't — this is normal).
- Report: timestamp before vs after, any errors.

### Step 4 — Push it back to original

Repeat Step 1 but set `appearance_theme` back to the Step-0 baseline.
Repeat Step 2 (another SSH heartbeat trigger). Repeat Step 3 and
confirm everything is back to the baseline.

### Step 5 — Trace dump

Navigate **W-Admin** to
`https://poolaissistant.modprojects.co.uk/admin/trace_view.php`. Paste
the full output.

Expected: two `admin_update_setting` entries (one per push), each with
`auth` not `NOAUTH`, and bodies containing
`{"device_id":12,"settings":{"appearance_theme":"..."}}`.

---

## What a PASS looks like

- Admin push returns `ok:true` and a `command_id` both times.
- After each SSH heartbeat trigger, the Pi visibly changes theme within
  ~15 seconds of the command finishing.
- Admin "current" column updates to match the pushed value on the next
  snapshot.
- Customer-side "Last updated" advances after each heartbeat.

## What a FAIL looks like (capture and report)

- Admin push returns non-200 or `ok:false` → capture full response.
- Heartbeat runs but `appearance_theme` doesn't change on the Pi → the
  `apply_settings` handler wrote to `pooldash_settings.json` but the
  Flask UI didn't pick it up, or the write failed. Ask the user to SSH
  and show the last 30 lines of
  `/opt/PoolAIssistant/logs/health_reporter.log`.
- Admin current column never updates even after heartbeat → heartbeat
  snapshot isn't including the value, or server isn't storing it.
- Customer portal Last-updated doesn't advance → upload or heartbeat
  path is broken.

---

## Report format

Same as prior runs — one block per Step, with result / http / response
/ notes. Include screenshots or visible text from W-Pi at Step 0 and
Step 3 so we can confirm the visual theme change.

End with the full Step 5 trace dump verbatim.
