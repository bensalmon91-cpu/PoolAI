"""
PoolAIssistant Launcher/Settings UI
Web-based launcher interface with mode selection, data push with rate limiting,
and guided setup for technicians.
"""

import json
import os
import secrets
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify

# Paths
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config" / "launcher_settings.json"
ALERTS_PATH = SCRIPT_DIR / "analysis" / "latest_alerts.json"


class LauncherSettings:
    """Manage launcher settings with persistence."""

    def __init__(self):
        self.config_path = CONFIG_PATH
        self.config = self.load()

    def load(self) -> dict:
        """Load settings from file."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                return json.load(f)
        return self._default_config()

    def save(self):
        """Save settings to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def _default_config(self) -> dict:
        return {
            "selected_mode": "web",
            "data_push": {
                "last_push_timestamp": None,
                "cooldown_hours": 1,
                "daily_limit": 24,
                "pushes_today": 0,
                "today_date": None
            },
            "server": {
                "host": "0.0.0.0",
                "port": 8080
            }
        }

    def get_mode(self) -> str:
        return self.config.get("selected_mode", "web")

    def set_mode(self, mode: str):
        if mode in ["cli", "web", "sms"]:
            self.config["selected_mode"] = mode
            self.save()


class DataPusher:
    """Handle cloud push with rate limiting."""

    def __init__(self, settings: LauncherSettings):
        self.settings = settings
        self.push_config = settings.config.get("data_push", {})

    def can_push(self) -> tuple[bool, str, dict]:
        """Check if push is allowed. Returns (allowed, message, info)."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Reset daily counter if new day
        if self.push_config.get("today_date") != today:
            self.push_config["today_date"] = today
            self.push_config["pushes_today"] = 0
            self.settings.save()

        # Check daily limit
        daily_limit = self.push_config.get("daily_limit", 24)
        pushes_today = self.push_config.get("pushes_today", 0)

        if pushes_today >= daily_limit:
            return False, f"Daily limit reached ({daily_limit} pushes)", {
                "pushes_today": pushes_today,
                "daily_limit": daily_limit,
                "next_available": "Tomorrow"
            }

        # Check cooldown
        last_push = self.push_config.get("last_push_timestamp")
        cooldown_hours = self.push_config.get("cooldown_hours", 1)

        if last_push:
            last_push_time = datetime.fromisoformat(last_push)
            cooldown_end = last_push_time + timedelta(hours=cooldown_hours)
            now = datetime.now()

            if now < cooldown_end:
                remaining = cooldown_end - now
                minutes_remaining = int(remaining.total_seconds() / 60)
                return False, f"Cooldown active: {minutes_remaining} minutes remaining", {
                    "pushes_today": pushes_today,
                    "daily_limit": daily_limit,
                    "minutes_remaining": minutes_remaining,
                    "next_available": cooldown_end.strftime("%H:%M")
                }

        # Calculate time since last push
        time_since_push = None
        if last_push:
            last_push_time = datetime.fromisoformat(last_push)
            elapsed = datetime.now() - last_push_time
            hours = int(elapsed.total_seconds() / 3600)
            minutes = int((elapsed.total_seconds() % 3600) / 60)
            if hours > 0:
                time_since_push = f"{hours}h {minutes}m ago"
            else:
                time_since_push = f"{minutes}m ago"

        return True, "Ready to push", {
            "pushes_today": pushes_today,
            "daily_limit": daily_limit,
            "last_push": time_since_push or "Never"
        }

    def record_push(self):
        """Record a successful push."""
        self.push_config["last_push_timestamp"] = datetime.now().isoformat()
        self.push_config["pushes_today"] = self.push_config.get("pushes_today", 0) + 1
        self.settings.config["data_push"] = self.push_config
        self.settings.save()

    def full_sync(self) -> dict:
        """Execute full sync: pull data, run analysis, push results."""
        results = {
            "sync_status": None,
            "alert_status": None,
            "push_status": None,
            "errors": []
        }

        # 1. Pull latest sensor data
        try:
            from db_sync import ChunkSyncer
            syncer = ChunkSyncer()
            sync_ok = syncer.sync()
            results["sync_status"] = "success" if sync_ok else "failed"
        except Exception as e:
            results["sync_status"] = "error"
            results["errors"].append(f"Sync: {str(e)}")

        # 2. Run analysis
        try:
            from alert_checker import AlertChecker
            checker = AlertChecker()
            alert_results = checker.run_check()
            results["alert_status"] = alert_results.get("status", "UNKNOWN")
            results["alert_count"] = len(alert_results.get("alerts", []))
        except Exception as e:
            results["alert_status"] = "error"
            results["errors"].append(f"Analysis: {str(e)}")

        # 3. Push to cloud (placeholder - implement actual API calls)
        try:
            # TODO: Implement actual push to poolaissistant.modprojects.co.uk/api/
            results["push_status"] = "success"
            self.record_push()
        except Exception as e:
            results["push_status"] = "error"
            results["errors"].append(f"Push: {str(e)}")

        return results


def load_alerts() -> dict:
    """Load current alert status."""
    if ALERTS_PATH.exists():
        with open(ALERTS_PATH) as f:
            return json.load(f)
    return {"status": "UNKNOWN", "alerts": [], "trends": []}


# Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

settings = LauncherSettings()
pusher = DataPusher(settings)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>PoolAIssistant Launcher</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        .container {
            max-width: 500px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: #16213e;
            padding: 25px;
            text-align: center;
            border-bottom: 3px solid #0f3460;
        }
        h1 { color: #e94560; font-size: 1.6em; margin-bottom: 10px; }
        .status-badge {
            display: inline-block;
            padding: 8px 20px;
            border-radius: 25px;
            font-size: 0.95em;
            font-weight: bold;
        }
        .status-badge.CRITICAL { background: #e94560; }
        .status-badge.WARNING { background: #f39c12; color: #000; }
        .status-badge.OK { background: #27ae60; }
        .status-badge.UNKNOWN { background: #555; }

        .section {
            background: #16213e;
            padding: 20px;
            margin: 15px 0;
            border-radius: 12px;
            border-left: 4px solid #0f3460;
        }
        .section h2 {
            font-size: 1.1em;
            color: #aaa;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        /* Radio buttons */
        .mode-options {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .mode-option {
            display: flex;
            align-items: center;
            padding: 12px 15px;
            background: #1a1a2e;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .mode-option:hover { background: #0f3460; }
        .mode-option input[type="radio"] {
            width: 20px;
            height: 20px;
            margin-right: 12px;
            accent-color: #e94560;
        }
        .mode-option label {
            flex: 1;
            cursor: pointer;
        }
        .mode-option .mode-name {
            font-weight: bold;
            display: block;
        }
        .mode-option .mode-desc {
            font-size: 0.85em;
            color: #888;
        }

        /* Push section */
        .push-info {
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
            font-size: 0.9em;
            color: #aaa;
        }
        .push-status {
            padding: 10px;
            background: #1a1a2e;
            border-radius: 8px;
            margin-bottom: 15px;
            text-align: center;
        }
        .push-status.ready { border-left: 3px solid #27ae60; }
        .push-status.blocked { border-left: 3px solid #e94560; }

        /* Buttons */
        .btn {
            width: 100%;
            padding: 15px 25px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            font-weight: bold;
            transition: transform 0.1s, background 0.2s;
        }
        .btn:hover { transform: scale(1.02); }
        .btn:active { transform: scale(0.98); }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .btn-primary {
            background: #e94560;
            color: white;
        }
        .btn-primary:hover:not(:disabled) { background: #c73e54; }
        .btn-secondary {
            background: #0f3460;
            color: white;
            margin-bottom: 10px;
        }
        .btn-secondary:hover:not(:disabled) { background: #1a4a7a; }

        /* Alerts panel */
        .alert-summary {
            padding: 10px;
            background: #1a1a2e;
            border-radius: 8px;
            margin-top: 10px;
        }
        .alert-item {
            padding: 8px 0;
            border-bottom: 1px solid #333;
            font-size: 0.9em;
        }
        .alert-item:last-child { border-bottom: none; }
        .alert-critical { color: #e94560; }
        .alert-warning { color: #f39c12; }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8);
            z-index: 100;
            align-items: center;
            justify-content: center;
        }
        .modal-overlay.active { display: flex; }
        .modal {
            background: #16213e;
            padding: 25px;
            border-radius: 12px;
            max-width: 400px;
            width: 90%;
            text-align: center;
        }
        .modal h3 { margin-bottom: 15px; color: #e94560; }
        .modal p { margin-bottom: 15px; color: #aaa; line-height: 1.5; }
        .modal code {
            display: block;
            background: #1a1a2e;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            font-family: monospace;
        }
        .modal-actions {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        .modal-actions .btn { flex: 1; }

        /* Loading spinner */
        .spinner {
            display: none;
            width: 20px;
            height: 20px;
            border: 2px solid #fff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading .spinner { display: inline-block; }

        /* Footer */
        footer {
            text-align: center;
            padding: 20px;
            color: #555;
            font-size: 0.85em;
        }
    </style>
</head>
<body>
    <header>
        <h1>PoolAIssistant Launcher</h1>
        <div class="status-badge {{ status }}">{{ status }}</div>
    </header>

    <div class="container">
        <!-- Mode Selection -->
        <div class="section">
            <h2>Select Interaction Mode</h2>
            <div class="mode-options">
                <div class="mode-option">
                    <input type="radio" name="mode" id="mode-cli" value="cli"
                           {% if selected_mode == 'cli' %}checked{% endif %}>
                    <label for="mode-cli">
                        <span class="mode-name">CLI - Terminal Chat</span>
                        <span class="mode-desc">Interactive command-line session</span>
                    </label>
                </div>
                <div class="mode-option">
                    <input type="radio" name="mode" id="mode-web" value="web"
                           {% if selected_mode == 'web' %}checked{% endif %}>
                    <label for="mode-web">
                        <span class="mode-name">Web - Browser Interface</span>
                        <span class="mode-desc">Visual chat in web browser</span>
                    </label>
                </div>
                <div class="mode-option">
                    <input type="radio" name="mode" id="mode-sms" value="sms"
                           {% if selected_mode == 'sms' %}checked{% endif %}>
                    <label for="mode-sms">
                        <span class="mode-name">SMS - WhatsApp/SMS Webhook</span>
                        <span class="mode-desc">Receive alerts via messaging</span>
                    </label>
                </div>
            </div>
        </div>

        <!-- Data Sync Section -->
        <div class="section">
            <h2>Data Sync</h2>
            <div class="push-info">
                <span>Last push: <strong id="lastPush">{{ push_info.last_push }}</strong></span>
                <span>Today: <strong id="pushesToday">{{ push_info.pushes_today }}/{{ push_info.daily_limit }}</strong></span>
            </div>
            <div class="push-status {% if can_push %}ready{% else %}blocked{% endif %}" id="pushStatus">
                {{ push_message }}
            </div>
            <button class="btn btn-secondary" id="pushBtn" onclick="pushData()" {% if not can_push %}disabled{% endif %}>
                <span class="spinner" id="pushSpinner"></span>
                Push Data to Cloud
            </button>
        </div>

        <!-- Active Alerts -->
        {% if alerts %}
        <div class="section">
            <h2>Active Alerts ({{ alerts|length }})</h2>
            <div class="alert-summary">
                {% for alert in alerts[:5] %}
                <div class="alert-item alert-{{ alert.level|lower }}">
                    [{{ alert.level }}] {{ alert.pool }} {{ alert.sensor }}: {{ alert.current_value }}
                </div>
                {% endfor %}
                {% if alerts|length > 5 %}
                <div class="alert-item" style="color: #666;">+ {{ alerts|length - 5 }} more...</div>
                {% endif %}
            </div>
        </div>
        {% endif %}

        <!-- Launch Button -->
        <div class="section" style="border-left-color: #e94560;">
            <button class="btn btn-primary" id="initiateBtn" onclick="initiate()">
                <span class="spinner" id="initiateSpinner"></span>
                INITIATE
            </button>
        </div>
    </div>

    <footer>
        PoolAIssistant v1.0 | Swanwood Spa
    </footer>

    <!-- Modal -->
    <div class="modal-overlay" id="modal">
        <div class="modal">
            <h3 id="modalTitle">Launch Mode</h3>
            <p id="modalContent"></p>
            <div id="modalCode"></div>
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                <button class="btn btn-primary" id="modalAction" onclick="launchMode()">Launch</button>
            </div>
        </div>
    </div>

    <script>
        let selectedMode = '{{ selected_mode }}';

        // Save mode on change
        document.querySelectorAll('input[name="mode"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                selectedMode = e.target.value;
                fetch('/api/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({mode: selectedMode})
                });
            });
        });

        function pushData() {
            const btn = document.getElementById('pushBtn');
            const spinner = document.getElementById('pushSpinner');

            btn.disabled = true;
            btn.classList.add('loading');

            fetch('/api/push', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    btn.classList.remove('loading');

                    if (data.success) {
                        document.getElementById('pushStatus').className = 'push-status ready';
                        document.getElementById('pushStatus').textContent = 'Push complete!';
                        document.getElementById('lastPush').textContent = 'Just now';
                        document.getElementById('pushesToday').textContent =
                            data.pushes_today + '/' + data.daily_limit;

                        // Reload after brief delay to refresh status
                        setTimeout(() => location.reload(), 2000);
                    } else {
                        document.getElementById('pushStatus').className = 'push-status blocked';
                        document.getElementById('pushStatus').textContent = data.message;
                        btn.disabled = true;
                    }
                })
                .catch(err => {
                    btn.classList.remove('loading');
                    btn.disabled = false;
                    document.getElementById('pushStatus').textContent = 'Push failed: ' + err;
                });
        }

        function initiate() {
            const modal = document.getElementById('modal');
            const title = document.getElementById('modalTitle');
            const content = document.getElementById('modalContent');
            const codeDiv = document.getElementById('modalCode');
            const actionBtn = document.getElementById('modalAction');

            if (selectedMode === 'cli') {
                title.textContent = 'CLI Mode';
                content.textContent = 'Run this command in your terminal to start the CLI interface:';
                codeDiv.innerHTML = '<code>python run_technician.py cli</code>';
                actionBtn.textContent = 'Copy Command';
                actionBtn.onclick = () => {
                    navigator.clipboard.writeText('python run_technician.py cli');
                    actionBtn.textContent = 'Copied!';
                    setTimeout(() => closeModal(), 1000);
                };
            } else if (selectedMode === 'web') {
                title.textContent = 'Web Mode';
                content.textContent = 'The web interface will open in a new tab. Make sure to allow popups if blocked.';
                codeDiv.innerHTML = '<code>http://localhost:5000</code>';
                actionBtn.textContent = 'Open Web Interface';
                actionBtn.onclick = () => launchWeb();
            } else if (selectedMode === 'sms') {
                title.textContent = 'SMS/WhatsApp Mode';
                content.textContent = 'This will start the webhook server. Configure Twilio to point to:';
                codeDiv.innerHTML = '<code>http://YOUR_IP:5001/webhook</code>';
                actionBtn.textContent = 'Start Server';
                actionBtn.onclick = () => launchSMS();
            }

            modal.classList.add('active');
        }

        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }

        function launchWeb() {
            fetch('/api/initiate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: 'web'})
            }).then(r => r.json()).then(data => {
                if (data.url) {
                    window.open(data.url, '_blank');
                }
                closeModal();
            });
        }

        function launchSMS() {
            fetch('/api/initiate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: 'sms'})
            }).then(r => r.json()).then(data => {
                document.getElementById('modalContent').textContent = data.message;
                document.getElementById('modalAction').style.display = 'none';
            });
        }

        // Close modal on overlay click
        document.getElementById('modal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('modal')) {
                closeModal();
            }
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Main launcher page."""
    alerts_data = load_alerts()
    can_push_result, push_message, push_info = pusher.can_push()

    return render_template_string(
        HTML_TEMPLATE,
        status=alerts_data.get('status', 'UNKNOWN'),
        alerts=alerts_data.get('alerts', []),
        selected_mode=settings.get_mode(),
        can_push=can_push_result,
        push_message=push_message,
        push_info=push_info
    )


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Read/update settings."""
    if request.method == 'POST':
        data = request.get_json()
        if 'mode' in data:
            settings.set_mode(data['mode'])
        return jsonify({"success": True, "mode": settings.get_mode()})
    return jsonify(settings.config)


@app.route('/api/push', methods=['POST'])
def api_push():
    """Push data to cloud with rate limiting."""
    can_push_result, message, info = pusher.can_push()

    if not can_push_result:
        return jsonify({
            "success": False,
            "message": message,
            **info
        })

    # Execute full sync
    results = pusher.full_sync()

    # Get updated push info
    _, _, new_info = pusher.can_push()

    return jsonify({
        "success": results.get("push_status") == "success",
        "message": "Sync complete" if not results.get("errors") else "; ".join(results["errors"]),
        "sync_status": results.get("sync_status"),
        "alert_status": results.get("alert_status"),
        "alert_count": results.get("alert_count", 0),
        **new_info
    })


@app.route('/api/initiate', methods=['POST'])
def api_initiate():
    """Launch selected mode."""
    data = request.get_json()
    mode = data.get('mode', settings.get_mode())

    if mode == 'web':
        # Start web server in background and return URL
        # In production, the web server would already be running
        return jsonify({
            "success": True,
            "url": "http://localhost:5000",
            "message": "Opening web interface..."
        })

    elif mode == 'sms':
        # Return instructions for SMS setup
        return jsonify({
            "success": True,
            "message": "SMS server would start on port 5001. Run: python run_technician.py sms"
        })

    elif mode == 'cli':
        return jsonify({
            "success": True,
            "command": "python run_technician.py cli",
            "message": "Run the command in your terminal"
        })

    return jsonify({"success": False, "message": "Unknown mode"})


@app.route('/api/status', methods=['GET'])
def api_status():
    """Get current alerts status."""
    alerts_data = load_alerts()
    can_push_result, push_message, push_info = pusher.can_push()

    return jsonify({
        "status": alerts_data.get('status', 'UNKNOWN'),
        "alert_count": len(alerts_data.get('alerts', [])),
        "alerts": alerts_data.get('alerts', []),
        "trends": alerts_data.get('trends', []),
        "push": {
            "can_push": can_push_result,
            "message": push_message,
            **push_info
        }
    })


def run_launcher(host='0.0.0.0', port=8080):
    """Run the launcher server."""
    print(f"\nPoolAIssistant Launcher")
    print(f"=" * 40)
    print(f"Access at: http://localhost:{port}")
    print(f"Or from other devices: http://<your-ip>:{port}")
    print(f"=" * 40)
    print()
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="PoolAIssistant Launcher")
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')

    args = parser.parse_args()
    run_launcher(host=args.host, port=args.port)
