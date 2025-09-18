import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = "pawforum.db"

DEFAULT_CHANNELS = [
    ("general", "General"),
    ("curiosities", "Curiosities"),
    ("tips-and-advice", "Tips & Advice"),
    ("adoptions", "Adoptions"),
    ("support-corner", "Support Corner"),
]


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with get_conn() as con:
        cur = con.cursor()
        # users
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                google_sub TEXT UNIQUE,
                email TEXT,
                name TEXT,
                avatar_url TEXT
            )
            """
        )
        # channels
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        # messages
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                user TEXT NOT NULL,
                text TEXT,
                image_path TEXT,
                ts INTEGER NOT NULL,
                FOREIGN KEY(channel_id) REFERENCES channels(id)
            )
            """
        )
        # seed canales
        cur.execute("SELECT COUNT(*) FROM channels")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO channels (id, name) VALUES (?, ?)", DEFAULT_CHANNELS)
        con.commit()


# ---- users ----
from passlib.hash import bcrypt

def create_user(username: str, password: str) -> Optional[str]:
    username = (username or '').strip()
    password = (password or '').strip()
    if not username or not password:
        return "Username and password are required."
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    pw_hash = bcrypt.hash(password)
    with get_conn() as con:
        try:
            con.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, pw_hash, int(time.time())),
            )
            con.commit()
        except sqlite3.IntegrityError:
            return "Username already exists."
    return None


def verify_user(username: str, password: str) -> bool:
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
    if not row:
        return False
    return bcrypt.verify(password, row[0])


def upsert_google_user(sub: str, email: str, name: str | None, avatar: str | None):
    username = email
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT username FROM users WHERE google_sub = ?", (sub,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("SELECT username FROM users WHERE email = ?", (email,))
        row2 = cur.fetchone()
        if row2:
            con.execute(
                "UPDATE users SET google_sub = ?, name = ?, avatar_url = ? WHERE email = ?",
                (sub, name, avatar, email),
            )
            con.commit()
            return row2[0]
        con.execute(
            "INSERT INTO users (username, password_hash, created_at, google_sub, email, name, avatar_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, "", int(time.time()), sub, email, name, avatar),
        )
        con.commit()
        return username


# ---- channels & messages ----

def list_channels() -> List[Dict[str, Any]]:
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM channels ORDER BY name ASC")
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def insert_channel(channel_id: str, name: str) -> Optional[str]:
    import re
    channel_id = (channel_id or '').strip().lower().replace(' ', '-')
    if not re.match(r'^[a-z0-9\-]{3,}$', channel_id or ''):
        return "Channel id must be 3+ chars, lowercase, digits or dashes."
    name = (name or '').strip()
    if not name:
        return "Display name is required."
    with get_conn() as con:
        try:
            con.execute("INSERT INTO channels (id, name) VALUES (?, ?)", (channel_id, name))
            con.commit()
        except sqlite3.IntegrityError:
            return "Channel id already exists."
    return None


def list_messages(channel_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT user, text, image_path, ts FROM messages WHERE channel_id = ? ORDER BY ts ASC LIMIT ?",
            (channel_id, limit),
        )
        rows = cur.fetchall()
    return [
        {"user": r[0], "text": r[1], "image_path": r[2], "ts": r[3]}
        for r in rows
    ]


def add_message(channel_id: str, user: str, text: str = "", image_path: str | None = None):
    ts = int(time.time())
    with get_conn() as con:
        con.execute(
            "INSERT INTO messages (channel_id, user, text, image_path, ts) VALUES (?, ?, ?, ?, ?)",
            (channel_id, user, text, image_path, ts),
        )
        con.commit()