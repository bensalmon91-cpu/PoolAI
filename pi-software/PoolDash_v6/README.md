🟦 PoolAIssistant – Monitoring & Control Platform

Version: v6.1.1 (Universal Deployment)
Author: Ben Salmon
Purpose: Industrial pool / plant monitoring, logging, and dashboarding using Modbus TCP.

📦 Overview

PoolAIssistant is a lightweight, modular monitoring system designed to:

Collect live Modbus TCP data from pool / plant controllers

Log historical values to SQLite

Display live dashboards via a web UI

Record faults and fault clear events reliably

Run unattended on Linux (Raspberry Pi / mini-PC)

It is designed for robust long-term operation, not rapid prototyping.

🧱 Project Structure
PoolAIssistant_v6/
│
├── run_ui.py                     # Starts the web UI (Flask)
├── modbus_logger.py              # Modbus logger (readings + alarms)
│
├── pooldash_app/
│   ├── __init__.py
│   ├── config.py                 # Central configuration
│   ├── blueprints/               # UI logic
│   │   ├── main_ui.py
│   │   ├── charts.py
│   │   ├── alarms.py
│   │   ├── proxy.py
│   │   └── pump_selector.py
│   └── static/                   # CSS, JS
│
├── instance/
│   └── pooldash_settings.json    # Runtime configuration
│
├── modbus_points.py              # Register → meaning map
├── requirements.txt
├── .env.sample                   # Optional environment overrides
└── README.md

🚀 Quick Start

## 🔰 Getting Started for Beginners

### Accessing PoolAIssistant

There are two ways to access your PoolAIssistant system:

#### 1️⃣ **Web Interface** (Recommended for Daily Use)
The easiest way to view your pool data and settings:

**On the same network:**
1. Open any web browser (Chrome, Firefox, Safari, Edge)
2. Type in the address bar: `http://poolai.local:8080`
3. Press Enter

You'll see the PoolAIssistant dashboard with your pool tabs!

**If `.local` doesn't work:**
- Find your Pi's IP address (check your router or use the AP method below)
- Use: `http://10.0.30.80:8080` (replace with your Pi's IP)

#### 2️⃣ **SSH Terminal Access** (For Advanced Configuration)
For system administration and troubleshooting:

**Windows (PowerShell or Command Prompt):**
```
ssh poolai@poolai.local
```
When prompted, enter your password.

**Mac/Linux (Terminal):**
```bash
ssh poolai@poolai.local
```

**First-time connection:** You may see a message asking to confirm the connection. Type `yes` and press Enter.

---

### 🌐 Access Point Mode (No Network Setup Required)

Can't connect? The Pi creates its own WiFi network for easy setup!

**When Active:**
- ✅ **First 30 minutes** after boot (always broadcasts)
- ✅ **Anytime** the Pi isn't connected to WiFi

**How to Connect:**

1. **On your phone/laptop WiFi settings:**
   - Look for network: **PoolAIssistant**
   - Password: `12345678`

2. **Once connected, open browser:**
   - Go to: `http://192.168.4.1:8080`

3. **Configure WiFi (in Settings page):**
   - Click **Settings** tab
   - Enter your WiFi name (SSID) and password
   - Click **Save Wi-Fi settings**
   - Pi will connect to your network and turn off the AP

**After WiFi is configured:**
- The AP turns off automatically
- Access normally via `http://poolai.local:8080`
- If WiFi disconnects, AP automatically turns back on

---

### 📱 Quick Reference Card

| What                  | How                                    |
|-----------------------|----------------------------------------|
| **View Dashboard**    | `http://poolai.local:8080`    |
| **Initial Setup**     | Connect to "PoolAIssistant" WiFi      |
| **SSH Login**         | `ssh poolai@poolai.local` |
| **AP WiFi Password**  | `12345678`                            |
| **Change Settings**   | Click Settings tab in web interface   |

---

### For Cloned/Pre-Configured Pi:

If you received a pre-configured SD card:
1. Insert SD card into Raspberry Pi
2. Connect Ethernet to your network
3. Power on
4. Find Pi IP address (check router or use `nmap`)
5. Access web UI: `http://<pi-ip>:8080`

The Pi will auto-configure on first boot with pre-set controller IPs.

### For Fresh Installation on Cloned SD Card:

If booting a cloned master image for the first time:
```bash
ssh poolai@poolai.local
# Or: ssh poolaissistant@<pi-ip>
cd /opt/PoolAIssistant/app
sudo bash first_boot_setup.sh
```

Follow the interactive wizard to configure your controllers.

### For Development/Manual Setup:

1️⃣ Install system dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sqlite3
```

2️⃣ Create virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3️⃣ Install Python dependencies
```bash
pip install -r requirements.txt
```

4️⃣ Start the logger (Modbus polling)
```bash
python modbus_logger.py
```

5️⃣ Start the web UI
```bash
python run_ui.py
```

Access the UI at: `http://<device-ip>:8080`

### Multi-Site Deployment:

For deploying to multiple sites, see **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** which covers:
- Creating master SD card images
- Pre-configuring for different networks
- Network-universal deployment workflows
- Site-specific configuration templates

⚙️ Systemd (Recommended for Production)

Two services are expected:

Service	Purpose
poolaissistant_logger.service	Polls Modbus + writes DB
poolaissistant_ui.service	Web interface

These are typically installed via your installer script, but can be created manually if needed.

🧠 Architecture Overview
Data Flow
Modbus Devices → modbus_logger.py → SQLite → Flask UI → Browser

Logging Philosophy

Faults: Logged only on change (including clear events)

Trends: Polled at regular intervals

No duplicate spam

Safe for months of uptime

🔥 Fault Logging Logic (Important)

This version uses edge-triggered fault detection:

Condition	Logged?
Fault appears (0 → non-zero)	✅ YES
Fault persists	❌ No
Fault clears (non-zero → 0)	✅ YES
System idle / no fault	❌ No

This keeps your database clean while still giving full visibility of fault lifecycles.

🧩 Configuration Files
pooldash_app/config.py

Edit this to change:

Pool names

IP addresses

Register mappings

UI behaviour

.env

Optional overrides for:

POOLDB=/opt/PoolAIssistant/data/pool_readings.sqlite3
POOLS_JSON={"Pool 1":{"host":"controller-1","unit":1}}
MODBUS_TIMEOUT=3
POLL_FAULTS_EVERY_S=1.5

🧪 Testing & Validation

Check logger output:

journalctl -u poolaissistant_logger -f


Check UI:

journalctl -u poolaissistant_ui -f


Manual DB check:

sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3

🧠 Design Notes

SQLite WAL mode is enabled for safe concurrent reads.

All Modbus I/O is retried and timeout-protected.

No UI thread ever blocks on Modbus I/O.

Logging is idempotent and safe under restart.

Designed for months of unattended runtime.
