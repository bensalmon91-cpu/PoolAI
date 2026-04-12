"use strict";

const nodemailer = require("nodemailer");
const { ALERT_EMAIL } = require("../config");

function createTransporter() {
  const host = process.env.SMTP_HOST || "";
  if (!host) return null;

  return nodemailer.createTransport({
    host,
    port: Number(process.env.SMTP_PORT || 587),
    secure: false,
    auth: {
      user: process.env.SMTP_USER || "",
      pass: process.env.SMTP_PASS || "",
    },
  });
}

async function sendResetEmail(to, token) {
  const baseUrl = process.env.APP_BASE_URL || "";
  const link = baseUrl
    ? `${baseUrl.replace(/\/$/, "")}/pages/reset.html?token=${token}`
    : "";

  const transporter = createTransporter();
  if (!transporter) {
    console.log("Password reset link (SMTP not configured):", link || token);
    return;
  }

  const from = process.env.SMTP_FROM || "no-reply@pooldash.example.com";
  const subject = "PoolDash password reset";
  const text = link ? `Reset your password: ${link}` : `Reset token: ${token}`;

  await transporter.sendMail({ from, to, subject, text });
}

async function sendAlertEmail(subject, body) {
  if (!ALERT_EMAIL) {
    console.log("Alert (no ALERT_EMAIL configured):", subject);
    return;
  }

  const transporter = createTransporter();
  if (!transporter) {
    console.log("Alert (SMTP not configured):", subject, body);
    return;
  }

  try {
    const from = process.env.SMTP_FROM || "alerts@pooldash.example.com";
    await transporter.sendMail({ from, to: ALERT_EMAIL, subject, text: body });
    console.log("Alert email sent:", subject);
  } catch (err) {
    console.error("Failed to send alert email:", err);
  }
}

module.exports = {
  sendResetEmail,
  sendAlertEmail,
};
