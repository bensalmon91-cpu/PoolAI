"use strict";

const { getDeviceByToken } = require("../utils/devices");

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

module.exports = {
  requireAuth,
  requireAdmin,
  requireDeviceAuth,
  ensureBootstrapSecret,
};
