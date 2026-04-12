"use strict";

const crypto = require("crypto");

function normalizeMac(mac) {
  return (
    String(mac || "")
      .trim()
      .toLowerCase()
      .replace(/[^0-9a-f]/g, "")
      .match(/.{1,2}/g)
      ?.join(":") || ""
  );
}

function hashToken(token) {
  return crypto.createHash("sha256").update(token).digest("hex");
}

function generateToken() {
  return crypto.randomBytes(32).toString("hex");
}

function parseVersion(raw) {
  if (!raw) return [];
  return String(raw)
    .trim()
    .split(".")
    .map((part) => Number(part))
    .map((n) => (Number.isFinite(n) ? n : 0));
}

function compareVersions(a, b) {
  const va = parseVersion(a);
  const vb = parseVersion(b);
  const len = Math.max(va.length, vb.length);
  for (let i = 0; i < len; i += 1) {
    const av = va[i] || 0;
    const bv = vb[i] || 0;
    if (av > bv) return 1;
    if (av < bv) return -1;
  }
  return 0;
}

module.exports = {
  normalizeMac,
  hashToken,
  generateToken,
  parseVersion,
  compareVersions,
};
