"""Local-account adapter; replaceable by an identity-provider integration."""
import sqlite3
from contextlib import closing
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash


class LocalAccounts:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS users '
                       '(username TEXT PRIMARY KEY, password_hash TEXT NOT NULL)')
        self._dummy_hash = generate_password_hash('unused-dummy-password')

    def create(self, username, password):
        if (not isinstance(username, str) or not username.isascii()
                or not 1 <= len(username) <= 80
                or not all(c.isalnum() or c in '._-' for c in username)):
            raise ValueError('Username must be 1–80 ASCII letters, digits, ., _, or -')
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError('Password must be 12–256 characters')
        with closing(sqlite3.connect(self.path)) as db, db:
            try:
                db.execute('INSERT INTO users VALUES (?, ?)',
                           (username, generate_password_hash(password)))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Username already exists') from exc

    def authenticate(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256:
            return False
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT password_hash FROM users WHERE username = ?',
                             (username,)).fetchone()
        matches = check_password_hash(row[0] if row else self._dummy_hash, password)
        return row is not None and matches
