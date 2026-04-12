"use strict";

/**
 * PoolDash Portal Backend
 *
 * Main entry point - configures Express app and mounts route modules.
 * All business logic is in src/ modules.
 */

const express = require("express");
const session = require("express-session");
const dotenv = require("dotenv");
const PgSession = require("connect-pg-simple")(session);

// Load environment variables
dotenv.config();

// Import configuration and modules
const { CSS, JS, PORT, isProduction, validateEnv } = require("./src/config");
const { pool } = require("./src/db");
const { startHealthMonitor } = require("./src/services/health-monitor");
const {
  pagesRouter,
  authRouter,
  deviceRouter,
  portalRouter,
  adminRouter,
} = require("./src/routes");

// Validate environment
validateEnv();

// Create Express app
const app = express();

// Trust proxy in production (for secure cookies behind reverse proxy)
if (isProduction) {
  app.set("trust proxy", 1);
}

// Session store (Postgres-backed if database is configured)
const sessionStore = pool
  ? new PgSession({
      pool,
      createTableIfMissing: true,
    })
  : undefined;

// Middleware
app.use(express.urlencoded({ extended: true }));
app.use(express.json());
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

// Static files
app.use("/css", express.static(CSS));
app.use("/js", express.static(JS));

// Mount routes
app.use(pagesRouter);
app.use(authRouter);
app.use(deviceRouter);
app.use(portalRouter);
app.use(adminRouter);

// Start health monitoring
startHealthMonitor();

// Start server
app.listen(PORT, () => {
  console.log(`PoolDash_v6 backend running on http://localhost:${PORT}`);
  console.log(`Environment: ${isProduction ? "production" : "development"}`);
});
