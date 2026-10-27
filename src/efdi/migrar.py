"""Migración de la base SQL Server de la aplicación (APP_DB_* en el .env).

Uso:
    python -m efdi.migrar
    # en Docker:
    docker compose run --rm siedfaser uv run python -m efdi.migrar

Qué hace:
  1. Crea las tablas e índices que falten (users, audit_log, extracciones,
     lotes, schema_version) y registra la versión del esquema. Se puede correr
     las veces que sea: lo que ya existe no se toca y no borra datos.
  2. Si la tabla users quedó vacía, ofrece crear el primer administrador
     pidiendo la contraseña por pantalla (no queda guardada en el .env).
     Sin terminal interactiva, avisa que se usarán AUTH_USER/AUTH_PASSWORD.
"""
from __future__ import annotations

import getpass
import sys

from efdi.config import settings
from efdi.infrastructure.db import EsquemaNoListoError, db
from efdi.infrastructure.user_store import users_store
from efdi.services.auth_service import PASSWORD_MIN_LEN, crear_admin


def _pedir_admin() -> None:
    print("\nLa tabla de usuarios está vacía. Se va a crear el primer administrador.")
    username = input(f"Usuario [{settings.auth_user or 'admin'}]: ").strip() or settings.auth_user or "admin"
    while True:
        p1 = getpass.getpass(f"Contraseña (mínimo {PASSWORD_MIN_LEN} caracteres): ")
        p2 = getpass.getpass("Repita la contraseña: ")
        if p1 != p2:
            print("Las contraseñas no coinciden, intente de nuevo.")
            continue
        try:
            crear_admin(username, p1, creado_por="system:migrar")
        except ValueError as e:
            print(e)
            continue
        print(f"Administrador '{username}' creado.")
        return


def main() -> int:
    print(f"Base de la app: {settings.app_db_name} en {settings.app_db_host}:{settings.app_db_port}")
    try:
        version = db.crear_esquema()
        db.verificar_esquema()
    except EsquemaNoListoError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 — se muestra tal cual para diagnosticar permisos/red
        print(f"ERROR al crear las tablas: {e}", file=sys.stderr)
        return 1
    print(f"Esquema listo (versión {version}).")

    if users_store.count() == 0:
        if sys.stdin.isatty():
            _pedir_admin()
        elif settings.auth_password:
            print("Sin usuarios: al arrancar, la app creará el admin con AUTH_USER/AUTH_PASSWORD del .env.")
        else:
            print(
                "AVISO: no hay usuarios y no hay AUTH_PASSWORD en el .env, así que nadie podrá entrar.\n"
                "Vuelva a correr este comando en una terminal interactiva (docker compose run sí lo es)\n"
                "para crear el administrador."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
