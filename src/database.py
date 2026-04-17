"""
SQLite database layer for Safwa Bank RAG System.
Manages: user accounts, sessions, chat history.
"""
import sqlite3
import uuid
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import DB_FILE


@contextmanager
def get_conn():
    """Thread-safe SQLite connection context manager."""
    conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL") 
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                employee_id     TEXT PRIMARY KEY,
                full_name       TEXT NOT NULL,
                department      TEXT NOT NULL,
                role            TEXT NOT NULL,
                job_title       TEXT DEFAULT '',
                created_at      TEXT DEFAULT (datetime('now')),
                last_login      TEXT
            );

            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                employee_id     TEXT NOT NULL,
                title           TEXT DEFAULT 'New Conversation',
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (employee_id) REFERENCES users(employee_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                employee_id     TEXT NOT NULL,
                role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content         TEXT NOT NULL,
                sources         TEXT DEFAULT '[]',
                timestamp       TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            );
        """)



def register_user(employee_id: str, full_name: str, department: str, role: str, job_title: str = "") -> dict:
    """Register a new user. Returns user dict or raises on duplicate."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT employee_id FROM users WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if existing:
            raise ValueError(f"Employee ID '{employee_id}' is already registered.")
        conn.execute(
            """INSERT INTO users (employee_id, full_name, department, role, job_title)
               VALUES (?, ?, ?, ?, ?)""",
            (employee_id, full_name, department, role, job_title)
        )
    return get_user(employee_id)


def login_user(employee_id: str) -> dict | None:
    """Validate login by employee_id. Updates last_login. Returns user dict or None."""
    with get_conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if user:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE employee_id = ?",
                (datetime.now().isoformat(), employee_id)
            )
            return dict(user)
    return None


def get_user(employee_id: str) -> dict | None:
    """Fetch a single user by employee_id."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        return dict(row) if row else None



def create_conversation(employee_id: str) -> str:
    """Create a new conversation. Returns conversation_id."""
    conv_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (conversation_id, employee_id) VALUES (?, ?)",
            (conv_id, employee_id)
        )
    return conv_id


def get_conversations(employee_id: str) -> list[dict]:
    """Get all conversations for a user, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.conversation_id, c.title, c.updated_at,
                      (SELECT content FROM messages WHERE conversation_id = c.conversation_id
                       AND role = 'user' ORDER BY id ASC LIMIT 1) as first_message
               FROM conversations c
               WHERE c.employee_id = ?
               ORDER BY c.updated_at DESC
               LIMIT 30""",
            (employee_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_conversation_title(conv_id: str, title: str):
    """Update conversation title (set from first user message)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE conversation_id = ?",
            (title[:80], datetime.now().isoformat(), conv_id)
        )


def touch_conversation(conv_id: str):
    """Update conversation updated_at timestamp."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
            (datetime.now().isoformat(), conv_id)
        )



def save_message(conv_id: str, employee_id: str, role: str, content: str, sources: str = "[]"):
    """Persist a single message."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO messages (conversation_id, employee_id, role, content, sources)
               VALUES (?, ?, ?, ?, ?)""",
            (conv_id, employee_id, role, content, sources)
        )
    touch_conversation(conv_id)


def get_messages(conv_id: str) -> list[dict]:
    """Get all messages in a conversation."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content, sources, timestamp
               FROM messages WHERE conversation_id = ?
               ORDER BY id ASC""",
            (conv_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_messages(conv_id: str, limit: int = 8) -> list[dict]:
    """Get the last N messages for context window."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages
               WHERE conversation_id = ?
               ORDER BY id DESC LIMIT ?""",
            (conv_id, limit)
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))