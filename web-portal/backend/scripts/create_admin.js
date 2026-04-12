"use strict";

const readline = require("readline");
const bcrypt = require("bcryptjs");
const dotenv = require("dotenv");
const { Pool } = require("pg");

dotenv.config();

function prompt(question) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

async function main() {
  const dbUrl = process.env.DATABASE_URL || "";
  if (!dbUrl) {
    console.error("DATABASE_URL is not configured in .env");
    process.exit(1);
  }

  const email = (await prompt("Admin email: ")).toLowerCase();
  const password = await prompt("Admin password: ");

  if (!email || !password) {
    console.error("Email and password are required.");
    process.exit(1);
  }

  const pool = new Pool({
    connectionString: dbUrl,
    ssl: process.env.PGSSL === "true" ? { rejectUnauthorized: false } : false,
  });

  try {
    const hash = await bcrypt.hash(password, 12);
    const result = await pool.query(
      "INSERT INTO users (email, password_hash, is_admin) VALUES ($1, $2, TRUE) RETURNING id, email",
      [email, hash]
    );
    console.log(`Created admin user: ${result.rows[0].email} (id ${result.rows[0].id})`);
  } catch (err) {
    console.error("Failed to create admin user:", err.message || err);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

main();
