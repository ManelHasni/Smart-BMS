"""
history_store.py -- Historique long terme (multi-session) pour le Smart BMS.

Contrairement a l'historique de session (RAM, efface a la fermeture), ce module
persiste des points SOH/cycles dans un fichier SQLite local, pour pouvoir :
  - reprendre le SOH la ou il en etait a la derniere fermeture (au lieu de repartir
    a 100% a chaque lancement -- un pack reel ne "rajeunit" pas en redemarrant l'app)
  - tracer une courbe de vieillissement sur plusieurs jours/semaines de sessions
  - purger automatiquement les points trop anciens (retention configurable)

Utilise sqlite3 (bibliotheque standard Python, aucune dependance supplementaire).
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path


class HistoryStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.session_id = str(uuid.uuid4())[:8]
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS soh_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tick INTEGER NOT NULL,
                    cycles INTEGER NOT NULL,
                    soh REAL NOT NULL,
                    soc REAL NOT NULL,
                    scenario TEXT NOT NULL
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON soh_history(timestamp)")

    def insert_point(self, tick, cycles, soh, soc, scenario):
        with self._connect() as con:
            con.execute(
                "INSERT INTO soh_history (timestamp, session_id, tick, cycles, soh, soc, scenario) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), self.session_id,
                 tick, cycles, soh, soc, scenario),
            )

    def get_last_soh(self):
        """Renvoie le dernier SOH enregistre (toutes sessions confondues), ou None
        si l'historique est vide (premier lancement)."""
        with self._connect() as con:
            row = con.execute(
                "SELECT soh FROM soh_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def get_last_cycles(self):
        with self._connect() as con:
            row = con.execute(
                "SELECT cycles FROM soh_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def get_history(self, limit=2000):
        """Renvoie les points (timestamp, soh, cycles, session_id) les plus recents,
        du plus ancien au plus recent (ordre chronologique, pret a tracer)."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT timestamp, soh, cycles, session_id FROM soh_history "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return list(reversed(rows))

    def count_sessions(self):
        with self._connect() as con:
            row = con.execute("SELECT COUNT(DISTINCT session_id) FROM soh_history").fetchone()
        return row[0] if row else 0

    def purge_older_than(self, days: int):
        """Supprime les points plus vieux que `days` jours. Renvoie le nombre de lignes supprimees."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.execute("DELETE FROM soh_history WHERE timestamp < ?", (cutoff,))
            return cur.rowcount

    def clear_all(self):
        with self._connect() as con:
            con.execute("DELETE FROM soh_history")
