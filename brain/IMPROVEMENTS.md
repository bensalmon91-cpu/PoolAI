# Brain — Pending Improvements & Open Questions

**Last updated:** 2026-05-04

This file tracks known weaknesses in the brain/ pipeline and proposes concrete next steps.
Created during the multi-device refactor / consolidation pass on 2026-05-03.

---

## Headline problem: 7-week data gap

As of 2026-05-03, the freshest reading in `output/pool_readings.db` is from
**2026-03-12 18:43 UTC**. The Pi at Swanwood (`10.0.30.5`) appears to have
stopped uploading chunks after that point. Pool operators have therefore had
no historical-trend or anomaly-detection signal for 7 weeks.

Possible causes (in rough order of likelihood):

1. **The chunker on the Pi stopped running** — `chunk_manager_improved.py` is
   typically scheduled via cron/systemd; the v6.11.x rollout (per root
   `CLAUDE.md`) did "network redesign + installer cleanup" around the relevant
   window and the schedule may not have been re-installed.
2. **Pi-side chunk-creation succeeds but upload fails silently** —
   `chunk_manager_improved.py` keeps a per-period "failed_chunks" tracker; if
   the API key in the Pi's settings was rotated server-side, every upload
   would 401 and pile up in failed-chunks.
3. **Chunks are landing on a different path** — the Pi was reassigned to
   device ID `5` around Feb 24 (we saw `/data/chunks/2/` go silent that day
   and `/data/chunks/5/` start). If a *third* device-ID rebrand happened
   after Mar 12, chunks would be landing in a directory we don't yet know
   about. (`db_sync.py --devices` will show this once the Pi resumes.)
4. **The raw Modbus pipeline on the Pi failed** — chemistry data isn't being
   written to the Pi's local SQLite at all, so there's nothing to chunk.

### Action plan to close the gap

The investigation is *outside* `brain/` — it's a Pi-software / web-portal task —
but `brain/` should make the staleness loud and unmissable so it can't go
silent for 7 weeks again.

| # | Action | Owner | Status |
|---|---|---|---|
| G1 | Hit `/api/heartbeat.php`-derived `device_health` (or look at the admin portal) for the Swanwood Pi to see `last_upload_success` | web-portal | ✅ done 2026-05-04 — found device 12 (replaced device 5 on 2026-04-12) has zero successful uploads since creation |
| G2 | If G1 says the Pi *is* uploading, check whether chunks are landing in `/data/chunks/{new_id}/` — re-run `python brain/db_sync.py --devices` | brain | ✅ confirmed on 2026-05-04: only `/data/chunks/2/` and `/data/chunks/5/` exist, both empty since drained on Mar 12 |
| G3 | If the Pi has stopped chunking, SSH to `poolai@10.0.30.5` and check `systemctl status pooldash-chunk-manager` (or whatever the unit is called) and `~/PoolDash_v6/logs/chunk_manager.log` | pi-software | 🟡 partial — admin-triggered upload fixed in v6.11.11 (`f1c5c38`) by correcting hardcoded `/home/poolaissistant/` path → `Path(__file__).resolve().parent`. **Autonomous `chunk_sync.timer` still suspected dormant** — needs SSH check |
| G4 | If the API key on the Pi is stale (G2 returns 401s), rotate via admin portal and update Pi `settings.json` | web-portal + pi | ⏳ blocked behind G3 — diagnose timer state first |
| G5 | Implement **B1** below (staleness alarm in brain) before relying on the pipeline for monitoring again | brain | ✅ done 2026-05-04 (`f1c5c38`) |

---

## B. Brain-internal improvements (this repo, this codebase)

These are concrete, scoped changes to brain/ files. Roughly ordered by value-per-effort.

### B1. Staleness alarm ✅ DONE (2026-05-04)

**Problem:** `db_sync.py` declared "Sync complete!" for 7 weeks while the database
fell 7 weeks out of date. Every consumer downstream (alerts, baselines,
investigator) cheerfully kept running on stale data.

**Implementation:**
- `ChunkSyncer._check_staleness()` queries `MAX(ts) FROM readings` after the
  merge phase, computes hours since the newest reading.
- Threshold is `STALENESS_HOURS` env var (default 6).
- `output/staleness.json` written every sync as a structured marker — readable
  by external monitors without parsing logs.
- `db_sync.py` exits non-zero on stale data, even if the sync itself succeeded —
  cron/Task Scheduler wrappers can now alarm.
- `alert_checker.py` adds a `staleness` field to `analysis/latest_alerts.json`
  and escalates overall `status` to `CRITICAL` when stale, regardless of
  per-sensor alerts. The "stale" log line says explicitly that the per-sensor
  alerts below reflect old data, not live state.

Verified against the post-Mar-12 dataset on 2026-05-04: warning fires
("1268.8h old, 52.9 days"), staleness.json written, exit code 1.

### B2. Replace Pi-key auth with a proper consumer key

**Problem:** `brain/.env` historically held an `API_KEY` that was a row from
the `pi_devices` table. That was wrong — brain isn't a Pi. The key got
deactivated/rotated, every API call went 401, and the FTP fallback masked it.

