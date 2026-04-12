"use strict";

const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const express = require("express");
const session = require("express-session");
const multer = require("multer");
const dotenv = require("dotenv");
const bcrypt = require("bcryptjs");
const nodemailer = require("nodemailer");
const { Pool } = require("pg");
const PgSession = require("connect-pg-simple")(session);

dotenv.config();

// Validate required environment variables
const requiredEnvVars = ["SESSION_SECRET", "BOOTSTRAP_SECRET"];
const missingVars = requiredEnvVars.filter((v) => !process.env[v] || process.env[v] === "change-this-secret");
if (missingVars.length > 0) {
  console.warn(`Warning: Missing or default environment variables: ${missingVars.join(", ")}`);
  console.warn("Copy .env.example to .env and update the values for production use.");
}

if (!process.env.DATABASE_URL) {
  console.warn("Warning: DATABASE_URL not set. Database features will be disabled.");
}

const app = express();
const PORT = process.env.PORT || 3000;
const ROOT = path.join(__dirname, "..");
const PAGES = path.join(ROOT, "pages");
const CSS = path.join(ROOT, "css");
const JS = path.join(ROOT, "js");
const UPLOADS = path.join(ROOT, "uploads");
const DATA_DIR = path.join(__dirname, "data");
const DEVICES_FILE = path.join(DATA_DIR, "devices.json");
const UPDATES_DIR = path.join(__dirname, "updates");
const UPDATES_FILE = path.join(DATA_DIR, "updates.json");

if (!fs.existsSync(UPLOADS)) {
  fs.mkdirSync(UPLOADS, { recursive: true });
}
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}
if (!fs.existsSync(UPDATES_DIR)) {
  fs.mkdirSync(UPDATES_DIR, { recursive: true });
}

const dbUrl = process.env.DATABASE_URL || "";
const pool = dbUrl
  ? new Pool({
      connectionString: dbUrl,
      ssl: process.env.PGSSL === "true" ? { rejectUnauthorized: false } : false,
    })
  : null;

function ensureDb(req, res) {
  if (!pool) {
    res.status(500).send("DATABASE_URL not configured");
    return false;
  }
  return true;
}

const sessionStore = pool
  ? new PgSession({
      pool,
      createTableIfMissing: true,
    })
  : undefined;

const portalUpload = multer({
  dest: UPLOADS,
  limits: {
    fileSize: 20 * 1024 * 1024,
  },
});

app.use(express.urlencoded({ extended: true }));
app.use(express.json());
const isProduction = process.env.NODE_ENV === "production";

app.use(
  session({
    store: sessionStore,
    secret: process.env.SESSION_SECRET || "change-me",
    resave: false,
    saveUninitialized: false,
    cookie: {
      httpOnly: true,
      sameSite: "lax",
      secure: isProduction,
      maxAge: 24 * 60 * 60 * 1000, // 24 hours
    },
  })
);

// Trust proxy in production (for secure cookies behind reverse proxy)
if (isProduction) {
  app.set("trust proxy", 1);
}

app.use("/css", express.static(CSS));
app.use("/js", express.static(JS));

