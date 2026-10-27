"""Setup global de tests.

1. Apunta DATA_DIR a un tmp único POR sesión de pytest ANTES de cualquier import
   de `efdi.*` (los ZIP/PDF y `.auth_secret` de los tests no tocan ./data).

2. La base de la app es SQL Server: los tests corren contra una base de
   PRUEBA aparte, definida con TEST_APP_DB_HOST / TEST_APP_DB_PORT /
   TEST_APP_DB_NAME / TEST_APP_DB_USER / TEST_APP_DB_PASS en el entorno.
   Se copian sobre APP_DB_* (las variables de entorno ganan sobre el .env), así
   que el APP_DB_* real del .env nunca se usa. Por seguridad el nombre de la
   base de prueba DEBE terminar en "_test": cada test vacía sus tablas.
"""
import os
import tempfile

import pytest

# Se ejecuta cuando pytest carga este archivo (antes de coleccionar los tests).
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="efdi_pytest_")
os.environ.setdefault("DATA_DIR", _TMP_DATA_DIR)
os.environ.setdefault("USE_MOCK", "true")
os.environ.setdefault("AUTH_USER", "admin")
os.environ.setdefault("AUTH_PASSWORD", "Admin123!")

_FALTAN = [v for v in ("TEST_APP_DB_HOST", "TEST_APP_DB_NAME", "TEST_APP_DB_USER", "TEST_APP_DB_PASS")
           if not os.environ.get(v)]
if _FALTAN:
    pytest.exit(
        "Los tests necesitan una base SQL Server de PRUEBA. Defina en el entorno: "
        + ", ".join(_FALTAN) + " (y opcional TEST_APP_DB_PORT). El nombre debe terminar en '_test'.",
        returncode=4,
    )
if not os.environ["TEST_APP_DB_NAME"].lower().endswith("_test"):
    pytest.exit(
        f"TEST_APP_DB_NAME='{os.environ['TEST_APP_DB_NAME']}' no termina en '_test'. "
        "Los tests vacían las tablas: nunca deben apuntar a la base real.",
        returncode=4,
    )
for _v in ("HOST", "PORT", "NAME", "USER", "PASS"):
    if os.environ.get(f"TEST_APP_DB_{_v}"):
        os.environ[f"APP_DB_{_v}"] = os.environ[f"TEST_APP_DB_{_v}"]


@pytest.fixture(scope="session", autouse=True)
def _esquema_app() -> None:
    """Crea las tablas en la base de prueba una vez por sesión (idempotente)."""
    from efdi.infrastructure.db import db
    db.crear_esquema()


@pytest.fixture(autouse=True)
def _tablas_vacias(_esquema_app) -> None:
    """Cada test arranca con la base vacía."""
    from efdi.infrastructure.db import db
    with db.transaction() as conn:
        for tabla in ("lotes", "extracciones", "audit_log", "users"):
            conn.execute(f"DELETE FROM {tabla}")
