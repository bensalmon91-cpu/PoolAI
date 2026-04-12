"use strict";

const express = require("express");
const crypto = require("crypto");
const path = require("path");
const fs = require("fs");
const multer = require("multer");
const { UPLOADS, UPDATES_DIR } = require("../config");
const { pool, ensureDb, query } = require("../db");
const { upsertDeviceFromProvision } = require("../db/queries");
const { requireDeviceAuth, ensureBootstrapSecret } = require("../middleware/auth");
const { normalizeMac, hashToken, generateToken, compareVersions } = require("../utils/helpers");
const { readDevices, writeDevices, loadUpdates, latestUpdate } = require("../utils/devices");

const router = express.Router();

// Device upload storage
const deviceUpload = multer({
  storage: multer.diskStorage({
    destination(req, file, cb) {
      const dir = path.join(UPLOADS, req.device.deviceId);
      fs.mkdirSync(dir, { recursive: true });
      cb(null, dir);
    },
    filename(req, file, cb) {
      const safe = String(file.originalname || "upload")
        .replace(/[^a-zA-Z0-9_.-]/g, "_")
        .slice(0, 120);
      cb(null, `${Date.now()}-${safe}`);
    },
  }),
  limits: { fileSize: 20 * 1024 * 1024 },
});

// Device provisioning
router.post("/api/provision", ensureBootstrapSecret, (req, res) => {
  const mac = normalizeMac(req.body.mac);
  const hostname = String(req.body.hostname || "").trim();
  const model = String(req.body.model || "").trim();
  const softwareVersion = String(req.body.softwareVersion || "").trim();

  if (!mac || mac.length < 11) {
    return res.status(400).send("Invalid MAC address");
  }

  const devices = readDevices();
  let device = devices.find((d) => d.mac === mac);

  if (!device) {
    device = {
      deviceId: crypto.randomUUID(),
      mac,
      createdAt: new Date().toISOString(),
    };
    devices.push(device);
  }

  const token = generateToken();
  device.tokenHash = hashToken(token);
  device.hostname = hostname || device.hostname || "";
  device.model = model || device.model || "";
  device.softwareVersion = softwareVersion || device.softwareVersion || "";
  device.lastSeenAt = new Date().toISOString();

  writeDevices(devices);

  // Also upsert to database if available
  if (pool) {
    upsertDeviceFromProvision(device.deviceId, {
      mac,
      hostname,
      model,
      softwareVersion,
    }).catch(() => null);
  }

  return res.json({
    deviceId: device.deviceId,
    token,
  });
});

// Device file upload
router.post("/api/device/upload", requireDeviceAuth, deviceUpload.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).send("No file uploaded");
  }
  return res.status(200).send("Device upload received");
});

// Device readings
router.post("/api/device/readings", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const rows = Array.isArray(req.body.rows) ? req.body.rows : [];
  if (!rows.length) {
    return res.status(400).send("No readings provided");
  }
  if (rows.length > 2000) {
    return res.status(400).send("Batch too large");
  }

  const deviceId = req.device.deviceId;
  const values = [];
  const placeholders = [];
  let idx = 1;

  for (const row of rows) {
    if (!row || !row.ts || !row.point_label) continue;

    placeholders.push(
      `($${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++})`
    );
    values.push(
      deviceId,
      row.ts,
      row.pool || null,
      row.host || null,
      row.system_name || null,
      row.serial_number || null,
      row.point_label,
      row.value !== undefined ? row.value : null,
      row.raw_type || null
    );
  }

  if (!placeholders.length) {
    return res.status(400).send("No valid readings provided");
  }

  try {
    await query(
      `INSERT INTO device_readings
       (device_id, ts, pool, host, system_name, serial_number, point_label, value, raw_type)
       VALUES ${placeholders.join(", ")}`,
      values
    );
    await query("UPDATE devices SET last_seen_at = NOW() WHERE device_id = $1", [deviceId]);
    res.status(200).send("Readings stored");
  } catch (err) {
    res.status(500).send("Failed to store readings");
  }
});

// Device alarms
router.post("/api/device/alarms", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const rows = Array.isArray(req.body.rows) ? req.body.rows : [];
  if (!rows.length) {
    return res.status(400).send("No alarms provided");
  }
  if (rows.length > 2000) {
    return res.status(400).send("Batch too large");
  }

  const deviceId = req.device.deviceId;
  const values = [];
  const placeholders = [];
  let idx = 1;

  for (const row of rows) {
    if (!row || !row.started_ts || !row.source_label || !row.bit_name) continue;

    placeholders.push(
      `($${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++})`
    );
    values.push(
      deviceId,
      row.started_ts,
      row.ended_ts || null,
      row.pool || null,
      row.host || null,
      row.system_name || null,
      row.serial_number || null,
      row.source_label,
      row.bit_name
    );
  }

  if (!placeholders.length) {
    return res.status(400).send("No valid alarms provided");
  }

  try {
    await query(
      `INSERT INTO device_alarm_events
       (device_id, started_ts, ended_ts, pool, host, system_name, serial_number, source_label, bit_name)
       VALUES ${placeholders.join(", ")}`,
      values
    );
    await query("UPDATE devices SET last_seen_at = NOW() WHERE device_id = $1", [deviceId]);
    res.status(200).send("Alarms stored");
  } catch (err) {
    res.status(500).send("Failed to store alarms");
  }
});

