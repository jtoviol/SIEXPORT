"""Base propia de la aplicación en SQL Server (usuarios, extracciones, lotes, audit_log).

Reemplaza al SQLite `data/efdi.db`. Conexión: variables `APP_DB_*` del .env.

Las tablas NO se crean al arrancar la app: las crea el comando de migración
`python -m efdi.migrar` (idempotente, ver `crear_esquema`). Al arrancar,
`verificar_esquema` comprueba que existan y que la versión coincida; si no,
la app no levanta y el log dice qué comando correr.

`connect()` / `transaction()` devuelven un adaptador con la misma interfaz que
usaban los stores con sqlite3: `conn.execute(sql, params)` → cursor con
`fetchone()` / `fetchall()` (filas como dict, `row["columna"]`) y `rowcount`.
Los placeholders siguen siendo `?` (pyodbc usa el mismo estilo).
"""
import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from threading import Lock
from typing import Any

from efdi.config import settings

log = logging.getLogger(__name__)

# Versión del esquema en SQL Server. Empieza en 1: es una base nueva, no hereda
# la numeración v2..v8 del SQLite anterior.
SCHEMA_VERSION = 1

TABLAS = ("schema_version", "users", "audit_log", "extracciones", "lotes")

# Una sentencia por elemento (pyodbc no entiende el separador GO). Cada una
# está protegida con IF ... IS NULL / IF NOT EXISTS para poder correr la
# migración varias veces sin error.
_DDL: list[str] = [
    """IF OBJECT_ID(N'dbo.schema_version', N'U') IS NULL
    CREATE TABLE dbo.schema_version (version INT NOT NULL PRIMARY KEY)""",

    """IF OBJECT_ID(N'dbo.users', N'U') IS NULL
    CREATE TABLE dbo.users (
        id              NVARCHAR(36)  NOT NULL PRIMARY KEY,
        username        NVARCHAR(150) NOT NULL,
        nombre          NVARCHAR(200) NULL,
        email           NVARCHAR(254) NULL,
        password_hash   NVARCHAR(200) NOT NULL,
        rol             NVARCHAR(20)  NOT NULL CONSTRAINT df_users_rol DEFAULT 'viewer',
        modulos         NVARCHAR(1000) NOT NULL CONSTRAINT df_users_modulos DEFAULT '',
        activo          BIT           NOT NULL CONSTRAINT df_users_activo DEFAULT 1,
        creado_en       DATETIME2     NOT NULL,
        actualizado_en  DATETIME2     NULL,
        ultimo_login_en DATETIME2     NULL,
        creado_por      NVARCHAR(150) NULL,
        CONSTRAINT uq_users_username UNIQUE (username)
    )""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_users_activo')
    CREATE INDEX idx_users_activo ON dbo.users(activo)""",

    # actor y target se guardan como USERNAMES históricos (no FK): sobreviven
    # al borrado del user. `detalle` es JSON con cambios o metadata.
    """IF OBJECT_ID(N'dbo.audit_log', N'U') IS NULL
    CREATE TABLE dbo.audit_log (
        id             BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ts             DATETIME2     NOT NULL,
        actor_username NVARCHAR(150) NOT NULL,
        accion         NVARCHAR(60)  NOT NULL,
        target_type    NVARCHAR(40)  NULL,
        target_id      NVARCHAR(100) NULL,
        target_label   NVARCHAR(300) NULL,
        detalle        NVARCHAR(MAX) NULL
    )""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_audit_ts')
    CREATE INDEX idx_audit_ts ON dbo.audit_log(ts DESC)""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_audit_actor')
    CREATE INDEX idx_audit_actor ON dbo.audit_log(actor_username)""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_audit_target')
    CREATE INDEX idx_audit_target ON dbo.audit_log(target_type, target_id)""",

    """IF OBJECT_ID(N'dbo.extracciones', N'U') IS NULL
    CREATE TABLE dbo.extracciones (
        id                  NVARCHAR(36)  NOT NULL PRIMARY KEY,
        desde               DATE          NOT NULL,
        hasta               DATE          NOT NULL,
        limite              INT           NOT NULL,
        tamano_lote         INT           NOT NULL CONSTRAINT df_ext_tamano DEFAULT 10000,
        total_lotes         INT           NOT NULL CONSTRAINT df_ext_total_lotes DEFAULT 0,
        tipo                NVARCHAR(40)  NOT NULL CONSTRAINT df_ext_tipo DEFAULT 'demanda_inducida',
        modo_pdf            NVARCHAR(40)  NOT NULL,
        nombre              NVARCHAR(300) NULL,
        regimen             NVARCHAR(30)  NULL,
        facturas            NVARCHAR(1000) NULL,
        estado              NVARCHAR(20)  NOT NULL,
        total_atenciones    INT           NOT NULL CONSTRAINT df_ext_atenciones DEFAULT 0,
        total_afiliados     INT           NOT NULL CONSTRAINT df_ext_afiliados DEFAULT 0,
        total_pdfs          INT           NOT NULL CONSTRAINT df_ext_pdfs DEFAULT 0,
        creado_en           DATETIME2     NOT NULL,
        completado_en       DATETIME2     NULL,
        mensaje_error       NVARCHAR(MAX) NULL,
        zip_path            NVARCHAR(500) NULL,
        created_by_username NVARCHAR(150) NULL,
        origen_job_id       NVARCHAR(36)  NULL,
        resumen_json        NVARCHAR(MAX) NULL
    )""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_extracciones_creado')
    CREATE INDEX idx_extracciones_creado ON dbo.extracciones(creado_en DESC)""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_extracciones_tipo')
    CREATE INDEX idx_extracciones_tipo ON dbo.extracciones(tipo, creado_en DESC)""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_extracciones_creador')
    CREATE INDEX idx_extracciones_creador ON dbo.extracciones(created_by_username)""",

    """IF OBJECT_ID(N'dbo.lotes', N'U') IS NULL
    CREATE TABLE dbo.lotes (
        job_id           NVARCHAR(36)  NOT NULL,
        numero           INT           NOT NULL,
        offset_inicio    INT           NOT NULL,
        tamano           INT           NOT NULL,
        estado           NVARCHAR(20)  NOT NULL CONSTRAINT df_lotes_estado DEFAULT 'pending',
        fase             NVARCHAR(300) NOT NULL CONSTRAINT df_lotes_fase DEFAULT '',
        total_atenciones INT           NOT NULL CONSTRAINT df_lotes_atenciones DEFAULT 0,
        total_afiliados  INT           NOT NULL CONSTRAINT df_lotes_afiliados DEFAULT 0,
        total_pdfs       INT           NOT NULL CONSTRAINT df_lotes_pdfs DEFAULT 0,
        zip_path         NVARCHAR(500) NULL,
        iniciado_en      DATETIME2     NULL,
        completado_en    DATETIME2     NULL,
        mensaje_error    NVARCHAR(MAX) NULL,
        CONSTRAINT pk_lotes PRIMARY KEY (job_id, numero),
        CONSTRAINT fk_lotes_extracciones FOREIGN KEY (job_id)
            REFERENCES dbo.extracciones(id) ON DELETE CASCADE
    )""",
    """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_lotes_estado')
    CREATE INDEX idx_lotes_estado ON dbo.lotes(estado)""",
]


