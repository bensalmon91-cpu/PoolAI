"use strict";

const express = require("express");
const path = require("path");
const { ROOT, PAGES } = require("../config");
const { requireAuth, requireAdmin } = require("../middleware/auth");

const router = express.Router();

// Public pages
router.get("/", (req, res) => {
  res.sendFile(path.join(ROOT, "index.html"));
});

router.get("/index.html", (req, res) => {
  res.sendFile(path.join(ROOT, "index.html"));
});

router.get("/pages/advertising.html", (req, res) => {
  res.sendFile(path.join(PAGES, "advertising.html"));
});

router.get("/pages/login.html", (req, res) => {
  res.sendFile(path.join(PAGES, "login.html"));
});

router.get("/pages/forgot.html", (req, res) => {
  res.sendFile(path.join(PAGES, "forgot.html"));
});

router.get("/pages/reset.html", (req, res) => {
  res.sendFile(path.join(PAGES, "reset.html"));
});

// Protected pages
router.get("/pages/account.html", requireAuth, (req, res) => {
  res.sendFile(path.join(PAGES, "account.html"));
});

router.get("/account", requireAuth, (req, res) => {
  res.sendFile(path.join(PAGES, "account.html"));
});

router.get("/admin", requireAuth, requireAdmin, (req, res) => {
  res.sendFile(path.join(PAGES, "admin.html"));
});

router.get("/portal", requireAuth, (req, res) => {
  res.sendFile(path.join(PAGES, "portal.html"));
});

module.exports = router;
