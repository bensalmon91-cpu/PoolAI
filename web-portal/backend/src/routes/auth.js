"use strict";

const express = require("express");
const bcrypt = require("bcryptjs");
const multer = require("multer");
const { UPLOADS } = require("../config");
const { ensureDb, query } = require("../db");
const {
  findUserByEmail,
  findUserById,
  createPasswordReset,
  verifyPasswordReset,
  markPasswordResetUsed,
} = require("../db/queries");
const { requireAuth } = require("../middleware/auth");
const { sendResetEmail } = require("../services/email");

const router = express.Router();

const portalUpload = multer({
  dest: UPLOADS,
  limits: { fileSize: 20 * 1024 * 1024 },
});

router.post("/api/login", async (req, res) => {
  if (!ensureDb(req, res)) return;

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";

  if (!email || !password) {
    return res.status(400).send("Email and password required");
  }

  try {
    const user = await findUserByEmail(email);
    if (!user) {
      return res.status(401).send("Invalid credentials");
    }

    const ok = await bcrypt.compare(password, user.password_hash);
    if (!ok) {
      return res.status(401).send("Invalid credentials");
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

router.post("/api/logout", (req, res) => {
  req.session.destroy(() => {
    res.redirect("/pages/login.html");
  });
});

router.post("/api/password/forgot", async (req, res) => {
  if (!ensureDb(req, res)) return;

  const email = (req.body.email || "").trim().toLowerCase();
  if (!email) {
    return res.status(400).send("Email required");
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

router.post("/api/password/reset", async (req, res) => {
  if (!ensureDb(req, res)) return;

  const token = (req.body.token || "").trim();
  const password = req.body.password || "";

  if (!token || !password) {
    return res.status(400).send("Token and password required");
  }

  try {
    const reset = await verifyPasswordReset(token);
    if (!reset) {
      return res.status(400).send("Invalid or expired token");
    }

    const user = await findUserById(reset.user_id);
    if (!user) {
      return res.status(400).send("Invalid token");
    }

    const hash = await bcrypt.hash(password, 12);
    await query("UPDATE users SET password_hash = $1 WHERE id = $2", [hash, user.id]);
    await markPasswordResetUsed(reset.id);

    res.status(200).send("Password updated. You can now log in.");
  } catch (err) {
    res.status(500).send("Password reset failed");
  }
});

router.post("/api/upload", requireAuth, portalUpload.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).send("No file uploaded");
  }
  return res.status(200).send("Upload received");
});

module.exports = router;