// Device AI findings
router.post("/api/device/ai", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const rows = Array.isArray(req.body.rows) ? req.body.rows : [];
  if (!rows.length) {
    return res.status(400).send("No AI findings provided");
  }
  if (rows.length > 500) {
    return res.status(400).send("Batch too large");
  }

  const deviceId = req.device.deviceId;
  const values = [];
  const placeholders = [];
  let idx = 1;

  for (const row of rows) {
    if (!row || !row.ts || !row.pool || !row.summary) continue;

    placeholders.push(
      `($${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++}, $${idx++})`
    );
    values.push(
      deviceId,
      row.ts,
      row.pool,
      row.reason || "auto",
      row.summary,
      row.water_quality_grade || null,
      row.reliability_grade || null,
      row.details_json || null
    );
  }

  if (!placeholders.length) {
    return res.status(400).send("No valid AI findings provided");
  }

  try {
    await query(
      `INSERT INTO device_ai_findings
       (device_id, ts, pool, reason, summary, water_quality_grade, reliability_grade, details_json)
       VALUES ${placeholders.join(", ")}`,
      values
    );
    await query("UPDATE devices SET last_seen_at = NOW() WHERE device_id = $1", [deviceId]);
    res.status(200).send("AI findings stored");
  } catch (err) {
    res.status(500).send("Failed to store AI findings");
  }
});

// Device heartbeat
router.post("/api/device/heartbeat", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const deviceId = req.device.deviceId;
  const {
    uptime_seconds,
    disk_used_pct,
    memory_used_pct,
    cpu_temp,
    last_upload_success,
    last_upload_error,
    pending_chunks,
    failed_uploads,
    software_version,
    ip_address,
  } = req.body;

  try {
    await query(
      `INSERT INTO device_health
       (device_id, uptime_seconds, disk_used_pct, memory_used_pct, cpu_temp,
        last_upload_success, last_upload_error, pending_chunks, failed_uploads,
        software_version, ip_address)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
      [
        deviceId,
        uptime_seconds || null,
        disk_used_pct || null,
        memory_used_pct || null,
        cpu_temp || null,
        last_upload_success || null,
        last_upload_error || null,
        pending_chunks || 0,
        failed_uploads || 0,
        software_version || null,
        ip_address || null,
      ]
    );

    await query("UPDATE devices SET last_seen_at = NOW() WHERE device_id = $1", [deviceId]);

    const commands = await query(
      `SELECT id, command_type, payload
       FROM device_commands
       WHERE device_id = $1 AND status = 'pending'
       ORDER BY created_at ASC`,
      [deviceId]
    );

    res.json({ ok: true, commands: commands.rows });
  } catch (err) {
    console.error("Heartbeat error:", err);
    res.status(500).send("Failed to process heartbeat");
  }
});

// Device commands
router.get("/api/device/commands", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const deviceId = req.device.deviceId;

  try {
    const commands = await query(
      `SELECT id, command_type, payload, created_at
       FROM device_commands
       WHERE device_id = $1 AND status = 'pending'
       ORDER BY created_at ASC`,
      [deviceId]
    );

    if (commands.rows.length > 0) {
      const ids = commands.rows.map((c) => c.id);
      await query(
        `UPDATE device_commands
         SET status = 'acknowledged', acknowledged_at = NOW()
         WHERE id = ANY($1)`,
        [ids]
      );
    }

    res.json({ commands: commands.rows });
  } catch (err) {
    res.status(500).send("Failed to fetch commands");
  }
});

router.post("/api/device/commands/:id/complete", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const commandId = Number(req.params.id);
  const deviceId = req.device.deviceId;
  const { success, result } = req.body;

  if (!Number.isFinite(commandId)) {
    return res.status(400).send("Invalid command id");
  }

  try {
    const status = success ? "completed" : "failed";
    await query(
      `UPDATE device_commands
       SET status = $1, completed_at = NOW(), result = $2
       WHERE id = $3 AND device_id = $4`,
      [status, result || null, commandId, deviceId]
    );
    res.json({ ok: true });
  } catch (err) {
    res.status(500).send("Failed to update command");
  }
});

// Device updates
router.get("/api/device/update/check", requireDeviceAuth, (req, res) => {
  const currentVersion = String(req.query.current_version || "");
  const channel = String(req.query.channel || "stable");
  const update = latestUpdate(channel);

  if (!update) {
    return res.json({ update: false });
  }
  if (currentVersion && compareVersions(currentVersion, update.version) >= 0) {
    return res.json({ update: false });
  }

  return res.json({
    update: true,
    id: update.id,
    version: update.version,
    notes: update.notes || "",
    sha256: update.sha256 || "",
    download_url: `/api/device/update/download/${update.id}`,
  });
});

router.get("/api/device/update/download/:id", requireDeviceAuth, (req, res) => {
  const updateId = req.params.id;
  const update = loadUpdates().find((u) => u.id === updateId);

  if (!update || !update.filename) {
    return res.status(404).send("Update not found");
  }

  const filePath = path.join(UPDATES_DIR, update.filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).send("Update file not found");
  }

  return res.download(filePath);
});

module.exports = router;
