# PoolDash Backend

Node.js/Express backend for the PoolDash web portal. Handles device provisioning, data ingestion, user authentication, and portal APIs.

## Architecture

```
backend/
├── server.js              # Entry point - minimal Express setup
├── src/
│   ├── config/            # Environment config and validation
│   ├── db/                # Database connection and queries
│   ├── middleware/        # Auth middleware (session, device token, admin)
│   ├── routes/            # API route handlers
│   │   ├── auth.js        # Login, logout, password reset
│   │   ├── device.js      # Device provisioning, readings, updates
│   │   ├── portal.js      # Client portal APIs
│   │   ├── admin.js       # Admin management APIs
│   │   └── pages.js       # Static page serving
│   ├── services/          # Business logic (email, health monitoring)
│   └── utils/             # Helpers (MAC normalization, token hashing)
├── tests/                 # Jest test suites
│   ├── helpers.test.js    # Unit tests for utility functions
│   ├── middleware.test.js # Unit tests for auth middleware
│   ├── devices.test.js    # Unit tests for device logic
│   └── routes/            # Integration tests for API routes
├── data/                  # Runtime data (devices.json, updates.json)
├── scripts/               # Deployment scripts and systemd templates
└── db/                    # Database schema files
```

## Quick Start

```bash
# Install dependencies
npm install

# Copy and configure environment
cp .env.example .env

# Create database schema
psql "$DATABASE_URL" -f db/schema.sql

# Create admin user
npm run create-admin

# Start server
npm start
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm start` | Start production server |
| `npm run dev` | Start development server |
| `npm test` | Run test suite |
| `npm run test:watch` | Run tests in watch mode |
| `npm run test:coverage` | Run tests with coverage report |
| `npm run create-admin` | Create initial admin user |
| `npm run cleanup-readings` | Prune old device readings |

## Testing

The test suite includes unit tests and integration tests:

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run specific test file
npm test -- --testPathPattern=helpers

# Watch mode for development
npm run test:watch
```

**Test coverage:**
- `helpers.test.js` - MAC normalization, token hashing, version comparison
- `middleware.test.js` - Session auth, admin auth, device token auth
- `devices.test.js` - Device file operations, update management
- `routes/*.test.js` - API endpoint integration tests

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/login` | Email/password login |
| POST | `/api/logout` | End session |
| POST | `/api/password/forgot` | Request password reset |
| POST | `/api/password/reset` | Reset password with token |

### Device API (requires device token)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/provision` | Register new device (requires bootstrap secret) |
| POST | `/api/device/readings` | Upload sensor readings |
| POST | `/api/device/alarms` | Upload alarm events |
| POST | `/api/device/ai` | Upload AI findings |
| POST | `/api/device/heartbeat` | Health check with metrics |
| GET | `/api/device/commands` | Fetch pending commands |
| POST | `/api/device/commands/:id/complete` | Mark command complete |
| GET | `/api/device/update/check` | Check for software updates |
| GET | `/api/device/update/download/:id` | Download update package |

### Portal API (requires session auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/portal/pools` | List client's pools |
| GET | `/api/portal/pool/:id/latest` | Latest readings |
| GET | `/api/portal/pool/:id/recent` | Recent readings history |
| GET | `/api/portal/pool/:id/alarms` | Active/recent alarms |
| GET | `/api/portal/pool/:id/ai` | AI analysis findings |

### Admin API (requires admin session)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users` | List all users |
| POST | `/api/admin/users` | Create user |
| GET | `/api/admin/accounts` | List accounts |
| POST | `/api/admin/accounts` | Create account |
| POST | `/api/admin/accounts/:id` | Update account |
| GET | `/api/admin/pools` | List all pools |
| POST | `/api/admin/pools` | Create pool |
| POST | `/api/admin/pools/:id` | Update pool |
| GET | `/api/admin/devices` | List all devices |
| POST | `/api/admin/devices/:id` | Update device assignment |
| GET | `/api/admin/devices/health` | Device health dashboard |
| GET | `/api/admin/devices/:id/health-history` | Device health history |
| POST | `/api/admin/devices/:id/request-upload` | Request device upload |
| GET | `/api/admin/devices/:id/commands` | Device command history |

## Environment Variables

See `.env.example` for all options. Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SESSION_SECRET` | Express session secret |
| `BOOTSTRAP_SECRET` | Device provisioning secret |
| `NODE_ENV` | `development` or `production` |
| `PORT` | Server port (default: 3000) |
| `SMTP_*` | Email configuration |

## Data Model

- **Accounts** - Clients with contact details
- **Pools** - Belong to accounts
- **Devices** - Assigned to pools; store readings per device
- **Users** - Belong to accounts; can be admins

## Deployment

See `DEPLOYMENT.md` for production deployment guide including:
- Systemd service configuration
- Nginx reverse proxy setup
- SSL/TLS configuration
- Database setup
- Cron jobs for maintenance

## CI/CD

GitHub Actions runs tests on every push and PR to `main`. See `.github/workflows/test.yml`.
