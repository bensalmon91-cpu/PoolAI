"use strict";

const bcrypt = require("bcryptjs");
const { query } = require("./index");
const { hashToken, generateToken } = require("../utils/helpers");

// User queries
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

async function createUser(email, password, accountId, isAdmin) {
  const hash = await bcrypt.hash(password, 12);
  const result = await query(
    "INSERT INTO users (email, password_hash, account_id, is_admin) VALUES ($1, $2, $3, $4) RETURNING id, email, account_id, is_admin",
    [email, hash, accountId, Boolean(isAdmin)]
  );
  return result.rows[0];
}

// Account queries
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

// Pool queries
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

// Device queries
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

// Password reset queries
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
  if (!row) return null;
  if (row.used_at) return null;
  if (new Date(row.expires_at) < new Date()) return null;
  return row;
}

async function markPasswordResetUsed(id) {
  await query("UPDATE password_resets SET used_at = NOW() WHERE id = $1", [id]);
}

module.exports = {
  findUserByEmail,
  findUserById,
  createUser,
  createAccount,
  createAccountWithDetails,
  updateAccount,
  createPool,
  updatePool,
  upsertDeviceFromProvision,
  updateDeviceAssignment,
  createPasswordReset,
  verifyPasswordReset,
  markPasswordResetUsed,
};