function readDevices() {
  try {
    if (!fs.existsSync(DEVICES_FILE)) {
      return [];
    }
    const raw = fs.readFileSync(DEVICES_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

function writeDevices(devices) {
  fs.writeFileSync(DEVICES_FILE, JSON.stringify(devices, null, 2), "utf8");
}

function loadUpdates() {
  try {
    if (!fs.existsSync(UPDATES_FILE)) {
      return [];
    }
    const raw = fs.readFileSync(UPDATES_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

function parseVersion(raw) {
  if (!raw) {
    return [];
  }
  return String(raw)
    .trim()
    .split(".")
    .map((part) => Number(part))
    .map((n) => (Number.isFinite(n) ? n : 0));
}

function compareVersions(a, b) {
  const va = parseVersion(a);
  const vb = parseVersion(b);
  const len = Math.max(va.length, vb.length);
  for (let i = 0; i < len; i += 1) {
    const av = va[i] || 0;
    const bv = vb[i] || 0;
    if (av > bv) {
      return 1;
    }
    if (av < bv) {
      return -1;
    }
  }
  return 0;
}

function latestUpdate(channel) {
  const updates = loadUpdates().filter((u) => (u.channel || "stable") === channel);
  if (!updates.length) {
    return null;
  }
  return updates.reduce((latest, item) => {
    if (!latest) {
      return item;
    }
    return compareVersions(item.version, latest.version) > 0 ? item : latest;
  }, null);
}

function normalizeMac(mac) {
  return (
    String(mac || "")
      .trim()
      .toLowerCase()
      .replace(/[^0-9a-f]/g, "")
      .match(/.{1,2}/g)
      ?.join(":") || ""
  );
}

function hashToken(token) {
  return crypto.createHash("sha256").update(token).digest("hex");
}

function generateToken() {
  return crypto.randomBytes(32).toString("hex");
}

function getDeviceByToken(token) {
  const tokenHash = hashToken(token);
  const devices = readDevices();
  return devices.find((d) => d.tokenHash === tokenHash);
}

function requireDeviceAuth(req, res, next) {
  const header = req.header("authorization") || "";
  const bearer = header.toLowerCase().startsWith("bearer ") ? header.slice(7) : "";
  const token = bearer || req.header("x-device-token") || "";
  if (!token) {
    return res.status(401).send("Missing device token");
  }
  const device = getDeviceByToken(token);
  if (!device) {
    return res.status(401).send("Invalid device token");
  }
  req.device = device;
  return next();
}

function ensureBootstrapSecret(req, res, next) {
  const expected = process.env.BOOTSTRAP_SECRET || "";
  if (!expected) {
    return res.status(500).send("Bootstrap secret not configured");
  }
  const provided = req.header("x-bootstrap-secret") || "";
  if (provided !== expected) {
    return res.status(403).send("Invalid bootstrap secret");
  }
  return next();
}

function requireAuth(req, res, next) {
  if (req.session && req.session.user) {
    return next();
  }
  return res.redirect("/pages/login.html");
}

function requireAdmin(req, res, next) {
  if (req.session && req.session.user && req.session.user.isAdmin) {
    return next();
  }
  return res.status(403).send("Admin access required");
}

async function query(text, params) {
  if (!pool) {
    throw new Error("Database not configured");
  }
  return pool.query(text, params);
}

async function findUserByEmail(email) {
  const result = await query(
    "SELECT id, email, password_hash, account_id, is_admin FROM users WHERE email = $1",
    [email]
  );
  return result.rows[0] || null;
}

async function findUserById(id) {
  const result = await query(
    "SELECT id, email, password_hash, account_id, is_admin FROM users WHERE id = $1",
    [id]
  );
  return result.rows[0] || null;
}

async function createAccount(name) {
  const result = await query(
    "INSERT INTO accounts (name, contact_name, contact_email, contact_phone, address) VALUES ($1, $2, $3, $4, $5) RETURNING id, name",
    [name, null, null, null, null]
  );
  return result.rows[0];
}

async function createAccountWithDetails(payload) {
  const result = await query(
    `INSERT INTO accounts (name, contact_name, contact_email, contact_phone, address)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, name, contact_name, contact_email, contact_phone, address`,
    [
      payload.name,
      payload.contact_name || null,
      payload.contact_email || null,
      payload.contact_phone || null,
      payload.address || null,
    ]
  );
  return result.rows[0];
}

async function updateAccount(accountId, payload) {
  const result = await query(
    `UPDATE accounts
     SET name = $2,
         contact_name = $3,
         contact_email = $4,
         contact_phone = $5,
         address = $6
     WHERE id = $1
     RETURNING id, name, contact_name, contact_email, contact_phone, address`,
    [
      accountId,
      payload.name,
      payload.contact_name || null,
      payload.contact_email || null,
      payload.contact_phone || null,
      payload.address || null,
    ]
  );
  return result.rows[0];
}

async function createPool(payload) {
  const result = await query(
    `INSERT INTO pools (account_id, name, location, notes)
     VALUES ($1, $2, $3, $4)
     RETURNING id, account_id, name, location, notes`,
    [payload.account_id, payload.name, payload.location || null, payload.notes || null]
  );
  return result.rows[0];
}

async function updatePool(poolId, payload) {
  const result = await query(
    `UPDATE pools
     SET name = $2,
         location = $3,
         notes = $4
     WHERE id = $1
     RETURNING id, account_id, name, location, notes`,
    [poolId, payload.name, payload.location || null, payload.notes || null]
  );
  return result.rows[0];
}

async function upsertDeviceFromProvision(deviceId, payload) {
  const result = await query(
    `INSERT INTO devices (device_id, mac, hostname, model, software_version, last_seen_at)
     VALUES ($1, $2, $3, $4, $5, NOW())
     ON CONFLICT (device_id) DO UPDATE
       SET mac = EXCLUDED.mac,
           hostname = EXCLUDED.hostname,
           model = EXCLUDED.model,
           software_version = EXCLUDED.software_version,
           last_seen_at = NOW()
     RETURNING id, device_id`,
    [
      deviceId,
      payload.mac || null,
      payload.hostname || null,
      payload.model || null,
      payload.softwareVersion || null,
    ]
  );
  return result.rows[0];
}

async function updateDeviceAssignment(deviceId, payload) {
  const result = await query(
    `UPDATE devices
     SET account_id = $2,
         pool_id = $3
     WHERE device_id = $1
     RETURNING id, device_id, account_id, pool_id`,
    [deviceId, payload.account_id || null, payload.pool_id || null]
  );
  return result.rows[0];
}

async function createUser(email, password, accountId, isAdmin) {
  const hash = await bcrypt.hash(password, 12);
  const result = await query(
    "INSERT INTO users (email, password_hash, account_id, is_admin) VALUES ($1, $2, $3, $4) RETURNING id, email, account_id, is_admin",
    [email, hash, accountId, Boolean(isAdmin)]
  );
  return result.rows[0];
}

async function createPasswordReset(userId) {
  const token = generateToken();
  const tokenHash = hashToken(token);
  const expiresAt = new Date(Date.now() + 60 * 60 * 1000);
  await query(
    "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
    [userId, tokenHash, expiresAt]
  );
  return token;
}

async function verifyPasswordReset(token) {
  const tokenHash = hashToken(token);
  const result = await query(
    "SELECT id, user_id, expires_at, used_at FROM password_resets WHERE token_hash = $1 ORDER BY created_at DESC LIMIT 1",
    [tokenHash]
  );
  const row = result.rows[0];
  if (!row) {
    return null;
  }
  if (row.used_at) {
    return null;
  }
  if (new Date(row.expires_at) < new Date()) {
    return null;
  }
  return row;
}

async function markPasswordResetUsed(id) {
  await query("UPDATE password_resets SET used_at = NOW() WHERE id = $1", [id]);
}

async function sendResetEmail(to, token) {
  const baseUrl = process.env.APP_BASE_URL || "";
  const link = baseUrl ? `${baseUrl.replace(/\\/$/, "")}/pages/reset.html?token=${token}` : "";

  const host = process.env.SMTP_HOST || "";
  if (!host) {
    console.log("Password reset link (SMTP not configured):", link || token);
    return;
  }

  const transporter = nodemailer.createTransport({
    host,
    port: Number(process.env.SMTP_PORT || 587),
    secure: false,
    auth: {
      user: process.env.SMTP_USER || "",
      pass: process.env.SMTP_PASS || "",
    },
  });

  const from = process.env.SMTP_FROM || "no-reply@pooldash.example.com";
  const subject = "PoolDash password reset";
  const text = link ? `Reset your password: ${link}` : `Reset token: ${token}`;

  await transporter.sendMail({ from, to, subject, text });
}

// Alert email configuration
const ALERT_EMAIL = process.env.ALERT_EMAIL || "";
const DEVICE_OFFLINE_MINUTES = 30; // Consider offline after 30 minutes
let lastAlertSent = {}; // Track when we last sent alerts to avoid spam

async function sendAlertEmail(subject, body) {
  if (!ALERT_EMAIL) {
    console.log("Alert (no ALERT_EMAIL configured):", subject);
    return;
  }

  const host = process.env.SMTP_HOST || "";
  if (!host) {
    console.log("Alert (SMTP not configured):", subject, body);
    return;
  }

  try {
    const transporter = nodemailer.createTransport({
      host,
      port: Number(process.env.SMTP_PORT || 587),
      secure: false,
      auth: {
        user: process.env.SMTP_USER || "",
        pass: process.env.SMTP_PASS || "",
      },
    });

    const from = process.env.SMTP_FROM || "alerts@pooldash.example.com";
    await transporter.sendMail({ from, to: ALERT_EMAIL, subject, text: body });
    console.log("Alert email sent:", subject);
  } catch (err) {
    console.error("Failed to send alert email:", err);
  }
}

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

// Run health check every 15 minutes
setInterval(checkDeviceHealth, 15 * 60 * 1000);
// Also run once on startup after a delay
setTimeout(checkDeviceHealth, 60 * 1000);

app.get("/", (req, res) => {
  res.sendFile(path.join(ROOT, "index.html"));
});

app.get("/index.html", (req, res) => {
  res.sendFile(path.join(ROOT, "index.html"));
});

app.get("/pages/advertising.html", (req, res) => {
  res.sendFile(path.join(PAGES, "advertising.html"));
});

app.get("/pages/login.html", (req, res) => {
  res.sendFile(path.join(PAGES, "login.html"));
});

app.get("/pages/forgot.html", (req, res) => {
  res.sendFile(path.join(PAGES, "forgot.html"));
});

app.get("/pages/reset.html", (req, res) => {
  res.sendFile(path.join(PAGES, "reset.html"));
});

app.get("/pages/account.html", requireAuth, (req, res) => {
  res.sendFile(path.join(PAGES, "account.html"));
});

app.get("/account", requireAuth, (req, res) => {
  res.sendFile(path.join(PAGES, "account.html"));
});

app.get("/admin", requireAuth, requireAdmin, (req, res) => {
  res.sendFile(path.join(PAGES, "admin.html"));
});

app.get("/portal", requireAuth, (req, res) => {
  res.sendFile(path.join(PAGES, "portal.html"));
});

app.post("/api/login", async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  if (!email || !password) {
    res.status(400).send("Email and password required");
    return;
  }
  try {
    const user = await findUserByEmail(email);
    if (!user) {
      res.status(401).send("Invalid credentials");
      return;
    }
    const ok = await bcrypt.compare(password, user.password_hash);
    if (!ok) {
      res.status(401).send("Invalid credentials");
      return;
    }
    req.session.user = {
      id: user.id,
      email: user.email,
      accountId: user.account_id,
      isAdmin: user.is_admin,
    };
    res.redirect(303, "/portal");
  } catch (err) {
    res.status(500).send("Login failed");
  }
});

app.post("/api/logout", (req, res) => {
  req.session.destroy(() => {
    res.redirect("/pages/login.html");
  });
});

app.post("/api/password/forgot", async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const email = (req.body.email || "").trim().toLowerCase();
  if (!email) {
    res.status(400).send("Email required");
    return;
  }
  try {
    const user = await findUserByEmail(email);
    if (user) {
      const token = await createPasswordReset(user.id);
      await sendResetEmail(user.email, token);
    }
    res.status(200).send("If the account exists, a reset email has been sent.");
  } catch (err) {
    res.status(500).send("Password reset failed");
  }
});

app.post("/api/password/reset", async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const token = (req.body.token || "").trim();
  const password = req.body.password || "";
  if (!token || !password) {
    res.status(400).send("Token and password required");
    return;
  }
  try {
    const reset = await verifyPasswordReset(token);
    if (!reset) {
      res.status(400).send("Invalid or expired token");
      return;
    }
    const user = await findUserById(reset.user_id);
    if (!user) {
      res.status(400).send("Invalid token");
      return;
    }
    const hash = await bcrypt.hash(password, 12);
    await query("UPDATE users SET password_hash = $1 WHERE id = $2", [hash, user.id]);
    await markPasswordResetUsed(reset.id);
    res.status(200).send("Password updated. You can now log in.");
  } catch (err) {
    res.status(500).send("Password reset failed");
  }
});

app.post("/api/upload", requireAuth, portalUpload.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).send("No file uploaded");
  }
  return res.status(200).send("Upload received");
});

