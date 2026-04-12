"use strict";

const express = require("express");
const { ensureDb, query } = require("../db");
const { requireAuth } = require("../middleware/auth");

const router = express.Router();

router.get("/api/portal/pools", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

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

router.get("/api/portal/pool/:id/latest", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

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

router.get("/api/portal/pool/:id/alarms", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

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

router.get("/api/portal/pool/:id/ai", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

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

router.get("/api/portal/pool/:id/recent", requireAuth, async (req, res) => {
  if (!ensureDb(req, res)) return;

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

module.exports = router;
