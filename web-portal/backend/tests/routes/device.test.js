"use strict";

const request = require("supertest");

// Setup mocks before requiring app
jest.mock("../../src/db", () => ({
  pool: null,
  ensureDb: jest.fn(() => true),
  query: jest.fn(),
}));

jest.mock("../../src/db/queries", () => ({
  upsertDeviceFromProvision: jest.fn(),
}));

jest.mock("../../src/utils/devices", () => ({
  readDevices: jest.fn(() => []),
  writeDevices: jest.fn(),
  getDeviceByToken: jest.fn(),
  loadUpdates: jest.fn(() => []),
  latestUpdate: jest.fn(() => null),
}));

jest.mock("../../src/config", () => ({
  CSS: "/mock/css",
  JS: "/mock/js",
  UPLOADS: "/mock/uploads",
  UPDATES_DIR: "/mock/updates",
  PORT: 3000,
  isProduction: false,
  ALERT_EMAIL: "",
  validateEnv: jest.fn(),
}));

const { ensureDb, query } = require("../../src/db");
const {
  readDevices,
  writeDevices,
  getDeviceByToken,
  latestUpdate,
} = require("../../src/utils/devices");

// Create test app
const express = require("express");
const session = require("express-session");

function createApp() {
  const app = express();
  app.use(express.urlencoded({ extended: true }));
  app.use(express.json());
  app.use(
    session({
      secret: "test-secret",
      resave: false,
      saveUninitialized: false,
    })
  );

  const deviceRouter = require("../../src/routes/device");
  app.use(deviceRouter);
  return app;
}