app.post("/api/provision", ensureBootstrapSecret, (req, res) => {
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
  limits: {
    fileSize: 20 * 1024 * 1024,
  },
});

app.post("/api/device/upload", requireDeviceAuth, deviceUpload.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).send("No file uploaded");
  }
  return res.status(200).send("Device upload received");
});

app.post("/api/device/readings", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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
    if (!row || !row.ts || !row.point_label) {
      continue;
    }
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

app.post("/api/device/alarms", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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
    if (!row || !row.started_ts || !row.source_label || !row.bit_name) {
      continue;
    }
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

app.post("/api/device/ai", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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
    if (!row || !row.ts || !row.pool || !row.summary) {
      continue;
    }
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

app.get("/api/portal/pools", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const accountId = req.session.user && req.session.user.accountId;
  if (!accountId) {
    return res.json([]);
  }
  try {
    const result = await query(
      "SELECT id, name, location, notes FROM pools WHERE account_id = $1 ORDER BY name",
      [accountId]
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to load pools");
  }
});

app.get("/api/portal/pool/:id/latest", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const accountId = req.session.user && req.session.user.accountId;
  const poolId = Number(req.params.id);
  if (!accountId || !Number.isFinite(poolId)) {
    return res.status(400).send("Invalid pool");
  }
  try {
    const devices = await query(
      "SELECT device_id FROM devices WHERE account_id = $1 AND pool_id = $2",
      [accountId, poolId]
    );
    const ids = devices.rows.map((r) => r.device_id);
    if (!ids.length) {
      return res.json({ values: [] });
    }
    const labels = [
      "pH_MeasuredValue",
      "Chlorine_MeasuredValue",
      "ORP_MeasuredValue",
      "Temp_MeasuredValue",
    ];
    const result = await query(
      `SELECT r.point_label, r.value, r.ts
       FROM device_readings r
       JOIN (
         SELECT point_label, MAX(ts) AS max_ts
         FROM device_readings
         WHERE device_id = ANY($1) AND point_label = ANY($2)
         GROUP BY point_label
       ) m
       ON r.point_label = m.point_label AND r.ts = m.max_ts
       WHERE r.device_id = ANY($1)
       ORDER BY r.point_label`,
      [ids, labels]
    );
    res.json({ values: result.rows });
  } catch (err) {
    res.status(500).send("Failed to load latest readings");
  }
});

app.get("/api/portal/pool/:id/alarms", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const accountId = req.session.user && req.session.user.accountId;
  const poolId = Number(req.params.id);
  if (!accountId || !Number.isFinite(poolId)) {
    return res.status(400).send("Invalid pool");
  }
  try {
    const devices = await query(
      "SELECT device_id FROM devices WHERE account_id = $1 AND pool_id = $2",
      [accountId, poolId]
    );
    const ids = devices.rows.map((r) => r.device_id);
    if (!ids.length) {
      return res.json({ open: [], recent: [] });
    }
    const open = await query(
      `SELECT started_ts, pool, source_label, bit_name
       FROM device_alarm_events
       WHERE device_id = ANY($1) AND ended_ts IS NULL
       ORDER BY started_ts DESC
       LIMIT 50`,
      [ids]
    );
    const recent = await query(
      `SELECT started_ts, ended_ts, pool, source_label, bit_name
       FROM device_alarm_events
       WHERE device_id = ANY($1)
       ORDER BY started_ts DESC
       LIMIT 100`,
      [ids]
    );
    res.json({ open: open.rows, recent: recent.rows });
  } catch (err) {
    res.status(500).send("Failed to load alarms");
  }
});

app.get("/api/portal/pool/:id/ai", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const accountId = req.session.user && req.session.user.accountId;
  const poolId = Number(req.params.id);
  if (!accountId || !Number.isFinite(poolId)) {
    return res.status(400).send("Invalid pool");
  }
  try {
    const devices = await query(
      "SELECT device_id FROM devices WHERE account_id = $1 AND pool_id = $2",
      [accountId, poolId]
    );
    const ids = devices.rows.map((r) => r.device_id);
    if (!ids.length) {
      return res.json({ findings: [] });
    }
    const result = await query(
      `SELECT ts, reason, summary, water_quality_grade, reliability_grade
       FROM device_ai_findings
       WHERE device_id = ANY($1)
       ORDER BY ts DESC
       LIMIT 20`,
      [ids]
    );
    res.json({ findings: result.rows });
  } catch (err) {
    res.status(500).send("Failed to load AI findings");
  }
});

