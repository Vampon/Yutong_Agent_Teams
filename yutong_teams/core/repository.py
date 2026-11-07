"""One canonical store: per-entity documents plus an immutable event ledger.

Documents are current coordination state, not a cache reconstructed from events.
An operation updates its documents and appends its facts in one SQLite transaction.
This follows CCCC's state-authority boundary without pretending all state is an
event-sourced aggregate. Runtime processes and UI snapshots are never authority.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading
from .contracts import now, uid


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.local = threading.local()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, group_id TEXT NOT NULL,
                body TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE INDEX IF NOT EXISTS records_group ON records(kind,group_id);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                group_id TEXT NOT NULL, kind TEXT NOT NULL, actor_id TEXT NOT NULL,
                time TEXT NOT NULL, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_group ON events(group_id,seq);
            CREATE TABLE IF NOT EXISTS dedupe (
                scope TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL,
                result TEXT NOT NULL, PRIMARY KEY(scope,key));
            CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT,'ledger is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT,'ledger is append-only'); END;
            PRAGMA user_version=2;
        """)

    @contextmanager
    def transaction(self):
        with self.lock:
            outer = not getattr(self.local, "depth", 0)
            if outer:
                self.db.execute("BEGIN IMMEDIATE")
            self.local.depth = getattr(self.local, "depth", 0) + 1
            try:
                yield self
                if outer:
                    self.db.execute("COMMIT")
            except BaseException:
                if outer:
                    self.db.execute("ROLLBACK")
                raise
            finally:
                self.local.depth -= 1

    def get(self, kind, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
            return json.loads(row[0]) if row else default

    def require(self, kind, key):
        value = self.get(kind, key)
        if value is None:
            raise ValueError("记录不存在：%s / %s" % (kind, key))
        return value

    def put(self, kind, value):
        if not getattr(self.local, "depth", 0):
            raise RuntimeError("State mutations require a transaction")
        self.db.execute("INSERT INTO records(kind,id,group_id,body) VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET group_id=excluded.group_id,body=excluded.body",
                        (kind, value["id"], value.get("group_id", ""), json.dumps(value, ensure_ascii=False)))
        return value

    def list(self, kind, group_id=None):
        with self.lock:
            if group_id is None:
                rows = self.db.execute("SELECT body FROM records WHERE kind=? ORDER BY rowid", (kind,))
            else:
                rows = self.db.execute("SELECT body FROM records WHERE kind=? AND group_id=? ORDER BY rowid", (kind, group_id))
            return [json.loads(row[0]) for row in rows]

    def ordered(self, kind, group_id=None):
        """Stable commit order for the UI, independent of wall-clock adjustments.

        Existing records retain their insertion position when UPSERT updates them.
        This also preserves legacy imports without rewriting their timestamps.
        """
        with self.lock:
            sql = "SELECT rowid,body FROM records WHERE kind=?"
            params = [kind]
            if group_id is not None:
                sql += " AND group_id=?"
                params.append(group_id)
            rows = self.db.execute(sql + " ORDER BY rowid", params)
            return [dict(json.loads(row[1]), order=row[0]) for row in rows]

    def emit(self, group_id, kind, actor_id, data):
        if not getattr(self.local, "depth", 0):
            raise RuntimeError("Ledger mutations require a transaction")
        item = dict(id=uid(), group_id=group_id, kind=kind, actor_id=actor_id, time=now(), data=data)
        cursor = self.db.execute("INSERT INTO events(id,group_id,kind,actor_id,time,data) VALUES(?,?,?,?,?,?)",
                                 (item["id"], group_id, kind, actor_id, item["time"], json.dumps(data, ensure_ascii=False)))
        item["seq"] = cursor.lastrowid
        return item

    def events(self, group_id, after=0, limit=100):
        with self.lock:
            rows = self.db.execute("SELECT seq,id,kind,actor_id,time,data FROM events WHERE group_id=? AND seq>? ORDER BY seq LIMIT ?",
                                   (group_id, int(after), min(500, max(1, int(limit)))))
            return [dict(seq=r[0], id=r[1], kind=r[2], actor_id=r[3], time=r[4], data=json.loads(r[5])) for r in rows]

    def revision(self):
        with self.lock:
            return self.db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]

    def recent(self, group_id, limit=60):
        with self.lock:
            rows = self.db.execute("SELECT seq,id,kind,actor_id,time,data FROM events WHERE group_id=? AND kind NOT IN ('run.progress','session.updated') ORDER BY seq DESC LIMIT ?",
                                   (group_id, min(200, max(1, int(limit)))))
            return [dict(seq=r[0], id=r[1], kind=r[2], actor_id=r[3], time=r[4], data=json.loads(r[5])) for r in rows]

    def idempotent(self, scope, key, fingerprint, operation):
        """Caller holds the transaction, including both side effects and dedupe."""
        from .contracts import Conflict
        if not key:
            return operation()
        if not isinstance(key, str) or len(key) > 160:
            raise ValueError("无效请求标识")
        row = self.db.execute("SELECT fingerprint,result FROM dedupe WHERE scope=? AND key=?", (scope, key)).fetchone()
        encoded = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True)
        if row:
            if row[0] != encoded:
                raise Conflict("同一请求标识不能用于不同内容")
            return json.loads(row[1])
        result = operation()
        self.db.execute("INSERT INTO dedupe VALUES(?,?,?,?)", (scope, key, encoded, json.dumps(result, ensure_ascii=False)))
        return result

    def close(self):
        with self.lock:
            self.db.close()
