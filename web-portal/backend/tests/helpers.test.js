"use strict";

const {
  normalizeMac,
  hashToken,
  generateToken,
  parseVersion,
  compareVersions,
} = require("../src/utils/helpers");

describe("normalizeMac", () => {
  test("normalizes MAC with colons", () => {
    expect(normalizeMac("AA:BB:CC:DD:EE:FF")).toBe("aa:bb:cc:dd:ee:ff");
  });

  test("normalizes MAC with dashes", () => {
    expect(normalizeMac("AA-BB-CC-DD-EE-FF")).toBe("aa:bb:cc:dd:ee:ff");
  });

  test("normalizes MAC without separators", () => {
    expect(normalizeMac("AABBCCDDEEFF")).toBe("aa:bb:cc:dd:ee:ff");
  });

  test("handles mixed case", () => {
    expect(normalizeMac("aA:Bb:cC:dD:eE:fF")).toBe("aa:bb:cc:dd:ee:ff");
  });

  test("returns empty string for null/undefined", () => {
    expect(normalizeMac(null)).toBe("");
    expect(normalizeMac(undefined)).toBe("");
    expect(normalizeMac("")).toBe("");
  });

  test("filters non-hex characters", () => {
    expect(normalizeMac("AA:BB:CC:DD:EE:FF:GG")).toBe("aa:bb:cc:dd:ee:ff");
  });
});

describe("hashToken", () => {
  test("returns consistent hash for same input", () => {
    const hash1 = hashToken("test-token");
    const hash2 = hashToken("test-token");
    expect(hash1).toBe(hash2);
  });

  test("returns different hash for different input", () => {
    const hash1 = hashToken("token-1");
    const hash2 = hashToken("token-2");
    expect(hash1).not.toBe(hash2);
  });

  test("returns 64-character hex string", () => {
    const hash = hashToken("test");
    expect(hash).toMatch(/^[a-f0-9]{64}$/);
  });
});

describe("generateToken", () => {
  test("returns 64-character hex string", () => {
    const token = generateToken();
    expect(token).toMatch(/^[a-f0-9]{64}$/);
  });

  test("generates unique tokens", () => {
    const tokens = new Set();
    for (let i = 0; i < 100; i++) {
      tokens.add(generateToken());
    }
    expect(tokens.size).toBe(100);
  });
});

describe("parseVersion", () => {
  test("parses simple version", () => {
    expect(parseVersion("1.2.3")).toEqual([1, 2, 3]);
  });

  test("parses version with two parts", () => {
    expect(parseVersion("6.4")).toEqual([6, 4]);
  });

  test("parses single number", () => {
    expect(parseVersion("5")).toEqual([5]);
  });

  test("handles empty/null input", () => {
    expect(parseVersion("")).toEqual([]);
    expect(parseVersion(null)).toEqual([]);
    expect(parseVersion(undefined)).toEqual([]);
  });

  test("converts non-numeric parts to 0", () => {
    expect(parseVersion("1.x.3")).toEqual([1, 0, 3]);
  });
});

describe("compareVersions", () => {
  test("returns 0 for equal versions", () => {
    expect(compareVersions("1.2.3", "1.2.3")).toBe(0);
  });

  test("returns 1 when first is greater (major)", () => {
    expect(compareVersions("2.0.0", "1.9.9")).toBe(1);
  });

  test("returns 1 when first is greater (minor)", () => {
    expect(compareVersions("1.3.0", "1.2.9")).toBe(1);
  });

  test("returns 1 when first is greater (patch)", () => {
    expect(compareVersions("1.2.4", "1.2.3")).toBe(1);
  });

  test("returns -1 when second is greater", () => {
    expect(compareVersions("1.2.3", "1.2.4")).toBe(-1);
  });

  test("handles different version lengths", () => {
    expect(compareVersions("1.2", "1.2.0")).toBe(0);
    expect(compareVersions("1.2.1", "1.2")).toBe(1);
    expect(compareVersions("1.2", "1.2.1")).toBe(-1);
  });

  test("real version examples", () => {
    expect(compareVersions("6.4.0", "6.3.0")).toBe(1);
    expect(compareVersions("6.3.0", "6.2.5")).toBe(1);
    expect(compareVersions("6.2.5", "6.3.0")).toBe(-1);
  });
});
