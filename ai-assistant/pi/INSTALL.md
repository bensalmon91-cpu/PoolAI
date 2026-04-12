# AI Assistant - Pi Installation Guide

## Files to Deploy

Copy these files to your Pi device:

```
ai-assistant/pi/
├── ai_sync.py              → /home/pi/PoolDash_v6/scripts/ai_sync.py
├── blueprints/
│   └── ai_assistant.py     → /home/pi/PoolDash_v6/pooldash_app/blueprints/ai_assistant.py
└── templates/
    └── ai_assistant.html   → /home/pi/PoolDash_v6/pooldash_app/templates/ai_assistant.html
```

## Step 1: Copy Files

```bash
# On your Pi, from the PoolDash_v6 directory:
cd /home/pi/PoolDash_v6

# Copy ai_sync.py to scripts
cp /path/to/ai_sync.py scripts/

# Copy blueprint
cp /path/to/ai_assistant.py pooldash_app/blueprints/

# Copy template
cp /path/to/ai_assistant.html pooldash_app/templates/
```

## Step 2: Register Flask Blueprint

Edit `/home/pi/PoolDash_v6/pooldash_app/__init__.py`:

```python
# Add this import near the top with other blueprint imports
from pooldash_app.blueprints.ai_assistant import ai_bp

# Add this where other blueprints are registered (look for app.register_blueprint)
app.register_blueprint(ai_bp)
```

## Step 3: Integrate with Health Reporter

Edit `/home/pi/PoolDash_v6/scripts/health_reporter.py`:

### Add import at top:
```python
from ai_sync import get_ai_payload, process_ai_response
```

### Modify the heartbeat data (around line 530):
Find where `health_data` is built and add:
```python
# AI Assistant sync
health_data['ai'] = get_ai_payload()
```

### Process the response (around line 548):
After `response = send_heartbeat(settings, health_data)`, add:
```python
# Process AI sync response
if response and 'ai' in response:
    process_ai_response(response['ai'])
```

## Step 4: Add Navigation Link (Optional)

Edit the base template to add a link to the AI Assistant:
```html
<a href="/ai/">AI Assistant</a>
```

## Step 5: Restart Services

```bash
sudo systemctl restart pooldash
```

## Verification

1. Visit `http://<pi-ip>:5000/ai/` to see the AI Assistant interface
2. Check logs for AI sync messages:
   ```bash
   journalctl -u pooldash -f | grep -i ai
   ```

## Database Location

The AI data is stored locally at:
- `~/.pooldash/ai_assistant.db`

This SQLite database caches questions and suggestions for offline operation.
