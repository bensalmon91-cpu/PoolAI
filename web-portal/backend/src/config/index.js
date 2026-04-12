"use strict";

const path = require("path");
const fs = require("fs");

// Directory paths
const ROOT = path.join(__dirname, "..", "..", "..");
const BACKEND = path.join(__dirname, "..", "..");
const PAGES = path.join(ROOT, "pages");
const CSS = path.join(ROOT, "css");
const JS = path.join(ROOT, "js");
const UPLOADS = path.join(ROOT, "uploads");
const DATA_DIR = path.join(BACKEND, "data");
const DEVICES_FILE = path.join(DATA_DIR, "devices.json");
const UPDATES_DIR = path.join(BACKEND, "updates");
const UPDATES_FILE = path.join(DATA_DIR, "updates.json");

// Ensure directories exist
[UPLOADS, DATA_DIR, UPDATES_DIR].forEach((dir) => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
});

// Environment
const isProduction = process.env.NODE_ENV === "production";
const PORT = process.env.PORT || 3000;

// Alert configuration
const ALERT_EMAIL = process.env.ALERT_EMAIL || "";
const DEVICE_OFFLINE_MINUTES = 30;

// Validate required environment variables
function validateEnv() {
  const requiredEnvVars = ["SESSION_SECRET", "BOOTSTRAP_SECRET"];
  const missingVars = requiredEnvVars.filter(
    (v) => !process.env[v] || process.env[v] === "change-this-secret"
  );

  if (missingVars.length > 0) {
    console.warn(`Warning: Missing or default environment variables: ${missingVars.join(", ")}`);
    console.warn("Copy .env.example to .env and update the values for production use.");
  }

  if (!process.env.DATABASE_URL) {
    console.warn("Warning: DATABASE_URL not set. Database features will be disabled.");
  }
}

module.exports = {
  ROOT,
  BACKEND,
  PAGES,
  CSS,
  JS,
  UPLOADS,
  DATA_DIR,
  DEVICES_FILE,
  UPDATES_DIR,
  UPDATES_FILE,
  isProduction,
  PORT,
  ALERT_EMAIL,
  DEVICE_OFFLINE_MINUTES,
  validateEnv,
};
