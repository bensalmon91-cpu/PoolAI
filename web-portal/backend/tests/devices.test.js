"use strict";

const fs = require("fs");
const path = require("path");

// Mock fs for device file operations
jest.mock("fs");
jest.mock("../src/config", () => ({
  DEVICES_FILE: "/mock/devices.json",
  UPDATES_FILE: "/mock/updates.json",
}));

const { hashToken } = require("../src/utils/helpers");

// Now require the module after mocks are set up
const {
  readDevices,
  writeDevices,
  getDeviceByToken,
  loadUpdates,
  latestUpdate,
} = require("../src/utils/devices");

describe("readDevices", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("returns empty array when file does not exist", () => {
    fs.existsSync.mockReturnValue(false);

    const result = readDevices();

    expect(result).toEqual([]);
  });

  test("returns parsed devices from file", () => {
    const mockDevices = [
      { deviceId: "device-1", mac: "aa:bb:cc:dd:ee:ff" },
      { deviceId: "device-2", mac: "11:22:33:44:55:66" },
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockDevices));

    const result = readDevices();

    expect(result).toEqual(mockDevices);
  });

  test("returns empty array on parse error", () => {
    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue("invalid json");

    const result = readDevices();

    expect(result).toEqual([]);
  });

  test("returns empty array when file contains non-array", () => {
    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify({ not: "array" }));

    const result = readDevices();

    expect(result).toEqual([]);
  });
});

describe("writeDevices", () => {
  test("writes devices to file with formatting", () => {
    const devices = [{ deviceId: "test", mac: "aa:bb:cc:dd:ee:ff" }];

    writeDevices(devices);

    expect(fs.writeFileSync).toHaveBeenCalledWith(
      "/mock/devices.json",
      JSON.stringify(devices, null, 2),
      "utf8"
    );
  });
});

describe("getDeviceByToken", () => {
  test("returns device with matching token hash", () => {
    const token = "test-token-12345";
    const tokenHash = hashToken(token);
    const mockDevices = [
      { deviceId: "device-1", tokenHash: "wrong-hash" },
      { deviceId: "device-2", tokenHash: tokenHash },
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockDevices));

    const result = getDeviceByToken(token);

    expect(result).toEqual(mockDevices[1]);
  });

  test("returns undefined when no device matches", () => {
    const mockDevices = [
      { deviceId: "device-1", tokenHash: "some-hash" },
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockDevices));

    const result = getDeviceByToken("non-existent-token");

    expect(result).toBeUndefined();
  });
});

describe("loadUpdates", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("returns empty array when file does not exist", () => {
    fs.existsSync.mockReturnValue(false);

    const result = loadUpdates();

    expect(result).toEqual([]);
  });

  test("returns parsed updates from file", () => {
    const mockUpdates = [
      { id: "update-1", version: "1.0.0", channel: "stable" },
      { id: "update-2", version: "1.1.0", channel: "beta" },
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockUpdates));

    const result = loadUpdates();

    expect(result).toEqual(mockUpdates);
  });
});

describe("latestUpdate", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("returns latest version for channel", () => {
    const mockUpdates = [
      { id: "1", version: "1.0.0", channel: "stable" },
      { id: "2", version: "1.2.0", channel: "stable" },
      { id: "3", version: "1.1.0", channel: "stable" },
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockUpdates));

    const result = latestUpdate("stable");

    expect(result.version).toBe("1.2.0");
    expect(result.id).toBe("2");
  });

  test("filters by channel", () => {
    const mockUpdates = [
      { id: "1", version: "2.0.0", channel: "beta" },
      { id: "2", version: "1.0.0", channel: "stable" },
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockUpdates));

    const result = latestUpdate("stable");

    expect(result.version).toBe("1.0.0");
  });

  test("returns null when no updates for channel", () => {
    const mockUpdates = [
      { id: "1", version: "1.0.0", channel: "beta" },
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockUpdates));

    const result = latestUpdate("stable");

    expect(result).toBeNull();
  });

  test("treats missing channel as stable", () => {
    const mockUpdates = [
      { id: "1", version: "1.0.0" }, // no channel = stable
    ];

    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(JSON.stringify(mockUpdates));

    const result = latestUpdate("stable");

    expect(result.version).toBe("1.0.0");
  });
});
