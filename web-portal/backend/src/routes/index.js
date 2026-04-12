"use strict";

const pagesRouter = require("./pages");
const authRouter = require("./auth");
const deviceRouter = require("./device");
const portalRouter = require("./portal");
const adminRouter = require("./admin");

module.exports = {
  pagesRouter,
  authRouter,
  deviceRouter,
  portalRouter,
  adminRouter,
};
