"""Configuración global cargada desde .env."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (tres niveles arriba de este archivo: src/efdi/config.py → proyecto/)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    use_mock: bool = Field(default=True, description="Usar datos falsos en lugar de SQL Server")
    limite_registros: int = Field(default=25, ge=1, le=10000)

    db_host: str = "localhost"
    db_port: int = 1433
    db_name: str = "seragil"
    db_user: str = ""
    db_password: str = ""
    db_driver: str = "ODBC Driver 17 for SQL Server"

    # Segunda conexión: base sibacom (módulo Caracterización Familiar).
    # Vive en otro servidor con credenciales propias — ver .env (DB_*_SIBACOM).
    db_host_sibacom: str = "localhost"
    db_port_sibacom: int = 1433
    db_name_sibacom: str = "sibacom"
    db_user_sibacom: str = ""
    db_password_sibacom: str = ""

    # Tercera conexión: base propia de la aplicación (usuarios, extracciones,
    # lotes, audit_log). Reemplaza al SQLite data/efdi.db. Las tablas las crea
    # `python -m efdi.migrar` — ver infrastructure/db.py.
    app_db_host: str = ""
    app_db_port: int = 1433
    app_db_name: str = ""
    app_db_user: str = ""
    app_db_pass: str = ""

    data_dir: Path = Field(default=Path("./data"))
    templates_dir: Path = Field(default=Path("./src/efdi/templates"))

    api_host: str = "0.0.0.0"
    api_port: int = 8765
    log_level: str = "INFO"

    # Paralelización de PDFs: 0 = desactivado (secuencial), N = workers fijos, -1 = auto
    pdf_workers: int = -1
    # Umbral mínimo de atenciones por lote para activar Pool (debajo de eso, secuencial)
    pdf_parallel_threshold: int = 100

    # Lotes en paralelo: cuántos lotes se procesan simultáneamente (1 = secuencial).
    # NOTA: cuando lote_workers > 1, el pool interno de PDFs por lote se desactiva
    # (el paralelismo viene del nivel de lote). Para jobs grandes (~45k afiliados),
    # 4 lotes paralelos × ~12k filas/lote da mejor throughput que 2 × 6k.
    lote_workers: int = 4

    # Limpieza automática: borra extracciones TERMINALES (completada/fallida/
    # cancelada) más viejas que esto, una vez al día. 0 = desactivado (default).
    # Nunca toca jobs 'pending'/'running' sin importar su antigüedad.
    auto_cleanup_dias: int = Field(default=0, ge=0)

    # Autenticación básica. AUTH_USER/AUTH_PASSWORD solo crean el primer admin
    # si la tabla users está vacía (sin password no se crea ninguno).
    auth_user: str = Field(default="admin")
    auth_password: str = Field(default="")
    # Clave HMAC de las cookies. Si vacío, se genera y persiste en DATA_DIR/.auth_secret
    # (ver api/dependencies.py::_cargar_secreto). Nunca se deriva de la password.
    auth_secret: str = Field(default="")

    @property
    def db_dsn(self) -> str:
        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.db_host},{self.db_port};"
            f"DATABASE={self.db_name};"
            f"UID={self.db_user};PWD={self.db_password};"
            "TrustServerCertificate=yes;Encrypt=no;"
        )

    @property
    def db_dsn_sibacom(self) -> str:
        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.db_host_sibacom},{self.db_port_sibacom};"
            f"DATABASE={self.db_name_sibacom};"
            f"UID={self.db_user_sibacom};PWD={self.db_password_sibacom};"
            "TrustServerCertificate=yes;Encrypt=no;"
        )

    @property
    def app_db_dsn(self) -> str:
        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.app_db_host},{self.app_db_port};"
            f"DATABASE={self.app_db_name};"
            f"UID={self.app_db_user};PWD={self.app_db_pass};"
            "TrustServerCertificate=yes;Encrypt=no;"
        )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
