"use strict";

const { pool, query } = require("../db");
const { sendAlertEmail } = require("./email");
const { DEVICE_OFFLINE_MINUTES } = require("../config");

// Track when we last sent alerts to avoid spam
const lastAlertSent = {};

async function checkDeviceHealth() {
  if (!pool) return;

  try {
    // Find devices that haven't been seen in DEVICE_OFFLINE_MINUTES
    const result = await query(
      `SELECT d.device_id, d.hostname, d.last_seen_at,
              a.name as account_name, p.name as pool_name
       FROM devices d
       LEFT JOIN accounts a ON d.account_id = a.id
       LEFT JOIN pools p ON d.pool_id = p.id
       WHERE d.last_seen_at IS NOT NULL
         AND d.last_seen_at < NOW() - ($1 || ' minutes')::INTERVAL
         AND d.account_id IS NOT NULL`,
      [DEVICE_OFFLINE_MINUTES]
    );

    for (const device of result.rows) {
      const alertKey = `offline_${device.device_id}`;
      const lastAlert = lastAlertSent[alertKey];
      const now = Date.now();

      // Only alert once per hour per device
      if (lastAlert && now - lastAlert < 60 * 60 * 1000) {
        continue;
      }

      const lastSeen = new Date(device.last_seen_at);
      const minutesAgo = Math.round((now - lastSeen) / 60000);

      const subject = `[PoolDash Alert] Device Offline: ${device.hostname || device.device_id.slice(0, 8)}`;
      const body = `Device has gone offline.

Device: ${device.hostname || device.device_id}
Account: ${device.account_name || "Unassigned"}
Pool: ${device.pool_name || "Unassigned"}
Last seen: ${lastSeen.toISOString()} (${minutesAgo} minutes ago)

This alert is sent when a device hasn't reported in for ${DEVICE_OFFLINE_MINUTES} minutes.

--
PoolDash Monitoring`;

      await sendAlertEmail(subject, body);
      lastAlertSent[alertKey] = now;
    }

    // Check for upload failures
    const failedUploads = await query(
      `SELECT h.device_id, h.last_upload_error, h.failed_uploads, h.ts,
              d.hostname, a.name as account_name
       FROM device_health h
       JOIN devices d ON h.device_id = d.device_id
       LEFT JOIN accounts a ON d.account_id = a.id
       WHERE h.failed_uploads > 0
         AND h.ts > NOW() - INTERVAL '1 hour'
       ORDER BY h.ts DESC`
    );

    // Group by device to only alert once
    const seenDevices = new Set();
    for (const row of failedUploads.rows) {
      if (seenDevices.has(row.device_id)) continue;
      seenDevices.add(row.device_id);

      const alertKey = `upload_fail_${row.device_id}`;
      const lastAlert = lastAlertSent[alertKey];
      const now = Date.now();

      // Only alert once per 2 hours per device for upload failures
      if (lastAlert && now - lastAlert < 2 * 60 * 60 * 1000) {
        continue;
      }

      const subject = `[PoolDash Alert] Upload Failure: ${row.hostname || row.device_id.slice(0, 8)}`;
      const body = `Device is experiencing upload failures.

Device: ${row.hostname || row.device_id}
Account: ${row.account_name || "Unassigned"}
Failed uploads: ${row.failed_uploads}
Last error: ${row.last_upload_error || "Unknown"}

The device will automatically retry uploads. If this persists, check the device's network connection.

--
PoolDash Monitoring`;

      await sendAlertEmail(subject, body);
      lastAlertSent[alertKey] = now;
    }
  } catch (err) {
    console.error("Error checking device health:", err);
  }
}

function startHealthMonitor() {
  // Run health check every 15 minutes
  setInterval(checkDeviceHealth, 15 * 60 * 1000);
  // Also run once on startup after a delay
  setTimeout(checkDeviceHealth, 60 * 1000);
}

module.exports = {
  checkDeviceHealth,
  startHealthMonitor,
};
