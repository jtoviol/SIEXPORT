"""Setup global de tests.

Apunta DATA_DIR a un tmp único POR sesión de pytest ANTES de cualquier import
de `efdi.*` — sino `efdi.infrastructure.db` intenta escribir en `./data/efdi.db`
que en WSL suele ser de root (creada por Docker) y falla con readonly.
"""
import os
import tempfile

# Se ejecuta cuando pytest carga este archivo (antes de coleccionar los tests).
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="efdi_pytest_")
os.environ.setdefault("DATA_DIR", _TMP_DATA_DIR)
os.environ.setdefault("USE_MOCK", "true")
os.environ.setdefault("AUTH_USER", "admin")
os.environ.setdefault("AUTH_PASSWORD", "Admin123!")
