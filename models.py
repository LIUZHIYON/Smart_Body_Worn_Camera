"""
Smart Body Worn Camera - Data Models (SQLite)
Demonstrates: Singleton pattern, SQLite CRUD, MVC Model layer
"""
import sqlite3
import os
import time
from threading import Lock

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "camera.db")


class Database:
    """Singleton database manager."""
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._seed_admin()

    def _create_tables(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                realName TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                format TEXT DEFAULT 'h264',
                duration REAL DEFAULT 0,
                size INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );
        """)
        self.conn.commit()

    def _seed_admin(self):
        c = self.conn.cursor()
        c.execute("SELECT id FROM users WHERE username='admin'")
        if not c.fetchone():
            c.execute(
                "INSERT INTO users (username, password, realName, role) VALUES (?,?,?,?)",
                ("admin", "admin123", "系统管理员", "admin"))
            self.conn.commit()

    # ── User ─────────────────────────────────────────────────────────────

    def authenticate(self, username, password):
        c = self.conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=? AND status='active'",
                  (username, password))
        return c.fetchone()

    def add_user(self, username, password, realName=""):
        c = self.conn.cursor()
        try:
            c.execute("INSERT INTO users (username,password,realName) VALUES (?,?,?)",
                      (username, password, realName))
            self.conn.commit()
            return True, "注册成功"
        except sqlite3.IntegrityError:
            return False, "用户名已存在"

    # ── Logs ─────────────────────────────────────────────────────────────

    def add_log(self, action, detail=""):
        c = self.conn.cursor()
        c.execute("INSERT INTO logs (action, detail) VALUES (?,?)", (action, detail))
        self.conn.commit()

    def get_logs(self, limit=100):
        c = self.conn.cursor()
        c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
        return c.fetchall()

    # ── Photos ───────────────────────────────────────────────────────────

    def add_photo(self, filename, path):
        c = self.conn.cursor()
        c.execute("INSERT INTO photos (filename, path) VALUES (?,?)", (filename, path))
        self.conn.commit()

    def get_photos(self, limit=50):
        c = self.conn.cursor()
        c.execute("SELECT * FROM photos ORDER BY id DESC LIMIT ?", (limit,))
        return c.fetchall()

    # ── Videos ───────────────────────────────────────────────────────────

    def add_video(self, filename, path, fmt="h264", duration=0, size=0):
        c = self.conn.cursor()
        c.execute("INSERT INTO videos (filename, path, format, duration, size) VALUES (?,?,?,?,?)",
                  (filename, path, fmt, duration, size))
        self.conn.commit()

    def get_videos(self, limit=50):
        c = self.conn.cursor()
        c.execute("SELECT * FROM videos ORDER BY id DESC LIMIT ?", (limit,))
        return c.fetchall()

    def get_video_by_id(self, vid):
        c = self.conn.cursor()
        c.execute("SELECT * FROM videos WHERE id=?", (vid,))
        return c.fetchone()

    # ── Settings ─────────────────────────────────────────────────────────

    def get_setting(self, key, default=""):
        c = self.conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        c = self.conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        self.conn.commit()
