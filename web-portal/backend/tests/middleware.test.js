"use strict";

// Mock the devices module before requiring middleware
jest.mock("../src/utils/devices", () => ({
  getDeviceByToken: jest.fn(),
}));

const { getDeviceByToken } = require("../src/utils/devices");
const {
  requireAuth,
  requireAdmin,
  requireDeviceAuth,
  ensureBootstrapSecret,
} = require("../src/middleware/auth");

// Helper to create mock request/response
function createMockReqRes(overrides = {}) {
  const req = {
    session: {},
    header: jest.fn(),
    ...overrides,
  };
  const res = {
    status: jest.fn().mockReturnThis(),
    send: jest.fn().mockReturnThis(),
    redirect: jest.fn().mockReturnThis(),
  };
  const next = jest.fn();
  return { req, res, next };
}

describe("requireAuth middleware", () => {
  test("calls next() when user is authenticated", () => {
    const { req, res, next } = createMockReqRes({
      session: { user: { id: 1, email: "test@example.com" } },
    });

    requireAuth(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.redirect).not.toHaveBeenCalled();
  });

  test("redirects to login when user is not authenticated", () => {
    const { req, res, next } = createMockReqRes({
      session: {},
    });

    requireAuth(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.redirect).toHaveBeenCalledWith("/pages/login.html");
  });

  test("redirects when session is missing", () => {
    const { req, res, next } = createMockReqRes();
    delete req.session;

    requireAuth(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.redirect).toHaveBeenCalledWith("/pages/login.html");
  });
});

describe("requireAdmin middleware", () => {
  test("calls next() when user is admin", () => {
    const { req, res, next } = createMockReqRes({
      session: { user: { id: 1, isAdmin: true } },
    });

    requireAdmin(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.status).not.toHaveBeenCalled();
  });

  test("returns 403 when user is not admin", () => {
    const { req, res, next } = createMockReqRes({
      session: { user: { id: 1, isAdmin: false } },
    });

    requireAdmin(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.send).toHaveBeenCalledWith("Admin access required");
  });

  test("returns 403 when user is missing", () => {
    const { req, res, next } = createMockReqRes({
      session: {},
    });

    requireAdmin(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(403);
  });
});

describe("requireDeviceAuth middleware", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("calls next() and sets req.device for valid bearer token", () => {
    const mockDevice = { deviceId: "test-device", mac: "aa:bb:cc:dd:ee:ff" };
    getDeviceByToken.mockReturnValue(mockDevice);

    const { req, res, next } = createMockReqRes();
    req.header.mockImplementation((name) => {
      if (name === "authorization") return "Bearer valid-token";
      return "";
    });

    requireDeviceAuth(req, res, next);

    expect(getDeviceByToken).toHaveBeenCalledWith("valid-token");
    expect(req.device).toBe(mockDevice);
    expect(next).toHaveBeenCalled();
  });

  test("calls next() for valid x-device-token header", () => {
    const mockDevice = { deviceId: "test-device" };
    getDeviceByToken.mockReturnValue(mockDevice);

    const { req, res, next } = createMockReqRes();
    req.header.mockImplementation((name) => {
      if (name === "x-device-token") return "device-token";
      return "";
    });

    requireDeviceAuth(req, res, next);

    expect(getDeviceByToken).toHaveBeenCalledWith("device-token");
    expect(next).toHaveBeenCalled();
  });

  test("returns 401 when token is missing", () => {
    const { req, res, next } = createMockReqRes();
    req.header.mockReturnValue("");

    requireDeviceAuth(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.send).toHaveBeenCalledWith("Missing device token");
  });

  test("returns 401 when token is invalid", () => {
    getDeviceByToken.mockReturnValue(null);

    const { req, res, next } = createMockReqRes();
    req.header.mockImplementation((name) => {
      if (name === "authorization") return "Bearer invalid-token";
      return "";
    });

    requireDeviceAuth(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.send).toHaveBeenCalledWith("Invalid device token");
  });
});

describe("ensureBootstrapSecret middleware", () => {
  const originalEnv = process.env.BOOTSTRAP_SECRET;

  afterEach(() => {
    process.env.BOOTSTRAP_SECRET = originalEnv;
  });

  test("calls next() when secret matches", () => {
    process.env.BOOTSTRAP_SECRET = "correct-secret";

    const { req, res, next } = createMockReqRes();
    req.header.mockImplementation((name) => {
      if (name === "x-bootstrap-secret") return "correct-secret";
      return "";
    });

    ensureBootstrapSecret(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.status).not.toHaveBeenCalled();
  });

  test("returns 403 when secret does not match", () => {
    process.env.BOOTSTRAP_SECRET = "correct-secret";

    const { req, res, next } = createMockReqRes();
    req.header.mockImplementation((name) => {
      if (name === "x-bootstrap-secret") return "wrong-secret";
      return "";
    });

    ensureBootstrapSecret(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.send).toHaveBeenCalledWith("Invalid bootstrap secret");
  });

  test("returns 500 when bootstrap secret is not configured", () => {
    process.env.BOOTSTRAP_SECRET = "";

    const { req, res, next } = createMockReqRes();
    req.header.mockReturnValue("any-secret");

    ensureBootstrapSecret(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(500);
    expect(res.send).toHaveBeenCalledWith("Bootstrap secret not configured");
  });
});
