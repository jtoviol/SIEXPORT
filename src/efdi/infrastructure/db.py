"""SQLite con schema versionado para persistir jobs y lotes."""
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from efdi.config import settings

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS extracciones (
    id TEXT PRIMARY KEY,
    desde TEXT NOT NULL,
    hasta TEXT NOT NULL,
    limite INTEGER NOT NULL,
    tamano_lote INTEGER NOT NULL DEFAULT 10000,
    total_lotes INTEGER NOT NULL DEFAULT 0,
    tipo TEXT NOT NULL DEFAULT 'demanda_inducida',
    modo_pdf TEXT NOT NULL,
    nombre TEXT,
    estado TEXT NOT NULL,
    total_atenciones INTEGER NOT NULL DEFAULT 0,
    total_afiliados INTEGER NOT NULL DEFAULT 0,
    total_pdfs INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL,
    completado_en TEXT,
    mensaje_error TEXT,
    zip_path TEXT
);

CREATE TABLE IF NOT EXISTS lotes (
    job_id TEXT NOT NULL,
    numero INTEGER NOT NULL,
    offset_inicio INTEGER NOT NULL,
    tamano INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pending',
    fase TEXT NOT NULL DEFAULT '',
    total_atenciones INTEGER NOT NULL DEFAULT 0,
    total_afiliados INTEGER NOT NULL DEFAULT 0,
    total_pdfs INTEGER NOT NULL DEFAULT 0,
    zip_path TEXT,
    iniciado_en TEXT,
    completado_en TEXT,
    mensaje_error TEXT,
    PRIMARY KEY (job_id, numero),
    FOREIGN KEY (job_id) REFERENCES extracciones(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_extracciones_creado ON extracciones(creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_lotes_estado ON lotes(estado);
CREATE INDEX IF NOT EXISTS idx_lotes_job ON lotes(job_id, numero);
"""


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.data_dir / "efdi.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_schema()

    def _migrate(self, conn: sqlite3.Connection, current_version: int) -> None:
        if current_version < 2:
            try:
                conn.execute("ALTER TABLE lotes ADD COLUMN fase TEXT NOT NULL DEFAULT ''")
            except Exception:
                pass
        if current_version < 3:
            try:
                conn.execute("ALTER TABLE extracciones ADD COLUMN tipo TEXT NOT NULL DEFAULT 'demanda_inducida'")
            except Exception:
                pass
        if current_version < 4:
            try:
                conn.execute("ALTER TABLE extracciones ADD COLUMN nombre TEXT")
            except Exception:
                pass

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            current_version = row["version"] if row else 0
            if current_version < SCHEMA_VERSION:
                conn.execute("BEGIN")
                self._migrate(conn, current_version)
                if row is None:
                    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
                else:
                    conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
                conn.execute("COMMIT")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Conexión nueva por contexto (sqlite3 no es thread-safe entre conexiones compartidas)."""
        conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Conexión con BEGIN..COMMIT explícito y lock de proceso para serializar writes."""
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise


db = Database()
