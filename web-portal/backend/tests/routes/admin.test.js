"use strict";

const request = require("supertest");

// Setup mocks before requiring app
jest.mock("../../src/db", () => ({
  pool: null,
  ensureDb: jest.fn(() => true),
  query: jest.fn(),
}));

jest.mock("../../src/db/queries", () => ({
  createUser: jest.fn(),
  createAccount: jest.fn(),
  createAccountWithDetails: jest.fn(),
  updateAccount: jest.fn(),
  createPool: jest.fn(),
  updatePool: jest.fn(),
  updateDeviceAssignment: jest.fn(),
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
  createUser,
  createAccount,
  createAccountWithDetails,
  createPool,
} = require("../../src/db/queries");

// Create test app with session handling
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

  // Test helper to set session
  app.use("/test-login", (req, res) => {
    req.session.user = {
      id: 1,
      email: "admin@example.com",
      accountId: 1,
      isAdmin: req.query.admin === "true",
    };
    res.json({ ok: true });
  });

  const adminRouter = require("../../src/routes/admin");
  app.use(adminRouter);
  return app;
}

describe("Admin Routes", () => {
  let app;
  let agent;

  beforeAll(() => {
    app = createApp();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    ensureDb.mockReturnValue(true);
    agent = request.agent(app);
  });

  describe("GET /api/admin/users", () => {
    test("redirects to login when not logged in", async () => {
      const res = await request(app).get("/api/admin/users");

      expect(res.status).toBe(302);
      expect(res.headers.location).toBe("/pages/login.html");
    });

    test("returns 403 when not admin", async () => {
      await agent.get("/test-login?admin=false");

      const res = await agent.get("/api/admin/users");

      expect(res.status).toBe(403);
      expect(res.text).toBe("Admin access required");
    });

    test("returns users list for admin", async () => {
      await agent.get("/test-login?admin=true");

      query.mockResolvedValue({
        rows: [
          { id: 1, email: "admin@example.com", is_admin: true, account_name: "Test Account" },
          { id: 2, email: "user@example.com", is_admin: false, account_name: "Test Account" },
        ],
      });

      const res = await agent.get("/api/admin/users");

      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0].email).toBe("admin@example.com");
    });
  });

  describe("POST /api/admin/users", () => {
    beforeEach(async () => {
      await agent.get("/test-login?admin=true");
    });

    test("returns 400 when email missing", async () => {
      const res = await agent
        .post("/api/admin/users")
        .send({ password: "test123" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Email and password required");
    });

    test("creates user with new account", async () => {
      createAccount.mockResolvedValue({ id: 5 });
      createUser.mockResolvedValue({
        id: 10,
        email: "new@example.com",
        is_admin: false,
      });

      const res = await agent.post("/api/admin/users").send({
        email: "new@example.com",
        password: "test123",
        accountName: "New Account",
      });

      expect(res.status).toBe(200);
      expect(createAccount).toHaveBeenCalledWith("New Account");
      expect(createUser).toHaveBeenCalledWith("new@example.com", "test123", 5, false);
    });

    test("creates admin user", async () => {
      createUser.mockResolvedValue({
        id: 11,
        email: "newadmin@example.com",
        is_admin: true,
      });

      const res = await agent.post("/api/admin/users").send({
        email: "newadmin@example.com",
        password: "admin123",
        accountId: 1,
        isAdmin: "true",
      });

      expect(res.status).toBe(200);
      expect(createUser).toHaveBeenCalledWith("newadmin@example.com", "admin123", 1, true);
    });
  });

  describe("GET /api/admin/accounts", () => {
    test("returns accounts list for admin", async () => {
      await agent.get("/test-login?admin=true");

      query.mockResolvedValue({
        rows: [
          { id: 1, name: "Account 1", contact_email: "a1@example.com" },
          { id: 2, name: "Account 2", contact_email: "a2@example.com" },
        ],
      });

      const res = await agent.get("/api/admin/accounts");

      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
    });
  });

  describe("POST /api/admin/accounts", () => {
    beforeEach(async () => {
      await agent.get("/test-login?admin=true");
    });

    test("returns 400 when name missing", async () => {
      const res = await agent.post("/api/admin/accounts").send({});

      expect(res.status).toBe(400);
      expect(res.text).toBe("Account name required");
    });

    test("creates account with details", async () => {
      createAccountWithDetails.mockResolvedValue({
        id: 5,
        name: "New Account",
        contact_email: "contact@example.com",
      });

      const res = await agent.post("/api/admin/accounts").send({
        name: "New Account",
        contact_name: "John Doe",
        contact_email: "contact@example.com",
        contact_phone: "123-456-7890",
        address: "123 Main St",
      });

      expect(res.status).toBe(200);
      expect(createAccountWithDetails).toHaveBeenCalledWith({
        name: "New Account",
        contact_name: "John Doe",
        contact_email: "contact@example.com",
        contact_phone: "123-456-7890",
        address: "123 Main St",
      });
    });
  });

  describe("GET /api/admin/pools", () => {
    test("returns pools list for admin", async () => {
      await agent.get("/test-login?admin=true");

      query.mockResolvedValue({
        rows: [
          { id: 1, name: "Pool 1", account_name: "Account 1" },
          { id: 2, name: "Pool 2", account_name: "Account 2" },
        ],
      });

      const res = await agent.get("/api/admin/pools");

      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
    });
  });

  describe("POST /api/admin/pools", () => {
    beforeEach(async () => {
      await agent.get("/test-login?admin=true");
    });

    test("returns 400 when account or name missing", async () => {
      const res = await agent.post("/api/admin/pools").send({ name: "Pool" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Account and pool name required");
    });

    test("creates pool", async () => {
      createPool.mockResolvedValue({
        id: 3,
        name: "New Pool",
        account_id: 1,
      });

      const res = await agent.post("/api/admin/pools").send({
        account_id: 1,
        name: "New Pool",
        location: "Building A",
        notes: "Test notes",
      });

      expect(res.status).toBe(200);
      expect(createPool).toHaveBeenCalledWith({
        account_id: 1,
        name: "New Pool",
        location: "Building A",
        notes: "Test notes",
      });
    });
  });

  describe("GET /api/admin/devices", () => {
    test("returns devices list for admin", async () => {
      await agent.get("/test-login?admin=true");

      query.mockResolvedValue({
        rows: [
          { device_id: "dev-1", hostname: "pi-1", account_name: "Account 1" },
          { device_id: "dev-2", hostname: "pi-2", account_name: "Account 2" },
        ],
      });

      const res = await agent.get("/api/admin/devices");

      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
    });
  });

  describe("GET /api/admin/devices/health", () => {
    test("returns device health with online status", async () => {
      await agent.get("/test-login?admin=true");

      const now = new Date();
      const fiveMinutesAgo = new Date(now - 5 * 60 * 1000);
      const hourAgo = new Date(now - 60 * 60 * 1000);

      query.mockResolvedValue({
        rows: [
          {
            device_id: "dev-1",
            hostname: "pi-1",
            last_seen_at: fiveMinutesAgo.toISOString(),
            cpu_temp: 55,
          },
          {
            device_id: "dev-2",
            hostname: "pi-2",
            last_seen_at: hourAgo.toISOString(),
            cpu_temp: 60,
          },
        ],
      });

      const res = await agent.get("/api/admin/devices/health");

      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0].is_online).toBe(true); // 5 minutes ago
      expect(res.body[1].is_online).toBe(false); // 1 hour ago
    });
  });
});