describe("Device Routes", () => {
  let app;
  const originalEnv = process.env.BOOTSTRAP_SECRET;

  beforeAll(() => {
    app = createApp();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    ensureDb.mockReturnValue(true);
    process.env.BOOTSTRAP_SECRET = "test-bootstrap-secret";
  });

  afterEach(() => {
    process.env.BOOTSTRAP_SECRET = originalEnv;
  });

  describe("POST /api/provision", () => {
    test("returns 500 when bootstrap secret not configured", async () => {
      process.env.BOOTSTRAP_SECRET = "";

      const res = await request(app)
        .post("/api/provision")
        .set("x-bootstrap-secret", "any-secret")
        .send({ mac: "aa:bb:cc:dd:ee:ff" });

      expect(res.status).toBe(500);
      expect(res.text).toBe("Bootstrap secret not configured");
    });

    test("returns 403 when bootstrap secret is wrong", async () => {
      const res = await request(app)
        .post("/api/provision")
        .set("x-bootstrap-secret", "wrong-secret")
        .send({ mac: "aa:bb:cc:dd:ee:ff" });

      expect(res.status).toBe(403);
      expect(res.text).toBe("Invalid bootstrap secret");
    });

    test("returns 400 for invalid MAC address", async () => {
      const res = await request(app)
        .post("/api/provision")
        .set("x-bootstrap-secret", "test-bootstrap-secret")
        .send({ mac: "invalid" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Invalid MAC address");
    });

    test("provisions new device successfully", async () => {
      readDevices.mockReturnValue([]);

      const res = await request(app)
        .post("/api/provision")
        .set("x-bootstrap-secret", "test-bootstrap-secret")
        .send({
          mac: "aa:bb:cc:dd:ee:ff",
          hostname: "test-pi",
          model: "Pi 4",
          softwareVersion: "6.4.0",
        });

      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty("deviceId");
      expect(res.body).toHaveProperty("token");
      expect(res.body.token).toMatch(/^[a-f0-9]{64}$/);
      expect(writeDevices).toHaveBeenCalled();
    });

    test("returns existing device with new token", async () => {
      readDevices.mockReturnValue([
        {
          deviceId: "existing-device-id",
          mac: "aa:bb:cc:dd:ee:ff",
          tokenHash: "old-hash",
        },
      ]);

      const res = await request(app)
        .post("/api/provision")
        .set("x-bootstrap-secret", "test-bootstrap-secret")
        .send({ mac: "AA:BB:CC:DD:EE:FF" }); // uppercase, should normalize

      expect(res.status).toBe(200);
      expect(res.body.deviceId).toBe("existing-device-id");
      expect(res.body).toHaveProperty("token");
    });
  });

  describe("POST /api/device/readings", () => {
    const mockDevice = { deviceId: "test-device-123", mac: "aa:bb:cc:dd:ee:ff" };

    beforeEach(() => {
      getDeviceByToken.mockReturnValue(mockDevice);
    });

    test("returns 401 when token is missing", async () => {
      getDeviceByToken.mockReturnValue(null);

      const res = await request(app)
        .post("/api/device/readings")
        .send({ rows: [] });

      expect(res.status).toBe(401);
    });

    test("returns 400 when no readings provided", async () => {
      const res = await request(app)
        .post("/api/device/readings")
        .set("x-device-token", "valid-token")
        .send({ rows: [] });

      expect(res.status).toBe(400);
      expect(res.text).toBe("No readings provided");
    });

    test("returns 400 when batch is too large", async () => {
      const rows = Array(2001).fill({ ts: "2024-01-01", point_label: "test" });

      const res = await request(app)
        .post("/api/device/readings")
        .set("x-device-token", "valid-token")
        .send({ rows });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Batch too large");
    });

    test("stores valid readings", async () => {
      query.mockResolvedValue({ rowCount: 1 });

      const res = await request(app)
        .post("/api/device/readings")
        .set("x-device-token", "valid-token")
        .send({
          rows: [
            { ts: "2024-01-01T12:00:00Z", point_label: "pH_MeasuredValue", value: 7.2 },
            { ts: "2024-01-01T12:00:00Z", point_label: "Chlorine_MeasuredValue", value: 1.5 },
          ],
        });

      expect(res.status).toBe(200);
      expect(res.text).toBe("Readings stored");
      expect(query).toHaveBeenCalledTimes(2); // INSERT + UPDATE last_seen
    });
  });

  describe("POST /api/device/heartbeat", () => {
    const mockDevice = { deviceId: "test-device-123" };

    beforeEach(() => {
      getDeviceByToken.mockReturnValue(mockDevice);
    });

    test("returns 401 without valid token", async () => {
      getDeviceByToken.mockReturnValue(null);

      const res = await request(app)
        .post("/api/device/heartbeat")
        .send({});

      expect(res.status).toBe(401);
    });

    test("stores heartbeat and returns commands", async () => {
      query
        .mockResolvedValueOnce({ rowCount: 1 }) // INSERT health
        .mockResolvedValueOnce({ rowCount: 1 }) // UPDATE last_seen
        .mockResolvedValueOnce({ // SELECT commands
          rows: [
            { id: 1, command_type: "upload", payload: "{}" },
          ],
        });

      const res = await request(app)
        .post("/api/device/heartbeat")
        .set("x-device-token", "valid-token")
        .send({
          uptime_seconds: 3600,
          disk_used_pct: 45,
          memory_used_pct: 60,
          cpu_temp: 55,
          software_version: "6.4.0",
        });

      expect(res.status).toBe(200);
      expect(res.body.ok).toBe(true);
      expect(res.body.commands).toHaveLength(1);
    });
  });

  describe("GET /api/device/update/check", () => {
    const mockDevice = { deviceId: "test-device-123" };

    beforeEach(() => {
      getDeviceByToken.mockReturnValue(mockDevice);
    });

    test("returns no update when none available", async () => {
      latestUpdate.mockReturnValue(null);

      const res = await request(app)
        .get("/api/device/update/check")
        .set("x-device-token", "valid-token")
        .query({ current_version: "6.4.0" });

      expect(res.status).toBe(200);
      expect(res.body.update).toBe(false);
    });

    test("returns no update when version is current", async () => {
      latestUpdate.mockReturnValue({
        id: "update-1",
        version: "6.4.0",
      });

      const res = await request(app)
        .get("/api/device/update/check")
        .set("x-device-token", "valid-token")
        .query({ current_version: "6.4.0" });

      expect(res.status).toBe(200);
      expect(res.body.update).toBe(false);
    });

    test("returns update when newer version available", async () => {
      latestUpdate.mockReturnValue({
        id: "update-2",
        version: "6.5.0",
        notes: "Bug fixes",
        sha256: "abc123",
      });

      const res = await request(app)
        .get("/api/device/update/check")
        .set("x-device-token", "valid-token")
        .query({ current_version: "6.4.0" });

      expect(res.status).toBe(200);
      expect(res.body.update).toBe(true);
      expect(res.body.version).toBe("6.5.0");
      expect(res.body.download_url).toBe("/api/device/update/download/update-2");
    });
  });
});