class EsquemaNoListoError(RuntimeError):
    """La base de la app no tiene las tablas (o la versión) que el código espera."""


class _Cursor:
    """Envuelve el cursor de pyodbc para devolver filas como dict."""

    def __init__(self, cur: Any) -> None:
        self._cur = cur

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def _fila(self, r: Any) -> dict[str, Any]:
        cols = [c[0] for c in self._cur.description]
        return dict(zip(cols, r))

    def fetchone(self) -> dict[str, Any] | None:
        r = self._cur.fetchone()
        return self._fila(r) if r is not None else None

    def fetchall(self) -> list[dict[str, Any]]:
        return [self._fila(r) for r in self._cur.fetchall()]


class _Conexion:
    """Interfaz mínima compatible con lo que los stores usaban de sqlite3."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _Cursor:
        cur = self._conn.cursor()
        if params:
            cur.execute(sql, list(params))
        else:
            cur.execute(sql)
        return _Cursor(cur)


class Database:
    def __init__(self) -> None:
        # Serializa las escrituras dentro del proceso (mismo comportamiento que
        # con SQLite). Entre procesos, los SELECT ... WITH (UPDLOCK) de los
        # stores evitan pisadas.
        self._lock = Lock()

    def _abrir(self, autocommit: bool) -> Any:
        if not settings.app_db_host or not settings.app_db_name:
            raise EsquemaNoListoError(
                "Faltan APP_DB_HOST / APP_DB_NAME en el .env: la app necesita su base SQL Server."
            )
        try:
            import pyodbc
        except ImportError as e:
            raise EsquemaNoListoError(
                "pyodbc no está instalado. Instale el extra: uv sync --extra sqlserver"
            ) from e
        conn = pyodbc.connect(settings.app_db_dsn, timeout=15, autocommit=autocommit)
        conn.timeout = 30  # timeout de ejecución de cada sentencia
        return conn

    @contextmanager
    def connect(self) -> Iterator[_Conexion]:
        """Conexión en autocommit para lecturas y escrituras de una sola sentencia."""
        conn = self._abrir(autocommit=True)
        try:
            yield _Conexion(conn)
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[_Conexion]:
        """Transacción explícita (COMMIT al salir, ROLLBACK si hay excepción)
        con lock de proceso para serializar writes."""
        with self._lock:
            conn = self._abrir(autocommit=False)
            try:
                yield _Conexion(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def crear_esquema(self) -> int:
        """Crea las tablas e índices que falten y registra la versión. Idempotente.
        Lo usa `python -m efdi.migrar`; la app nunca lo llama sola."""
        with self.transaction() as conn:
            for ddl in _DDL:
                conn.execute(ddl)
            row = conn.execute("SELECT MAX(version) AS v FROM dbo.schema_version").fetchone()
            actual = row["v"] if row and row["v"] is not None else 0
            if actual == 0:
                conn.execute("INSERT INTO dbo.schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            elif actual < SCHEMA_VERSION:
                conn.execute("UPDATE dbo.schema_version SET version = ?", (SCHEMA_VERSION,))
        return SCHEMA_VERSION

    def verificar_esquema(self) -> None:
        """Lanza EsquemaNoListoError con un mensaje accionable si la base no está lista."""
        try:
            with self.connect() as conn:
                faltan = [
                    t for t in TABLAS
                    if conn.execute("SELECT OBJECT_ID(?, N'U') AS oid", (f"dbo.{t}",)).fetchone()["oid"] is None
                ]
                if faltan:
                    raise EsquemaNoListoError(
                        f"Faltan tablas en la base {settings.app_db_name}: {', '.join(faltan)}. "
                        "Ejecute la migración: python -m efdi.migrar"
                    )
                row = conn.execute("SELECT MAX(version) AS v FROM dbo.schema_version").fetchone()
                version = row["v"] if row else None
        except EsquemaNoListoError:
            raise
        except Exception as e:
            raise EsquemaNoListoError(
                f"No se pudo conectar a la base de la app ({settings.app_db_name}): {e}"
            ) from e
        if version != SCHEMA_VERSION:
            raise EsquemaNoListoError(
                f"La base {settings.app_db_name} está en la versión {version} y el código espera "
                f"la {SCHEMA_VERSION}. Ejecute la migración: python -m efdi.migrar"
            )


db = Database()