app.get("/api/portal/pool/:id/recent", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const accountId = req.session.user && req.session.user.accountId;
  const poolId = Number(req.params.id);
  if (!accountId || !Number.isFinite(poolId)) {
    return res.status(400).send("Invalid pool");
  }
  const limit = Math.min(500, Math.max(50, Number(req.query.limit || 200)));
  try {
    const devices = await query(
      "SELECT device_id FROM devices WHERE account_id = $1 AND pool_id = $2",
      [accountId, poolId]
    );
    const ids = devices.rows.map((r) => r.device_id);
    if (!ids.length) {
      return res.json({ rows: [] });
    }
    const labels = [
      "pH_MeasuredValue",
      "Chlorine_MeasuredValue",
      "ORP_MeasuredValue",
      "Temp_MeasuredValue",
    ];
    const result = await query(
      `SELECT ts, point_label, value
       FROM device_readings
       WHERE device_id = ANY($1) AND point_label = ANY($2)
       ORDER BY ts DESC
       LIMIT $3`,
      [ids, labels, limit]
    );
    res.json({ rows: result.rows });
  } catch (err) {
    res.status(500).send("Failed to load recent readings");
  }
});

// Device heartbeat - receives health status from devices
app.post("/api/device/heartbeat", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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
    // Insert health record
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

    // Update last_seen_at
    await query("UPDATE devices SET last_seen_at = NOW() WHERE device_id = $1", [deviceId]);

    // Check for pending commands
    const commands = await query(
      `SELECT id, command_type, payload
       FROM device_commands
       WHERE device_id = $1 AND status = 'pending'
       ORDER BY created_at ASC`,
      [deviceId]
    );

    res.json({
      ok: true,
      commands: commands.rows,
    });
  } catch (err) {
    console.error("Heartbeat error:", err);
    res.status(500).send("Failed to process heartbeat");
  }
});

