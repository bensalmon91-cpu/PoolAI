"""
AI Sync Module for PoolDash

This module handles syncing AI questions and suggestions between the Pi and server.
Import this in health_reporter.py to add AI sync to heartbeat.

Usage in health_reporter.py:
    from ai_sync import get_ai_payload, process_ai_response

    # Before sending heartbeat, add AI data to health_data:
    health_data['ai'] = get_ai_payload()

    # After receiving heartbeat response:
    if response and 'ai' in response:
        process_ai_response(response['ai'])
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

# Database path - same as used by Flask blueprint
DB_PATH = None

def get_db_path():
    """Get path to AI database"""
    global DB_PATH
    if DB_PATH is None:
        # Try Flask instance path first, fall back to home directory
        instance_path = Path.home() / '.pooldash' / 'ai_assistant.db'
        instance_path.parent.mkdir(parents=True, exist_ok=True)
        DB_PATH = instance_path
    return DB_PATH

def set_db_path(path):
    """Set custom database path"""
    global DB_PATH
    DB_PATH = Path(path)

def init_db():
    """Initialize AI database tables if they don't exist"""
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
    log.info(f"AI database initialized at {db_path}")

def get_db():
    """Get database connection"""
    init_db()  # Ensure tables exist
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def get_ai_payload():
    """
    Get AI data to include in heartbeat request.

    Returns dict with:
        - responses: Answered questions to sync to server
        - suggestion_actions: Suggestion feedback to sync
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Get answered questions that need syncing
        cursor.execute('''
            SELECT id, queue_id, answer, answered_at
            FROM ai_questions_local
            WHERE status = 'answered' AND queue_id IS NOT NULL
        ''')

        responses = []
        for row in cursor.fetchall():
            responses.append({
                'queue_id': row['queue_id'],
                'answer': row['answer'],
                'answered_at': row['answered_at']
            })

        # Get suggestion actions that need syncing
        cursor.execute('''
            SELECT id, server_id, status, user_feedback
            FROM ai_suggestions_local
            WHERE status IN ('acted_upon', 'dismissed', 'read')
            AND server_id IS NOT NULL
        ''')

        suggestion_actions = []
        for row in cursor.fetchall():
            suggestion_actions.append({
                'suggestion_id': row['server_id'],
                'action': row['status'],
                'feedback': row['user_feedback'] or ''
            })

        conn.close()

        if responses or suggestion_actions:
            log.info(f"AI payload: {len(responses)} responses, {len(suggestion_actions)} actions")

        return {
            'responses': responses,
            'suggestion_actions': suggestion_actions
        }

    except Exception as e:
        log.error(f"Error getting AI payload: {e}")
        return {'responses': [], 'suggestion_actions': []}

def process_ai_response(ai_data):
    """
    Process AI data from heartbeat response.

    Args:
        ai_data: Dict with 'questions' and 'suggestions' from server
    """
    if not ai_data:
        return

    try:
        conn = get_db()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        questions = ai_data.get('questions', [])
        suggestions = ai_data.get('suggestions', [])

        # Store new questions
        for q in questions:
            queue_id = q.get('queue_id')
            if not queue_id:
                continue

            # Check if already exists
            cursor.execute(
                'SELECT id FROM ai_questions_local WHERE queue_id = ?',
                (queue_id,)
            )
            if cursor.fetchone():
                continue  # Already have this question

            cursor.execute('''
                INSERT INTO ai_questions_local
                (server_id, queue_id, text, input_type, options, pool, priority, status, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            ''', (
                q.get('question_id'),
                queue_id,
                q.get('text'),
                q.get('input_type', 'buttons'),
                json.dumps(q.get('options', [])),
                q.get('pool', ''),
                q.get('priority', 3),
                now
            ))
            log.info(f"New AI question received: {q.get('text', '')[:50]}...")

        # Store new suggestions
        for s in suggestions:
            server_id = s.get('id')
            if not server_id:
                continue

            cursor.execute(
                'SELECT id FROM ai_suggestions_local WHERE server_id = ?',
                (server_id,)
            )
            if cursor.fetchone():
                continue  # Already have this suggestion

            cursor.execute('''
                INSERT INTO ai_suggestions_local
                (server_id, pool, title, body, suggestion_type, priority, status, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, 'unread', ?)
            ''', (
                server_id,
                s.get('pool', ''),
                s.get('title'),
                s.get('body'),
                s.get('type', 'general'),
                s.get('priority', 3),
                now
            ))
            log.info(f"New AI suggestion received: {s.get('title', '')[:50]}...")

        # Mark synced responses as synced
        if ai_data.get('responses_synced'):
            cursor.execute('''
                UPDATE ai_questions_local
                SET status = 'synced'
                WHERE status = 'answered'
            ''')

        # Mark synced actions as synced
        if ai_data.get('actions_synced'):
            cursor.execute('''
                UPDATE ai_suggestions_local
                SET status = status || '_synced'
                WHERE status IN ('acted_upon', 'dismissed', 'read')
                AND server_id IS NOT NULL
            ''')

        conn.commit()
        conn.close()

        if questions or suggestions:
            log.info(f"AI sync complete: {len(questions)} questions, {len(suggestions)} suggestions")

    except Exception as e:
        log.error(f"Error processing AI response: {e}")

def get_pending_question_count():
    """Get count of pending questions"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM ai_questions_local WHERE status = "pending"')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

def get_unread_suggestion_count():
    """Get count of unread suggestions"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM ai_suggestions_local WHERE status = "unread"')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0
