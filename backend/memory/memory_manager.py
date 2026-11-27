"""
JARVIS / PHOEBE - CONVERSATIONAL MEMORY & PERSISTENCE
=====================================================
SQLite-backed persistent memory engine storing:
  - Conversation sessions and historical turns
  - Deep research reports and artifacts
  - Long-term user preferences
  - User-controlled memory wiping
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = _ROOT / "data" / "memory.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class MemoryManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create memory tables if not present."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    action_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    spoken_summary TEXT,
                    markdown_report TEXT NOT NULL,
                    sources_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_message(self, role: str, content: str, session_id: str = "default", action_type: str = "chat"):
        """Record a single message in persistent memory."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, action_type) VALUES (?, ?, ?, ?)",
                    (session_id, role, content, action_type),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Could not persist message: %s", e)

    def get_recent_history(self, session_id: str = "default", limit: int = 10) -> List[Dict[str, str]]:
        """Retrieve recent conversation history formatted for Ollama messages."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
                # Reverse to chronological order
                return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        except Exception as e:
            logger.warning("Could not retrieve history: %s", e)
            return []

    def save_research_report(self, query: str, spoken: str, report: str, sources: List[Dict[str, Any]]):
        """Save a completed deep research report."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO research_reports (query, spoken_summary, markdown_report, sources_json) VALUES (?, ?, ?, ?)",
                    (query, spoken, report, json.dumps(sources)),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Could not persist research report: %s", e)

    def get_recent_research(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve past research reports."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT query, spoken_summary, markdown_report, sources_json, created_at FROM research_reports ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                out = []
                for r in rows:
                    out.append({
                        "query": r["query"],
                        "spoken_summary": r["spoken_summary"],
                        "markdown_report": r["markdown_report"],
                        "sources": json.loads(r["sources_json"]) if r["sources_json"] else [],
                        "created_at": r["created_at"],
                    })
                return out
        except Exception as e:
            logger.warning("Could not retrieve research: %s", e)
            return []

    def set_preference(self, key: str, value: str):
        """Set a persistent user preference."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO user_preferences (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

    def get_preference(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a persistent user preference."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM user_preferences WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def clear_history(self, session_id: Optional[str] = None):
        """Clear conversation history (user-controlled memory wiping)."""
        with self._get_connection() as conn:
            if session_id:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            else:
                conn.execute("DELETE FROM messages")
            conn.commit()

    def clear_all(self):
        """Wipe all stored conversations, research, and preferences."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM research_reports")
            conn.execute("DELETE FROM user_preferences")
            conn.commit()


_memory_instance: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = MemoryManager()
    return _memory_instance
