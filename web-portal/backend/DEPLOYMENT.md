# PoolDash Portal Deployment (Cloud Host)

This guide sets up the Node/Express backend as a systemd service and places it behind nginx.

## Prerequisites

- Ubuntu 22.04+ or Debian 12+
- Node.js 18+ (LTS recommended)
- PostgreSQL 14+
- nginx
- Certbot (for SSL)

## 1) Create service user
```bash
sudo useradd -r -s /bin/false pooldash
sudo mkdir -p /opt/pooldash
sudo chown pooldash:pooldash /opt/pooldash
```

## 2) Upload code
Copy the portal repo to the host:
```bash
sudo -u pooldash git clone <repo-url> /opt/pooldash/portal
# Or upload via scp/rsync
```

## 3) Install dependencies
```bash
cd /opt/pooldash/portal/backend
sudo -u pooldash npm ci --production
```

## 4) Configure environment
Copy `.env.example` to `.env` and set values:
```bash
cd /opt/pooldash/portal/backend
sudo -u pooldash cp .env.example .env
sudo -u pooldash chmod 600 .env
sudo -u pooldash nano .env
```

**Required variables:**
| Variable | Description |
|----------|-------------|
| `NODE_ENV` | Set to `production` |
| `DATABASE_URL` | Postgres connection string |
| `SESSION_SECRET` | Long random string (32+ chars) |
| `BOOTSTRAP_SECRET` | Shared secret with Pi devices |
| `APP_BASE_URL` | Public URL (e.g., https://portal.example.com) |

**Optional (email features):**
| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASS` | SMTP password |
| `SMTP_FROM` | From address for emails |
| `ALERT_EMAIL` | Email for device offline alerts |

**Generate secure secrets:**
```bash
# Generate SESSION_SECRET
openssl rand -hex 32

# Generate BOOTSTRAP_SECRET (must match Pi devices)
openssl rand -hex 24
```

## 5) Create database schema
```bash
# Create database
sudo -u postgres createdb pooldash_portal
sudo -u postgres createuser pooldash_user

# Set password and grant access
sudo -u postgres psql -c "ALTER USER pooldash_user WITH PASSWORD 'your-secure-password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE pooldash_portal TO pooldash_user;"

# Apply schema
psql "$DATABASE_URL" -f /opt/pooldash/portal/backend/db/schema.sql
```

## 6) Create uploads directory
```bash
sudo mkdir -p /opt/pooldash/portal/uploads
sudo chown pooldash:pooldash /opt/pooldash/portal/uploads
sudo chmod 750 /opt/pooldash/portal/uploads
```

## 7) Install the systemd service
```bash
sudo cp /opt/pooldash/portal/backend/scripts/systemd/pooldash_portal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pooldash_portal.service
```

Check status/logs:
```bash
sudo systemctl status pooldash_portal.service
journalctl -u pooldash_portal.service -f
```

**Note:** The service runs with security hardening (NoNewPrivileges, ProtectSystem). If you encounter permission issues, check the `ReadWritePaths` directive in the service file.

## 6) Configure nginx (reverse proxy)
```
sudo cp /opt/pooldash/portal/backend/scripts/nginx/pooldash_portal.conf /etc/nginx/sites-available/pooldash_portal.conf
sudo ln -s /etc/nginx/sites-available/pooldash_portal.conf /etc/nginx/sites-enabled/pooldash_portal.conf
sudo nginx -t
sudo systemctl reload nginx
```

Update `server_name` in the nginx file to your domain.

## 7) Enable HTTPS
Use your preferred SSL setup (e.g., Certbot):
```
sudo certbot --nginx -d portal.example.com
```

## 8) Create the first admin
```
cd /opt/pooldash/portal/backend
npm run create-admin
```

## 9) Admin workflow
1. Create a client (account).
2. Create pools for that client.
3. Assign devices to pools.
4. Create users tied to the client account.

## 10) Pi configuration
Ensure each Pi has:
- `BACKEND_URL=https://your-domain`
- `BOOTSTRAP_SECRET` (matches backend)
- systemd sync timer enabled

## 11) Optional cleanup
Schedule daily cleanup:
```
cd /opt/pooldash/portal/backend
npm run cleanup-readings
```

You can run it via cron or systemd timer templates in `backend/scripts`.
