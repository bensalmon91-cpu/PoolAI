"use strict";

const request = require("supertest");
const bcrypt = require("bcryptjs");

// Setup mocks before requiring app
jest.mock("../../src/db", () => ({
  pool: null,
  ensureDb: jest.fn(() => true),
  query: jest.fn(),
}));

jest.mock("../../src/db/queries", () => ({
  findUserByEmail: jest.fn(),
  findUserById: jest.fn(),
  createPasswordReset: jest.fn(),
  verifyPasswordReset: jest.fn(),
  markPasswordResetUsed: jest.fn(),
}));

jest.mock("../../src/services/email", () => ({
  sendResetEmail: jest.fn(),
  sendAlertEmail: jest.fn(),
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
  findUserByEmail,
  createPasswordReset,
  verifyPasswordReset,
  findUserById,
  markPasswordResetUsed,
} = require("../../src/db/queries");
const { sendResetEmail } = require("../../src/services/email");

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

  const authRouter = require("../../src/routes/auth");
  app.use(authRouter);
  return app;
}

describe("Auth Routes", () => {
  let app;

  beforeAll(() => {
    app = createApp();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    ensureDb.mockReturnValue(true);
  });

  describe("POST /api/login", () => {
    test("returns 400 when email is missing", async () => {
      const res = await request(app)
        .post("/api/login")
        .send({ password: "test123" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Email and password required");
    });

    test("returns 400 when password is missing", async () => {
      const res = await request(app)
        .post("/api/login")
        .send({ email: "test@example.com" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Email and password required");
    });

    test("returns 401 when user not found", async () => {
      findUserByEmail.mockResolvedValue(null);

      const res = await request(app)
        .post("/api/login")
        .send({ email: "test@example.com", password: "test123" });

      expect(res.status).toBe(401);
      expect(res.text).toBe("Invalid credentials");
    });

    test("returns 401 when password is wrong", async () => {
      const hash = await bcrypt.hash("correct-password", 12);
      findUserByEmail.mockResolvedValue({
        id: 1,
        email: "test@example.com",
        password_hash: hash,
      });

      const res = await request(app)
        .post("/api/login")
        .send({ email: "test@example.com", password: "wrong-password" });

      expect(res.status).toBe(401);
      expect(res.text).toBe("Invalid credentials");
    });

    test("redirects to portal on successful login", async () => {
      const hash = await bcrypt.hash("correct-password", 12);
      findUserByEmail.mockResolvedValue({
        id: 1,
        email: "test@example.com",
        password_hash: hash,
        account_id: 10,
        is_admin: false,
      });

      const res = await request(app)
        .post("/api/login")
        .send({ email: "test@example.com", password: "correct-password" });

      expect(res.status).toBe(303);
      expect(res.headers.location).toBe("/portal");
    });

    test("normalizes email to lowercase", async () => {
      findUserByEmail.mockResolvedValue(null);

      await request(app)
        .post("/api/login")
        .send({ email: "TEST@EXAMPLE.COM", password: "test123" });

      expect(findUserByEmail).toHaveBeenCalledWith("test@example.com");
    });
  });

  describe("POST /api/logout", () => {
    test("redirects to login page", async () => {
      const res = await request(app).post("/api/logout");

      expect(res.status).toBe(302);
      expect(res.headers.location).toBe("/pages/login.html");
    });
  });

  describe("POST /api/password/forgot", () => {
    test("returns 400 when email is missing", async () => {
      const res = await request(app)
        .post("/api/password/forgot")
        .send({});

      expect(res.status).toBe(400);
      expect(res.text).toBe("Email required");
    });

    test("returns 200 even when user not found (security)", async () => {
      findUserByEmail.mockResolvedValue(null);

      const res = await request(app)
        .post("/api/password/forgot")
        .send({ email: "nonexistent@example.com" });

      expect(res.status).toBe(200);
      expect(res.text).toBe("If the account exists, a reset email has been sent.");
      expect(sendResetEmail).not.toHaveBeenCalled();
    });

    test("sends reset email when user exists", async () => {
      findUserByEmail.mockResolvedValue({
        id: 1,
        email: "test@example.com",
      });
      createPasswordReset.mockResolvedValue("reset-token-123");

      const res = await request(app)
        .post("/api/password/forgot")
        .send({ email: "test@example.com" });

      expect(res.status).toBe(200);
      expect(createPasswordReset).toHaveBeenCalledWith(1);
      expect(sendResetEmail).toHaveBeenCalledWith("test@example.com", "reset-token-123");
    });
  });

  describe("POST /api/password/reset", () => {
    test("returns 400 when token is missing", async () => {
      const res = await request(app)
        .post("/api/password/reset")
        .send({ password: "newpassword" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Token and password required");
    });

    test("returns 400 when password is missing", async () => {
      const res = await request(app)
        .post("/api/password/reset")
        .send({ token: "some-token" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Token and password required");
    });

    test("returns 400 when token is invalid", async () => {
      verifyPasswordReset.mockResolvedValue(null);

      const res = await request(app)
        .post("/api/password/reset")
        .send({ token: "invalid-token", password: "newpassword" });

      expect(res.status).toBe(400);
      expect(res.text).toBe("Invalid or expired token");
    });

    test("resets password successfully", async () => {
      verifyPasswordReset.mockResolvedValue({ id: 1, user_id: 5 });
      findUserById.mockResolvedValue({ id: 5, email: "test@example.com" });
      query.mockResolvedValue({ rowCount: 1 });
      markPasswordResetUsed.mockResolvedValue();

      const res = await request(app)
        .post("/api/password/reset")
        .send({ token: "valid-token", password: "newpassword" });

      expect(res.status).toBe(200);
      expect(res.text).toBe("Password updated. You can now log in.");
      expect(query).toHaveBeenCalled();
      expect(markPasswordResetUsed).toHaveBeenCalledWith(1);
    });
  });
});
