-- Core portal schema (Postgres)

CREATE TABLE IF NOT EXISTS accounts (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT,
  contact_phone TEXT,
  address TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
  is_admin BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS password_resets (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token_hash);

CREATE TABLE IF NOT EXISTS pools (
  id SERIAL PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  location TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pools_account ON pools(account_id);

CREATE TABLE IF NOT EXISTS devices (
  id SERIAL PRIMARY KEY,
  device_id TEXT NOT NULL UNIQUE,
  mac TEXT,
  hostname TEXT,
  model TEXT,
  software_version TEXT,
  account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
  pool_id INTEGER REFERENCES pools(id) ON DELETE SET NULL,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_account ON devices(account_id);
CREATE INDEX IF NOT EXISTS idx_devices_pool ON devices(pool_id);

CREATE TABLE IF NOT EXISTS device_readings (
  id BIGSERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  pool TEXT,
  host TEXT,
  system_name TEXT,
  serial_number TEXT,
  point_label TEXT NOT NULL,
  value DOUBLE PRECISION,
  raw_type TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_device_readings_device_ts ON device_readings(device_id, ts);
CREATE INDEX IF NOT EXISTS idx_device_readings_point_ts ON device_readings(point_label, ts);

CREATE TABLE IF NOT EXISTS device_alarm_events (
  id BIGSERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
  started_ts TIMESTAMPTZ NOT NULL,
  ended_ts TIMESTAMPTZ,
  pool TEXT,
  host TEXT,
  system_name TEXT,
  serial_number TEXT,
  source_label TEXT NOT NULL,
  bit_name TEXT NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_device_alarm_device_ts ON device_alarm_events(device_id, started_ts);
CREATE INDEX IF NOT EXISTS idx_device_alarm_open ON device_alarm_events(device_id, ended_ts);

CREATE TABLE IF NOT EXISTS device_ai_findings (
  id BIGSERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  pool TEXT NOT NULL,
  reason TEXT NOT NULL,
  summary TEXT NOT NULL,
  water_quality_grade TEXT,
  reliability_grade TEXT,
  details_json TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_device_ai_device_ts ON device_ai_findings(device_id, ts);

-- Device health monitoring
CREATE TABLE IF NOT EXISTS device_health (
  id BIGSERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  uptime_seconds INTEGER,
  disk_used_pct NUMERIC,
  memory_used_pct NUMERIC,
  cpu_temp NUMERIC,
  last_upload_success TIMESTAMPTZ,
  last_upload_error TEXT,
  pending_chunks INTEGER DEFAULT 0,
  failed_uploads INTEGER DEFAULT 0,
  software_version TEXT,
  ip_address TEXT
);

CREATE INDEX IF NOT EXISTS idx_device_health_device_ts ON device_health(device_id, ts DESC);

-- Device commands (for triggering on-demand actions)
CREATE TABLE IF NOT EXISTS device_commands (
  id BIGSERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
  command_type TEXT NOT NULL,  -- 'upload', 'restart', 'update'
  payload TEXT,                -- JSON payload if needed
  status TEXT NOT NULL DEFAULT 'pending',  -- pending, acknowledged, completed, failed
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  acknowledged_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  result TEXT                  -- Result message from device
);

CREATE INDEX IF NOT EXISTS idx_device_commands_device_status ON device_commands(device_id, status);
CREATE INDEX IF NOT EXISTS idx_device_commands_pending ON device_commands(device_id, status) WHERE status = 'pending';
