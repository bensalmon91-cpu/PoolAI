"""
AI Assistant Blueprint for PoolDash

Provides the AI chat interface for pool operators to:
- Answer questions from the system
- View AI-generated suggestions
- Request new questions ("Ask me something")
- Provide feedback on suggestions
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request, current_app

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

# Local SQLite database path
def get_db_path():
    """Get path to local AI database"""
    instance_path = Path(current_app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    return instance_path / 'ai_assistant.db'


def init_local_db():
    """Initialize local SQLite tables for offline caching"""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_questions_local (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER,
                queue_id INTEGER,
                text TEXT NOT NULL,
                input_type TEXT,
                options TEXT,
                pool TEXT,
                priority INTEGER DEFAULT 3,
                status TEXT DEFAULT 'pending',
                fetched_at TEXT,
                answered_at TEXT,
                answer TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_suggestions_local (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER,
                pool TEXT,
                title TEXT,
                body TEXT,
                suggestion_type TEXT,
                priority INTEGER DEFAULT 3,
                status TEXT DEFAULT 'unread',
                fetched_at TEXT,
                read_at TEXT,
                action_taken TEXT,
                user_feedback TEXT
            )
        ''')

        conn.commit()
        conn.close()
    except Exception as e:
        # Log error but don't crash the app
        import sys
        print(f"Warning: Failed to initialize AI database: {e}", file=sys.stderr)


def get_local_db():
    """Get SQLite connection"""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# Note: init_local_db() is called from __init__.py during app creation


@ai_bp.route('/')
def index():
    """Main AI Assistant interface"""
    # Get pending questions and unread suggestions from local cache
    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM ai_questions_local
        WHERE status = 'pending'
        ORDER BY priority DESC, id ASC
        LIMIT 5
    ''')
    questions = [dict(row) for row in cursor.fetchall()]

    cursor.execute('''
        SELECT * FROM ai_suggestions_local
        WHERE status IN ('unread', 'read')
        ORDER BY priority DESC, id DESC
        LIMIT 10
    ''')
    suggestions = [dict(row) for row in cursor.fetchall()]

    # Parse JSON options
    for q in questions:
        if q.get('options'):
            try:
                q['options'] = json.loads(q['options'])
            except (json.JSONDecodeError, TypeError):
                q['options'] = []

    cursor.execute('SELECT COUNT(*) FROM ai_questions_local WHERE status = "pending"')
    pending_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM ai_suggestions_local WHERE status = "unread"')
    unread_count = cursor.fetchone()[0]

    conn.close()

    return render_template('ai_assistant.html',
                         questions=questions,
                         suggestions=suggestions,
                         pending_count=pending_count,
                         unread_count=unread_count,
                         active_tab='AI')


@ai_bp.route('/api/questions')
def get_questions():
    """Get pending questions"""
    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM ai_questions_local
        WHERE status = 'pending'
        ORDER BY priority DESC, id ASC
    ''')
    questions = [dict(row) for row in cursor.fetchall()]

    for q in questions:
        if q.get('options'):
            try:
                q['options'] = json.loads(q['options'])
            except (json.JSONDecodeError, TypeError):
                q['options'] = []

    conn.close()

    return jsonify({'ok': True, 'questions': questions})


@ai_bp.route('/api/answer', methods=['POST'])
def submit_answer():
    """Submit answer to a question"""
    data = request.get_json()

    if not data or 'question_id' not in data or 'answer' not in data:
        return jsonify({'ok': False, 'error': 'Missing question_id or answer'}), 400

    question_id = data['question_id']
    answer = data['answer']
    answered_at = datetime.utcnow().isoformat()

    conn = get_local_db()
    cursor = conn.cursor()

    # Update local record
    cursor.execute('''
        UPDATE ai_questions_local
        SET status = 'answered', answer = ?, answered_at = ?
        WHERE id = ?
    ''', (answer, answered_at, question_id))

    # Get queue_id for server sync
    cursor.execute('SELECT queue_id FROM ai_questions_local WHERE id = ?', (question_id,))
    row = cursor.fetchone()
    queue_id = row['queue_id'] if row else None

    conn.commit()
    conn.close()

    # Mark for sync (will be handled by health_reporter)
    # For now, return success
    return jsonify({
        'ok': True,
        'message': 'Answer recorded',
        'queue_id': queue_id
    })


@ai_bp.route('/api/suggestions')
def get_suggestions():
    """Get suggestions"""
    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM ai_suggestions_local
        ORDER BY
            CASE status WHEN 'unread' THEN 0 ELSE 1 END,
            priority DESC,
            id DESC
        LIMIT 20
    ''')
    suggestions = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({'ok': True, 'suggestions': suggestions})


@ai_bp.route('/api/suggestion/<int:suggestion_id>/read', methods=['POST'])
def mark_suggestion_read(suggestion_id):
    """Mark a suggestion as read"""
    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE ai_suggestions_local
        SET status = 'read', read_at = ?
        WHERE id = ? AND status = 'unread'
    ''', (datetime.utcnow().isoformat(), suggestion_id))

    conn.commit()
    conn.close()

    return jsonify({'ok': True})


@ai_bp.route('/api/suggestion/<int:suggestion_id>/action', methods=['POST'])
def suggestion_action(suggestion_id):
    """Record action taken on suggestion"""
    data = request.get_json() or {}

    action = data.get('action', 'acted_upon')  # acted_upon or dismissed
    feedback = data.get('feedback', '')

    if action not in ('acted_upon', 'dismissed'):
        return jsonify({'ok': False, 'error': 'Invalid action'}), 400

    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE ai_suggestions_local
        SET status = ?, action_taken = ?, user_feedback = ?
        WHERE id = ?
    ''', (action, action, feedback, suggestion_id))

    conn.commit()
    conn.close()

    return jsonify({'ok': True})


@ai_bp.route('/api/ask-me', methods=['POST'])
def ask_me_something():
    """Request a new question from the server"""
    # This would normally make an API call to the server
    # For offline operation, we just return a message
    return jsonify({
        'ok': True,
        'message': 'Question request queued. New questions will appear on next sync.'
    })


@ai_bp.route('/api/stats')
def get_stats():
    """Get AI assistant statistics"""
    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM ai_questions_local WHERE status = "pending"')
    pending_questions = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM ai_questions_local WHERE status = "answered"')
    answered_questions = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM ai_suggestions_local WHERE status = "unread"')
    unread_suggestions = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM ai_suggestions_local WHERE status = "acted_upon"')
    acted_suggestions = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        'ok': True,
        'stats': {
            'pending_questions': pending_questions,
            'answered_questions': answered_questions,
            'unread_suggestions': unread_suggestions,
            'acted_suggestions': acted_suggestions
        }
    })


# Helper functions for health_reporter.py integration

def sync_from_server(questions, suggestions):
    """
    Sync questions and suggestions from server heartbeat response.
    Called by health_reporter.py after receiving heartbeat data.

    Args:
        questions: List of question dicts from server
        suggestions: List of suggestion dicts from server
    """
    conn = get_local_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    # Sync questions
    for q in questions:
        # Check if already exists
        cursor.execute(
            'SELECT id FROM ai_questions_local WHERE queue_id = ?',
            (q.get('queue_id'),)
        )
        existing = cursor.fetchone()

        if not existing:
            cursor.execute('''
                INSERT INTO ai_questions_local
                (server_id, queue_id, text, input_type, options, pool, priority, status, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            ''', (
                q.get('question_id'),
                q.get('queue_id'),
                q.get('text'),
                q.get('input_type', 'buttons'),
                json.dumps(q.get('options', [])),
                q.get('pool', ''),
                q.get('priority', 3),
                now
            ))

    # Sync suggestions
    for s in suggestions:
        cursor.execute(
            'SELECT id FROM ai_suggestions_local WHERE server_id = ?',
            (s.get('id'),)
        )
        existing = cursor.fetchone()

        if not existing:
            cursor.execute('''
                INSERT INTO ai_suggestions_local
                (server_id, pool, title, body, suggestion_type, priority, status, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, 'unread', ?)
            ''', (
                s.get('id'),
                s.get('pool', ''),
                s.get('title'),
                s.get('body'),
                s.get('type', 'general'),
                s.get('priority', 3),
                now
            ))

    conn.commit()
    conn.close()


def get_pending_responses():
    """
    Get answered questions that need to be synced to server.
    Called by health_reporter.py to include in heartbeat.

    Returns:
        List of response dicts to send to server
    """
    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, queue_id, answer, answered_at
        FROM ai_questions_local
        WHERE status = 'answered' AND queue_id IS NOT NULL
    ''')

    responses = []
    for row in cursor.fetchall():
        responses.append({
            'local_id': row['id'],
            'queue_id': row['queue_id'],
            'answer': row['answer'],
            'answered_at': row['answered_at']
        })

    conn.close()
    return responses


def mark_responses_synced(local_ids):
    """
    Mark responses as synced after successful server upload.
    Called by health_reporter.py after successful sync.

    Args:
        local_ids: List of local question IDs that were synced
    """
    if not local_ids:
        return

    conn = get_local_db()
    cursor = conn.cursor()

    placeholders = ','.join(['?' for _ in local_ids])
    cursor.execute(f'''
        UPDATE ai_questions_local
        SET status = 'synced'
        WHERE id IN ({placeholders})
    ''', local_ids)

    conn.commit()
    conn.close()


def get_suggestion_actions():
    """
    Get suggestion actions that need to be synced to server.
    Called by health_reporter.py to include in heartbeat.

    Returns:
        List of action dicts to send to server
    """
    conn = get_local_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, server_id, status, user_feedback
        FROM ai_suggestions_local
        WHERE status IN ('acted_upon', 'dismissed') AND server_id IS NOT NULL
    ''')

    actions = []
    for row in cursor.fetchall():
        actions.append({
            'local_id': row['id'],
            'suggestion_id': row['server_id'],
            'action': row['status'],
            'feedback': row['user_feedback']
        })

    conn.close()
    return actions


def mark_actions_synced(local_ids):
    """
    Mark suggestion actions as synced.
    Called by health_reporter.py after successful sync.

    Args:
        local_ids: List of local suggestion IDs that were synced
    """
    if not local_ids:
        return

    conn = get_local_db()
    cursor = conn.cursor()

    placeholders = ','.join(['?' for _ in local_ids])
    cursor.execute(f'''
        UPDATE ai_suggestions_local
        SET status = status || '_synced'
        WHERE id IN ({placeholders})
    ''', local_ids)

    conn.commit()
    conn.close()
