"""
PoolAIssistant Web Interface for Technicians
Flask-based web interface for pool technician interactions.
"""

from flask import Flask, render_template_string, request, jsonify, session
from technician_interface import TechnicianInterface
import secrets
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Store active sessions
sessions = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>PoolAIssistant - Technician Interface</title>
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
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: #16213e;
            padding: 20px;
            text-align: center;
            border-bottom: 2px solid #0f3460;
        }
        h1 { color: #e94560; font-size: 1.5em; }
        .status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-top: 10px;
        }
        .status.CRITICAL { background: #e94560; }
        .status.WARNING { background: #f39c12; color: #000; }
        .status.OK { background: #27ae60; }
        .chat-container {
            height: calc(100vh - 250px);
            overflow-y: auto;
            padding: 20px 0;
        }
        .message {
            margin: 10px 0;
            padding: 15px;
            border-radius: 15px;
            max-width: 85%;
        }
        .ai-message {
            background: #16213e;
            margin-right: auto;
            border-bottom-left-radius: 5px;
        }
        .user-message {
            background: #0f3460;
            margin-left: auto;
            border-bottom-right-radius: 5px;
            text-align: right;
        }
        .input-area {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #16213e;
            padding: 15px;
            border-top: 2px solid #0f3460;
        }
        .input-row {
            display: flex;
            max-width: 600px;
            margin: 0 auto;
            gap: 10px;
        }
        input[type="text"] {
            flex: 1;
            padding: 15px;
            border: none;
            border-radius: 25px;
            background: #1a1a2e;
            color: #eee;
            font-size: 16px;
        }
        button {
            padding: 15px 25px;
            background: #e94560;
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover { background: #c73e54; }
        .quick-replies {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }
        .quick-reply {
            padding: 8px 15px;
            background: #0f3460;
            border: 1px solid #e94560;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
        }
        .quick-reply:hover { background: #e94560; }
        .alerts-panel {
            background: #16213e;
            padding: 15px;
            margin: 10px 0;
            border-radius: 10px;
            border-left: 4px solid #e94560;
        }
        .alert-item {
            padding: 5px 0;
            font-size: 0.9em;
        }
        .done-btn {
            background: #27ae60;
            margin-top: 10px;
            width: 100%;
        }
    </style>
</head>
<body>
    <header>
        <h1>🏊 PoolAIssistant</h1>
        <div class="status {{ status }}">{{ status }}</div>
    </header>

    <div class="container">
        {% if alerts %}
        <div class="alerts-panel">
            <strong>Active Alerts:</strong>
            {% for alert in alerts %}
            <div class="alert-item">
                ⚠️ {{ alert.pool }} {{ alert.sensor }}: {{ alert.current_value }}
                (normal: {{ alert.normal_range }})
            </div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="chat-container" id="chat">
            <!-- Messages will be inserted here -->
        </div>
    </div>

    <div class="input-area">
        <div class="input-row">
            <input type="text" id="userInput" placeholder="Type your response..."
                   onkeypress="if(event.key==='Enter')sendMessage()">
            <button onclick="sendMessage()">Send</button>
        </div>
        <div class="quick-replies">
            <span class="quick-reply" onclick="quickReply('Yes, that\\'s correct')">Yes ✓</span>
            <span class="quick-reply" onclick="quickReply('No, that\\'s not right')">No ✗</span>
            <span class="quick-reply" onclick="quickReply('I\\'m not sure')">Not sure</span>
            <span class="quick-reply" onclick="quickReply('It\\'s under maintenance')">Maintenance</span>
        </div>
        <button class="done-btn" onclick="finishSession()">Finish Session</button>
    </div>

    <script>
        const chat = document.getElementById('chat');

        function addMessage(text, isUser) {
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user-message' : 'ai-message');
            div.textContent = text;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        // Load initial message
        fetch('/api/start', {method: 'POST'})
            .then(r => r.json())
            .then(data => addMessage(data.message, false));

        function sendMessage() {
            const input = document.getElementById('userInput');
            const text = input.value.trim();
            if (!text) return;

            addMessage(text, true);
            input.value = '';

            fetch('/api/respond', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: text})
            })
            .then(r => r.json())
            .then(data => addMessage(data.message, false));
        }

        function quickReply(text) {
            document.getElementById('userInput').value = text;
            sendMessage();
        }

        function finishSession() {
            fetch('/api/finish', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    addMessage('--- Session Summary ---', false);
                    addMessage(data.summary, false);
                    if (data.changes_suggested) {
                        if (confirm('Apply suggested threshold changes?')) {
                            fetch('/api/apply-changes', {method: 'POST'})
                                .then(r => r.json())
                                .then(d => addMessage('Changes applied: ' + d.changes.join(', '), false));
                        }
                    }
                });
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Main page."""
    interface = get_or_create_interface()
    return render_template_string(
        HTML_TEMPLATE,
        status=interface.alerts.get('status', 'UNKNOWN'),
        alerts=interface.alerts.get('alerts', [])
    )


def get_or_create_interface():
    """Get or create interface for current session."""
    session_id = session.get('id')
    if not session_id or session_id not in sessions:
        session_id = secrets.token_hex(8)
        session['id'] = session_id
        sessions[session_id] = TechnicianInterface()
    return sessions[session_id]


@app.route('/api/start', methods=['POST'])
def start_session():
    """Start a new conversation."""
    interface = get_or_create_interface()
    opening = interface.generate_initial_questions()
    interface.conversation_history.append({"role": "assistant", "content": opening})
    return jsonify({"message": opening})


@app.route('/api/respond', methods=['POST'])
def respond():
    """Process technician response."""
    interface = get_or_create_interface()
    data = request.get_json()
    message = data.get('message', '')

    response = interface.process_response(message)
    return jsonify({"message": response})


@app.route('/api/finish', methods=['POST'])
def finish_session():
    """Finish session and extract learnings."""
    interface = get_or_create_interface()
    learnings = interface.extract_learnings()
    interface.save_session(learnings)

    summary_parts = []
    if learnings.get('threshold_adjustments'):
        summary_parts.append(f"{len(learnings['threshold_adjustments'])} threshold adjustments suggested")
    if learnings.get('issues_confirmed'):
        summary_parts.append(f"{len(learnings['issues_confirmed'])} issues confirmed")
    if learnings.get('issues_dismissed'):
        summary_parts.append(f"{len(learnings['issues_dismissed'])} alerts explained")

    return jsonify({
        "summary": "; ".join(summary_parts) if summary_parts else "No changes needed",
        "learnings": learnings,
        "changes_suggested": bool(learnings.get('threshold_adjustments'))
    })


@app.route('/api/apply-changes', methods=['POST'])
def apply_changes():
    """Apply learned threshold changes."""
    interface = get_or_create_interface()
    learnings = interface.extract_learnings()
    changes = interface.apply_learnings_to_config(learnings)
    return jsonify({"changes": changes})


def run_web_server(host='0.0.0.0', port=5000):
    """Run the web server."""
    print(f"\n🏊 PoolAIssistant Web Interface")
    print(f"   Access at: http://localhost:{port}")
    print(f"   Or from other devices: http://<your-ip>:{port}\n")
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    run_web_server()
