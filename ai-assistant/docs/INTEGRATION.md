# Integration Guide

This document explains how to integrate the AI Assistant into the existing PoolAIssistant codebase.

## Server-Side Integration

### 1. Database Migration

Run the schema migration on Hostinger MySQL:

```sql
-- Connect to your database and run:
SOURCE /path/to/schema_ai.sql;
```

Or via phpMyAdmin:
1. Login to Hostinger panel
2. Go to Databases → phpMyAdmin
3. Select your database
4. Click "Import"
5. Upload `database/schema_ai.sql`

### 2. Environment Configuration

Add Claude API key to `.env` on Hostinger:

```bash
# Add this line to your existing .env file
CLAUDE_API_KEY=sk-ant-api03-your-key-here
```

Get your API key from: https://console.anthropic.com/

### 3. File Deployment

Copy files to your `php_deploy/` directory:

```bash
# From the ai-assistant directory:

# API endpoints
cp php/api/ai/*.php ../web-portal/php_deploy/api/ai/

# Admin pages
cp php/admin/ai_*.php ../web-portal/php_deploy/admin/

# Claude wrapper
cp php/includes/claude_api.php ../web-portal/php_deploy/includes/
```

### 4. Heartbeat Integration

Modify `php_deploy/api/heartbeat.php` to include AI data:

**After line 91** (after the health insert), add:

```php
// AI Assistant Integration
require_once __DIR__ . '/ai/heartbeat_extension.php';

// Process incoming AI responses/actions
if (!empty($input['ai'])) {
    processAIHeartbeatInput($pdo, $device_id, $input['ai']);
}

// Get AI data for response
$ai_data = getAIHeartbeatData($pdo, $device_id);
```

**Modify the jsonResponse** (around line 154):

```php
jsonResponse([
    'ok' => true,
    'commands' => $commands,
    'alias_sync' => $sync_alias,
    'ai' => $ai_data  // ADD THIS LINE
]);
```

### 5. Admin Navigation

Add AI dashboard link to `php_deploy/admin/index.php`:

**In the header section** (around line 244), add before the logout button:

```html
<nav style="display: flex; gap: 8px; margin-right: 16px;">
    <a href="ai_dashboard.php" class="logout-btn" style="background: #8b5cf6;">AI Assistant</a>
</nav>
```

Or add a full navigation bar by inserting this after the header opening tag:

```html
<nav style="display: flex; gap: 8px; margin-bottom: 20px;">
    <a href="index.php" class="logout-btn" style="background: var(--accent);">Devices</a>
    <a href="ai_dashboard.php" class="logout-btn" style="background: #8b5cf6;">AI Assistant</a>
</nav>
```

---

## Pi-Side Integration

### 1. Flask Blueprint

Copy the blueprint file:

```bash
cp pi/blueprints/ai_assistant.py ../pi-software/PoolDash_v6/pooldash_app/blueprints/
```

### 2. Template

Copy the template:

```bash
cp pi/templates/ai_assistant.html ../pi-software/PoolDash_v6/pooldash_app/templates/
```

### 3. Register Blueprint

Edit `pooldash_app/__init__.py` to register the blueprint:

```python
# Add import at top
from .blueprints.ai_assistant import ai_bp

# In create_app(), add after other blueprint registrations:
app.register_blueprint(ai_bp)
```

### 4. Add Navigation Link

Edit `pooldash_app/templates/base.html` to add AI tab:

Find the navigation section and add:

```html
<a href="{{ url_for('ai.index') }}" class="nav-item {% if request.endpoint and request.endpoint.startswith('ai.') %}active{% endif %}">
    AI Assistant
    {% if ai_pending_count > 0 %}
    <span class="badge">{{ ai_pending_count }}</span>
    {% endif %}
</a>
```

### 5. Health Reporter Integration

Modify `scripts/health_reporter.py` to sync AI data:

**Add import:**
```python
from pooldash_app.blueprints.ai_assistant import (
    sync_from_server,
    get_pending_responses,
    mark_responses_synced,
    get_suggestion_actions,
    mark_actions_synced
)
```

**In the heartbeat function, add to the payload:**
```python
# Get pending AI responses to send
ai_responses = get_pending_responses()
ai_actions = get_suggestion_actions()

payload = {
    # ... existing fields ...
    'ai': {
        'responses': ai_responses,
        'suggestion_actions': ai_actions
    }
}
```

**After successful heartbeat, sync received data:**
```python
if response.get('ok'):
    # ... existing command handling ...

    # Sync AI data
    ai_data = response.get('ai', {})
    if ai_data:
        sync_from_server(
            ai_data.get('questions', []),
            ai_data.get('suggestions', [])
        )

    # Mark synced responses
    if ai_responses:
        mark_responses_synced([r['local_id'] for r in ai_responses])
    if ai_actions:
        mark_actions_synced([a['local_id'] for a in ai_actions])
```

---

## Verification

### Server

1. Visit `/admin/ai_dashboard.php` - should show stats
2. Visit `/admin/ai_questions.php` - should show seeded questions
3. Test API: `curl https://your-domain/api/ai/questions.php` (with auth)

### Pi

1. Visit `/ai` on the Pi interface
2. Should show "All caught up!" if no questions pending
3. Check Flask logs for any blueprint errors

---

## Troubleshooting

### "Claude API key not configured"

Ensure `CLAUDE_API_KEY` is in your `.env` file and the file is being loaded.

### Questions not appearing on Pi

1. Check heartbeat response includes `ai` data
2. Verify questions are queued: Check `ai_question_queue` table
3. Check Pi logs for sync errors

### Admin pages show database errors

1. Verify schema migration ran successfully
2. Check all AI tables exist
3. Verify database user has permissions

### Suggestions not generating

1. Ensure Claude API key is valid
2. Check `ai_conversation_log` for errors
3. Verify `/api/ai/generate.php` endpoint works
