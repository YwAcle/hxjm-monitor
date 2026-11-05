"""Crash-safe delivery journal, never a replacement for the shared business store."""
import json
import sqlite3
import threading
from pathlib import Path


class Ledger:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS work (id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)')
        self.db.commit()

    def save(self, key, kind, body):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO work VALUES (?,?,?)',
                            (key, kind, json.dumps(body, ensure_ascii=False, allow_nan=False)))

    def get(self, key):
        with self.lock:
            row = self.db.execute('SELECT body FROM work WHERE id=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def all(self, kind):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM work WHERE kind=? ORDER BY rowid', (kind,))]

    def call(self, document, name, path, payload, client):
        """Persist the exact request before sending; retries retain IDs and timestamps."""
        calls = document.setdefault('calls', {})
        if name not in calls:
            calls[name] = {'path': path, 'payload': payload}
            self.save(document['id'], document['kind'], document)
        call = calls[name]
        if 'response' not in call:
            call['response'] = client.post(call['path'], call['payload'])
            self.save(document['id'], document['kind'], document)
        return call['response']