// Device polls for pending commands
app.get("/api/device/commands", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const deviceId = req.device.deviceId;

  try {
    const commands = await query(
      `SELECT id, command_type, payload, created_at
       FROM device_commands
       WHERE device_id = $1 AND status = 'pending'
       ORDER BY created_at ASC`,
      [deviceId]
    );

    // Mark commands as acknowledged
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

// Device reports command completion
app.post("/api/device/commands/:id/complete", requireDeviceAuth, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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

app.get("/api/device/update/check", requireDeviceAuth, (req, res) => {
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

app.get("/api/device/update/download/:id", requireDeviceAuth, (req, res) => {
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

app.get("/api/admin/users", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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

app.post("/api/admin/users", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  const accountName = (req.body.accountName || "").trim();
  const accountIdRaw = req.body.accountId;
  const isAdmin = String(req.body.isAdmin || "").toLowerCase() === "true";

  if (!email || !password) {
    res.status(400).send("Email and password required");
    return;
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

app.get("/api/admin/accounts", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  try {
    const result = await query(
      "SELECT id, name, contact_name, contact_email, contact_phone, address, created_at FROM accounts ORDER BY created_at DESC"
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).send("Failed to list accounts");
  }
});

app.post("/api/admin/accounts", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const name = (req.body.name || "").trim();
  if (!name) {
    res.status(400).send("Account name required");
    return;
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

app.post("/api/admin/accounts/:id", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const accountId = Number(req.params.id);
  if (!Number.isFinite(accountId)) {
    res.status(400).send("Invalid account id");
    return;
  }
  const name = (req.body.name || "").trim();
  if (!name) {
    res.status(400).send("Account name required");
    return;
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

app.get("/api/admin/pools", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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

app.post("/api/admin/pools", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const accountId = Number(req.body.account_id);
  const name = (req.body.name || "").trim();
  if (!Number.isFinite(accountId) || !name) {
    res.status(400).send("Account and pool name required");
    return;
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

app.post("/api/admin/pools/:id", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const poolId = Number(req.params.id);
  const name = (req.body.name || "").trim();
  if (!Number.isFinite(poolId) || !name) {
    res.status(400).send("Pool id and name required");
    return;
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

app.get("/api/admin/devices", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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

app.post("/api/admin/devices/:id", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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

// Get device health status for all devices
app.get("/api/admin/devices/health", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  try {
    // Get latest health record for each device
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

    // Calculate online status (device seen in last 20 minutes)
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

// Get health history for a specific device
app.get("/api/admin/devices/:id/health-history", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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

// Request device to upload data now
app.post("/api/admin/devices/:id/request-upload", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
  const deviceId = req.params.id;

  try {
    // Check if there's already a pending upload command
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

    // Create new upload command
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

// Get command history for a device
app.get("/api/admin/devices/:id/commands", requireAuth, requireAdmin, async (req, res) => {
  if (!ensureDb(req, res)) {
    return;
  }
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

app.listen(PORT, () => {
  console.log(`PoolDash_v6 backend running on http://localhost:${PORT}`);
});