**Fix today (this commit):** the API codepath has been removed from
`db_sync.py`. FTP is sole source of truth. `API_KEY` is no longer required
in `.env`.

**Future fix (B2-future):** if we ever want HTTP-based chunk listing back
(useful if FTP becomes unreliable or we move to S3-style storage), introduce
a separate `consumer_keys` table on the server, generate a brain-specific
key, and have the auth middleware accept either. Don't reuse `pi_devices`
as the trust store.

### B3. Convert hardcoded data assumptions to env-driven config

**Problem:** the chunker's path was hardcoded to `/data/chunks/2`. Same
risk lurks in:
- `'2020-01-' in db_path.name` — a hardcoded "skip test data" rule.
- `pool_readings.db` filename and the implicit `readings` table name in
  `merge_chunks` and `_check_staleness` (B1).
- The 4 IP-addressed controllers (`192.168.200.11..14`) are referenced by
  IP rather than by friendly name in the merged DB. (Probably fine, but
  worth flagging.)

**Fix:** anything that looks like environment-specific data should come from
`.env` (preferably the consolidated root `.env` once that lands).

### B4. Data-quality sanity checks before alerts

**Problem:** the Mar 12 alert run flagged Vitality pH at **2.67** as
CRITICAL. A live pH of 2.67 is hazardous and should have triggered immediate
human attention, but the *most likely explanation* is a failed pH probe
(stuck reading), not a real chemistry event. Right now alerts treat both
identically.

**Fix:** before alerting, run cheap sanity checks:
- pH should be 5.0–9.0 in any operating pool — outside that band, flag as
  *probable sensor fault* not *chemistry critical*.
- Temperature should be 0–60°C — outside, *probable sensor fault*.
- ORP should be 0–1500 mV — same.
- A reading that is **constant for >2 hours** at unusual values → probable
  stuck sensor.
- A reading that **suddenly jumps >50%** in <5 min and stays there →
  probable sensor swap or cable fault.

The investigator would then surface "Vitality pH probe likely failed" rather
than "POOL IS BATTERY ACID."

### B5. Replace silent FTP failures

**Problem:** the original `db_sync.py` had `try/except` blocks that returned
empty lists on failure. The new code logs errors but still returns empty —
which mostly works because `sync()` now warns when "no chunks available."
There are still a couple of silent paths in `_delete_from_ftp` and the
download path; auditing those is cheap follow-up work.

### B6. Auto-update brain/CLAUDE.md known-issues from the latest_alerts.json

The current "Current Known Issues (as of Feb 26)" section in `brain/CLAUDE.md`
is hand-written and decays. Generate it from `output/analysis/latest_alerts.json`
on every sync, with a clear `Generated:` timestamp. Saves a manual step in
the Session End Checklist.

---

## C. Cross-cutting (monorepo-level, beyond brain/)

### C1. Single source of truth for credentials (Option A in chat)

`web-portal/`, `brain/`, `ai-assistant/php/` each have their own `.env`. Some
keys (e.g. `ANTHROPIC_API_KEY`, FTP host/user) duplicate. The deploy
folders genuinely need their own — they get FTP'd to the live server as-is —
but the rest can collapse to a root `.env` discovered via `find_dotenv()`.

Tracked as a separate task in the task list.

### C2. Migrate plaintext credentials out of root CLAUDE.md

Currently in `PoolAIssistant-Project/CLAUDE.md` (lines ~39–68): FTP password,
DB password, bootstrap secret. Even in a private repo, secrets in tracked
files end up in git history, agent contexts, and shell history. Move to the
new root `.env`; replace the CLAUDE.md section with a pointer.

(Note: prior commits still contain the plaintext. If real rotation is
desired, rotate the credentials *and* either accept the historical leak in
git or scrub history with `git filter-repo`. Decide separately.)

### C3. Heartbeat-derived "is the Pi healthy" for brain to consume

`web-portal/php_deploy/api/heartbeat.php` writes Pi-side health into
`device_health`. Right now brain has no awareness of this. A 30-line addition
that reads the latest heartbeat per device and surfaces:
- last successful upload timestamp
- pending chunks count
- Pi disk / memory / temp pressure

…would let brain's staleness alarm (B1) distinguish "Pi is dead" from
"Pi is alive but chunker is stuck" from "everything is fine, just no new
data because nothing changed" — the three cases need different responses.

---

## D. Things to NOT do

For the record, these were considered and rejected:

- **Pull from Hostinger MySQL directly instead of via chunks.** The cloud
  DB (`u931726538_PoolAIssistant`) only has *recent* readings (real-time
  for the customer portal), not historical. Chunks remain the right
  archival path. We can supplement with MySQL for "what's happening
  *right now*" but not replace.
- **Make brain run on the Pi.** Tempting (zero-network sync), but the
  Pi has tight disk and the multi-pool analyzer is RAM-hungry on the
  merged 13GB SQLite. Stay client-server.
- **Remove the `delete_after_download` behavior.** It's the right default
  *given there's only one consumer*. Long-term, soft-delete on the server
  side (move to `archive/`) is safer, but that's a server change, not a
  brain change.
