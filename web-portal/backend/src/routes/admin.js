"use strict";

const express = require("express");
const { ensureDb, query } = require("../db");
const {
  createUser,
  createAccount,
  createAccountWithDetails,
  updateAccount,
  createPool,
  updatePool,
  updateDeviceAssignment,
} = require("../db/queries");
const { requireAuth, requireAdmin } = require("../middleware/auth");

const router = express.Router();

// Users
router.get("/api/admin/users", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  try {
    const result = await query(
      `SELECT u.id, u.email, u.is_admin, u.created_at, a.name AS account_name
       FROM users u
       LEFT JOIN accounts a ON u.account_id = a.id
       ORDER BY u.created_at DESC`
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to list users");
  }
});

router.post("/api/admin/users", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  const accountName = (req.body.accountName || "").trim();
  const accountIdRaw = req.body.accountId;
  const isAdmin = String(req.body.isAdmin || "").toLowerCase() === "true";

  if (!email || !password) {
    return res.status(400).send("Email and password required");
  }

  try {
    let accountId = null;
    if (accountIdRaw) {
      const parsed = Number(accountIdRaw);
      if (Number.isFinite(parsed)) {
        accountId = parsed;
      }
    }
    if (!accountId && accountName) {
      const account = await createAccount(accountName);
      accountId = account.id;
    }
    const user = await createUser(email, password, accountId, isAdmin);
    res.json(user);
  } catch (err) {
    res.status(500).send("Failed to create user");
  }
});

// Accounts
router.get("/api/admin/accounts", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  try {
    const result = await query(
      "SELECT id, name, contact_name, contact_email, contact_phone, address, created_at FROM accounts ORDER BY created_at DESC"
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to list accounts");
  }
});

router.post("/api/admin/accounts", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const name = (req.body.name || "").trim();
  if (!name) {
    return res.status(400).send("Account name required");
  }

  try {
    const account = await createAccountWithDetails({
      name,
      contact_name: (req.body.contact_name || "").trim(),
      contact_email: (req.body.contact_email || "").trim(),
      contact_phone: (req.body.contact_phone || "").trim(),
      address: (req.body.address || "").trim(),
    });
    res.json(account);
  } catch (err) {
    res.status(500).send("Failed to create account");
  }
});

router.post("/api/admin/accounts/:id", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const accountId = Number(req.params.id);
  if (!Number.isFinite(accountId)) {
    return res.status(400).send("Invalid account id");
  }

  const name = (req.body.name || "").trim();
  if (!name) {
    return res.status(400).send("Account name required");
  }

  try {
    const account = await updateAccount(accountId, {
      name,
      contact_name: (req.body.contact_name || "").trim(),
      contact_email: (req.body.contact_email || "").trim(),
      contact_phone: (req.body.contact_phone || "").trim(),
      address: (req.body.address || "").trim(),
    });
    res.json(account);
  } catch (err) {
    res.status(500).send("Failed to update account");
  }
});

// Pools
router.get("/api/admin/pools", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  try {
    const result = await query(
      `SELECT p.id, p.name, p.location, p.notes, p.created_at, p.account_id, a.name AS account_name
       FROM pools p
       JOIN accounts a ON p.account_id = a.id
       ORDER BY p.created_at DESC`
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to list pools");
  }
});

router.post("/api/admin/pools", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const accountId = Number(req.body.account_id);
  const name = (req.body.name || "").trim();

  if (!Number.isFinite(accountId) || !name) {
    return res.status(400).send("Account and pool name required");
  }

  try {
    const poolRow = await createPool({
      account_id: accountId,
      name,
      location: (req.body.location || "").trim(),
      notes: (req.body.notes || "").trim(),
    });
    res.json(poolRow);
  } catch (err) {
    res.status(500).send("Failed to create pool");
  }
});

router.post("/api/admin/pools/:id", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const poolId = Number(req.params.id);
  const name = (req.body.name || "").trim();

  if (!Number.isFinite(poolId) || !name) {
    return res.status(400).send("Pool id and name required");
  }

  try {
    const poolRow = await updatePool(poolId, {
      name,
      location: (req.body.location || "").trim(),
      notes: (req.body.notes || "").trim(),
    });
    res.json(poolRow);
  } catch (err) {
    res.status(500).send("Failed to update pool");
  }
});

