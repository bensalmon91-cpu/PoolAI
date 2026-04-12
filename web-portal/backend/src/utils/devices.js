"use strict";

const fs = require("fs");
const { DEVICES_FILE, UPDATES_FILE } = require("../config");
const { hashToken } = require("./helpers");
const { compareVersions } = require("./helpers");

function readDevices() {
  try {
    if (!fs.existsSync(DEVICES_FILE)) return [];
    const raw = fs.readFileSync(DEVICES_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

function writeDevices(devices) {
  fs.writeFileSync(DEVICES_FILE, JSON.stringify(devices, null, 2), "utf8");
}

function getDeviceByToken(token) {
  const tokenHash = hashToken(token);
  const devices = readDevices();
  return devices.find((d) => d.tokenHash === tokenHash);
}

function loadUpdates() {
  try {
    if (!fs.existsSync(UPDATES_FILE)) return [];
    const raw = fs.readFileSync(UPDATES_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

function latestUpdate(channel) {
  const updates = loadUpdates().filter((u) => (u.channel || "stable") === channel);
  if (!updates.length) return null;
  return updates.reduce((latest, item) => {
    if (!latest) return item;
    return compareVersions(item.version, latest.version) > 0 ? item : latest;
  }, null);
}

module.exports = {
  readDevices,
  writeDevices,
  getDeviceByToken,
  loadUpdates,
  latestUpdate,
};
