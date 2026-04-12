"use strict";

const { Pool } = require("pg");

const dbUrl = process.env.DATABASE_URL || "";

const pool = dbUrl
  ? new Pool({
      connectionString: dbUrl,
      ssl: process.env.PGSSL === "true" ? { rejectUnauthorized: false } : false,
    })
  : null;

async function query(text, params) {
  if (!pool) {
    throw new Error("Database not configured");
  }
  return pool.query(text, params);
}

function ensureDb(req, res) {
  if (!pool) {
    res.status(500).send("DATABASE_URL not configured");
    return false;
  }
  return true;
}

module.exports = {
  pool,
  query,
  ensureDb,
};