// Devices
router.get("/api/admin/devices", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  try {
    const result = await query(
      `SELECT d.device_id, d.mac, d.hostname, d.model, d.software_version, d.last_seen_at,
              d.account_id, d.pool_id,
              a.name AS account_name, p.name AS pool_name
       FROM devices d
       LEFT JOIN accounts a ON d.account_id = a.id
       LEFT JOIN pools p ON d.pool_id = p.id
       ORDER BY d.created_at DESC`
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to list devices");
  }
});

router.post("/api/admin/devices/:id", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const deviceId = req.params.id;
  const accountId = req.body.account_id ? Number(req.body.account_id) : null;
  const poolId = req.body.pool_id ? Number(req.body.pool_id) : null;

  try {
    const deviceRow = await updateDeviceAssignment(deviceId, {
      account_id: Number.isFinite(accountId) ? accountId : null,
      pool_id: Number.isFinite(poolId) ? poolId : null,
    });
    res.json(deviceRow);
  } catch (err) {
    res.status(500).send("Failed to update device assignment");
  }
});

// Device health
router.get("/api/admin/devices/health", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  try {
    const result = await query(
      `SELECT DISTINCT ON (h.device_id)
              h.device_id, h.ts as health_ts, h.uptime_seconds, h.disk_used_pct,
              h.memory_used_pct, h.cpu_temp, h.last_upload_success, h.last_upload_error,
              h.pending_chunks, h.failed_uploads, h.software_version, h.ip_address,
              d.hostname, d.mac, d.last_seen_at, d.account_id, d.pool_id,
              a.name as account_name, p.name as pool_name
       FROM device_health h
       JOIN devices d ON h.device_id = d.device_id
       LEFT JOIN accounts a ON d.account_id = a.id
       LEFT JOIN pools p ON d.pool_id = p.id
       ORDER BY h.device_id, h.ts DESC`
    );

    const now = new Date();
    const devices = result.rows.map((d) => {
      const lastSeen = d.last_seen_at ? new Date(d.last_seen_at) : null;
      const minutesAgo = lastSeen ? (now - lastSeen) / 60000 : null;
      return {
        ...d,
        is_online: minutesAgo !== null && minutesAgo < 20,
        minutes_since_seen: minutesAgo ? Math.round(minutesAgo) : null,
      };
    });

    res.json(devices);
  } catch (err) {
    console.error("Health fetch error:", err);
    res.status(500).send("Failed to fetch device health");
  }
});

router.get("/api/admin/devices/:id/health-history", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const deviceId = req.params.id;
  const limit = Math.min(1000, Math.max(10, Number(req.query.limit || 100)));

  try {
    const result = await query(
      `SELECT ts, uptime_seconds, disk_used_pct, memory_used_pct, cpu_temp,
              last_upload_success, last_upload_error, pending_chunks, failed_uploads
       FROM device_health
       WHERE device_id = $1
       ORDER BY ts DESC
       LIMIT $2`,
      [deviceId, limit]
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to fetch health history");
  }
});

router.post("/api/admin/devices/:id/request-upload", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const deviceId = req.params.id;

  try {
    const existing = await query(
      `SELECT id FROM device_commands
       WHERE device_id = $1 AND command_type = 'upload' AND status IN ('pending', 'acknowledged')`,
      [deviceId]
    );

    if (existing.rows.length > 0) {
      return res.status(400).json({
        ok: false,
        error: "Upload already requested and pending",
      });
    }

    const result = await query(
      `INSERT INTO device_commands (device_id, command_type, payload)
       VALUES ($1, 'upload', $2)
       RETURNING id, created_at`,
      [deviceId, JSON.stringify({ reason: "admin_request" })]
    );

    res.json({
      ok: true,
      command_id: result.rows[0].id,
      message: "Upload requested. Device will upload on next heartbeat.",
    });
  } catch (err) {
    res.status(500).send("Failed to request upload");
  }
});

router.get("/api/admin/devices/:id/commands", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) return;

  const deviceId = req.params.id;

  try {
    const result = await query(
      `SELECT id, command_type, status, created_at, acknowledged_at, completed_at, result
       FROM device_commands
       WHERE device_id = $1
       ORDER BY created_at DESC
       LIMIT 50`,
      [deviceId]
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to fetch commands");
  }
});

module.exports = router;
