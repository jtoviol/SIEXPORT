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

    data_dir: Path = Field(default=Path("./data"))
    templates_dir: Path = Field(default=Path("./src/efdi/templates"))

    api_host: str = "0.0.0.0"
    api_port: int = 8765
    log_level: str = "INFO"

    # Paralelización de PDFs: 0 = desactivado (secuencial), N = workers fijos, -1 = auto
    pdf_workers: int = -1
    # Umbral mínimo de atenciones por lote para activar Pool (debajo de eso, secuencial)
    pdf_parallel_threshold: int = 100

    # Lotes en paralelo: cuántos lotes se procesan simultáneamente (1 = secuencial)
    lote_workers: int = 2

    # Autenticación básica
    auth_user: str = Field(default="admin")
    auth_password: str = Field(default="Admin123123")
    auth_secret: str = Field(default="")   # Si vacío, se genera al arrancar (sesiones no persisten al reiniciar)

    @property
    def db_dsn(self) -> str:
        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.db_host},{self.db_port};"
            f"DATABASE={self.db_name};"
            f"UID={self.db_user};PWD={self.db_password};"
            "TrustServerCertificate=yes;Encrypt=no;"
        )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
