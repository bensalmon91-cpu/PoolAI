"use strict";

const dotenv = require("dotenv");
const { Pool } = require("pg");

dotenv.config();

async function main() {
  const dbUrl = process.env.DATABASE_URL || "";
  if (!dbUrl) {
    console.error("DATABASE_URL is not configured in .env");
    process.exit(1);
  }

  const retentionDays = Number(process.env.RETENTION_DAYS || "90");
  if (!Number.isFinite(retentionDays) || retentionDays <= 0) {
    console.error("RETENTION_DAYS must be a positive number");
    process.exit(1);
  }

  const pool = new Pool({
    connectionString: dbUrl,
    ssl: process.env.PGSSL === "true" ? { rejectUnauthorized: false } : false,
  });

  try {
    const result = await pool.query(
      "DELETE FROM device_readings WHERE ts < NOW() - ($1 || ' days')::interval",
      [retentionDays]
    );
    console.log(`Deleted ${result.rowCount} readings older than ${retentionDays} days.`);
  } catch (err) {
    console.error("Cleanup failed:", err.message || err);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

main();
