import sqlite3
from pathlib import Path

DATABASE = Path(__file__).parent / "security.db"


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sensitive_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                nonce BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id)
                    REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS access_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id)
                    REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS record_capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (record_id)
                    REFERENCES sensitive_records(id)
                    ON DELETE CASCADE
            );
        """)


def create_user(username, password_hash):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash)
            VALUES (?, ?)
            """,
            (username, password_hash)
        )
        return cursor.lastrowid


def get_user_by_username(username):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()


def create_owned_capability(record_id, owner_id, token_hash):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO record_capabilities
            (record_id, token_hash, expires_at)
            SELECT id, ?, datetime('now', '+15 minutes')
            FROM sensitive_records
            WHERE id = ? AND owner_id = ?
            """,
            (token_hash, record_id, owner_id)
        )
        return cursor.rowcount == 1


def get_capability(token_hash):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT r.id, r.owner_id, r.label,
                   r.ciphertext, r.nonce
            FROM record_capabilities AS c
            JOIN sensitive_records AS r
                ON c.record_id = r.id
            WHERE c.token_hash = ?
              AND c.expires_at > CURRENT_TIMESTAMP
            """,
            (token_hash,)
        ).fetchone()
