"""Tests críticos de autenticación, RBAC y gestión de usuarios.

Cubre los invariantes de seguridad del sistema multi-user (auth_service.py +
api/dependencies.py + routes_users.py + routes_me.py):
  - bootstrap del primer admin con creds del .env
  - bcrypt hash/verify roundtrip
  - login válido devuelve cookie HMAC
  - login con password incorrecta falla
  - GET /api/me con/sin auth
  - require_modulo bloquea acceso a módulos fuera de la lista del user
  - require_no_viewer bloquea POST si rol=viewer
  - require_admin bloquea endpoints de gestión a no-admins
  - admin no puede borrarse / desactivarse si es el último admin activo
  - cambio de password verifica la actual
  - reset password (admin) NO verifica la actual
  - audit log captura los eventos críticos
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from efdi.services.auth_service import (
    PASSWORD_MIN_LEN,
    bootstrap_admin_si_vacio,
    hash_password,
    verify_password,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """TestClient con DB SQLite aislada en tmp_path (cada test arranca limpio)."""
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_USER", "admin")
    monkeypatch.setenv("AUTH_PASSWORD", "Admin123!")

    # Forzar re-evaluación de settings y reimport de módulos que cachean db/_SECRET
    import importlib
    for modname in [
        "efdi.config", "efdi.infrastructure.db", "efdi.infrastructure.user_store",
        "efdi.infrastructure.audit_log", "efdi.services.auth_service",
        "efdi.api.dependencies", "efdi.api.routes_users", "efdi.api.routes_me",
        "efdi.api.routes", "efdi.api.routes_findrisc", "efdi.api.routes_caracterizacion",
        "efdi.main",
    ]:
        if modname in __import__("sys").modules:
            importlib.reload(__import__("sys").modules[modname])

    from efdi.main import app
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str) -> bool:
    """Hace login y conserva la cookie en el client. Devuelve True si 303."""
    r = client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    return r.status_code == 303 and "siexport_session" in r.cookies


def _crear_user(client: TestClient, username: str, password: str, rol: str,
                modulos: list[str], activo: bool = True) -> dict:
    """Crea un user vía POST /api/users (asume admin logueado)."""
    r = client.post("/api/users", json={
        "username": username, "password": password,
        "rol": rol, "modulos": modulos, "activo": activo,
    })
    assert r.status_code == 201, f"crear_user falló: {r.status_code} {r.text}"
    return r.json()


# ──────────────────────────────────────────────────────────────────────────────
# 1. Hashing / verify (unitarios — sin TestClient)
# ──────────────────────────────────────────────────────────────────────────────


def test_bcrypt_hash_verify_roundtrip():
    h = hash_password("MiPassword123")
    assert h != "MiPassword123"               # debe estar hasheada
    assert h.startswith("$2")                  # prefijo bcrypt
    assert verify_password("MiPassword123", h) is True
    assert verify_password("password_distinta", h) is False


def test_bcrypt_verify_falla_silenciosa_con_input_invalido():
    """verify_password nunca raise, siempre False ante errores."""
    assert verify_password("", "$2b$nada") is False
    assert verify_password("algo", "") is False
    assert verify_password("algo", "no-es-un-hash-bcrypt") is False


def test_password_truncada_a_72_bytes():
    """bcrypt acepta máx 72 bytes; el helper trunca silenciosamente."""
    p72 = "a" * 72
    p100 = "a" * 100
    h = hash_password(p72)
    assert verify_password(p100, h) is True   # 100 'a' truncado = 72 'a' → match


# ──────────────────────────────────────────────────────────────────────────────
# 2. Bootstrap del primer admin
# ──────────────────────────────────────────────────────────────────────────────


def test_bootstrap_crea_admin_si_tabla_vacia(client):
    """Al arrancar con tabla users vacía, el startup hook crea el admin."""
    # client ya hizo el bootstrap al arrancar la app
    assert _login(client, "admin", "Admin123!")
    r = client.get("/api/me")
    assert r.status_code == 200
    me = r.json()
    assert me["username"] == "admin"
    assert me["rol"] == "admin"
    # admin ve los 6 módulos automáticamente
    assert len(me["modulos_efectivos"]) >= 6


def test_bootstrap_no_re_crea_si_ya_hay_users(client):
    """Llamar bootstrap_admin_si_vacio una segunda vez devuelve None."""
    _login(client, "admin", "Admin123!")  # asegura bootstrap inicial
    assert bootstrap_admin_si_vacio() is None


# ──────────────────────────────────────────────────────────────────────────────
# 3. Login / autenticación
# ──────────────────────────────────────────────────────────────────────────────


def test_login_credenciales_validas_devuelve_cookie(client):
    assert _login(client, "admin", "Admin123!") is True


def test_login_password_incorrecta_falla(client):
    r = client.post(
        "/auth/login",
        data={"username": "admin", "password": "password_mala"},
        follow_redirects=False,
    )
    # Redirige a /auth/login?error=1
    assert r.status_code == 303
    assert "error=1" in r.headers.get("location", "")
    assert "siexport_session" not in r.cookies


def test_login_username_inexistente_falla(client):
    r = client.post(
        "/auth/login",
        data={"username": "no-existe", "password": "lo-que-sea"},
        follow_redirects=False,
    )
    assert "error=1" in r.headers.get("location", "")


def test_get_me_sin_auth_devuelve_401(client):
    r = client.get("/api/me", headers={"Accept": "application/json"})
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# 4. RBAC — permisos por módulo
# ──────────────────────────────────────────────────────────────────────────────


def test_user_sin_modulo_recibe_403(client):
    """maria es OPERADOR solo de findrisc → DI debe rechazar con 403."""
    _login(client, "admin", "Admin123!")
    _crear_user(client, "maria", "Maria12345", "operador", ["findrisc"])
    client.cookies.clear()
    assert _login(client, "maria", "Maria12345")

    # findrisc: permitido
    assert client.get("/findrisc/extractions").status_code == 200
    # DI: prohibido
    assert client.get("/extractions").status_code == 403
    # vacunación: prohibido
    assert client.get("/vacunacion/extractions").status_code == 403
    # caracterización: prohibido
    assert client.get("/caracterizacion-familiar/extractions").status_code == 403


def test_viewer_no_puede_modificar(client):
    """juan es VIEWER, solo puede leer; POST debe 403."""
    _login(client, "admin", "Admin123!")
    _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])
    client.cookies.clear()
    assert _login(client, "juan", "Juan12345")

    # GET permitido
    assert client.get("/findrisc/extractions").status_code == 200

    # POST denegado con mensaje claro
    r = client.post("/findrisc/extractions",
                    json={"desde": "2026-05-01", "hasta": "2026-05-31"})
    assert r.status_code == 403
    assert "viewer" in r.json()["detail"].lower()


def test_no_admin_no_puede_listar_users(client):
    _login(client, "admin", "Admin123!")
    _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])
    client.cookies.clear()
    assert _login(client, "juan", "Juan12345")

    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={
        "username": "x", "password": "Whatever1234", "rol": "viewer", "modulos": []
    }).status_code == 403


def test_admin_ve_todos_los_modulos(client):
    """Aunque modulos=[] en DB, ADMIN ve todos (regla de modulos_efectivos)."""
    _login(client, "admin", "Admin123!")
    r = client.get("/api/me").json()
    assert r["rol"] == "admin"
    assert "demanda-inducida" in r["modulos_efectivos"]
    assert "caracterizacion-familiar" in r["modulos_efectivos"]


# ──────────────────────────────────────────────────────────────────────────────
# 5. Anti self-lockout del último admin
# ──────────────────────────────────────────────────────────────────────────────


def test_ultimo_admin_no_se_desactiva(client):
    """Admin único no puede setear activo=false sobre sí mismo."""
    _login(client, "admin", "Admin123!")
    me = client.get("/api/me").json()
    r = client.put(f"/api/users/{me['id']}", json={"activo": False})
    assert r.status_code == 409
    assert "único admin" in r.json()["detail"].lower()


def test_ultimo_admin_no_se_borra(client):
    """Admin único no puede borrarse a sí mismo."""
    _login(client, "admin", "Admin123!")
    me = client.get("/api/me").json()
    r = client.delete(f"/api/users/{me['id']}")
    assert r.status_code == 409


def test_segundo_admin_si_se_puede_desactivar(client):
    """Con 2 admins activos, uno puede desactivarse — no se rompe nada."""
    _login(client, "admin", "Admin123!")
    otro = _crear_user(client, "admin2", "Admin2222!", "admin", [])
    # Desactivar el segundo (no es el que está logueado)
    r = client.put(f"/api/users/{otro['id']}", json={"activo": False})
    assert r.status_code == 200
    assert r.json()["activo"] is False


# ──────────────────────────────────────────────────────────────────────────────
# 6. Cambio de password
# ──────────────────────────────────────────────────────────────────────────────


def test_cambiar_password_propia_funciona(client):
    _login(client, "admin", "Admin123!")
    _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])
    client.cookies.clear()
    assert _login(client, "juan", "Juan12345")

    r = client.put("/api/me/password", json={
        "password_actual": "Juan12345",
        "password_nueva":  "Juan12345_NUEVA",
    })
    assert r.status_code == 200

    # Login con la nueva password funciona
    client.cookies.clear()
    assert _login(client, "juan", "Juan12345_NUEVA")
    # Login con la vieja YA NO funciona
    client.cookies.clear()
    assert not _login(client, "juan", "Juan12345")


def test_cambiar_password_con_actual_incorrecta_falla(client):
    _login(client, "admin", "Admin123!")
    _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])
    client.cookies.clear()
    _login(client, "juan", "Juan12345")

    r = client.put("/api/me/password", json={
        "password_actual": "password_incorrecta",
        "password_nueva":  "OtraNueva12345",
    })
    assert r.status_code == 401


def test_reset_password_admin_no_verifica_actual(client):
    """Admin puede resetear sin saber la password vieja."""
    _login(client, "admin", "Admin123!")
    juan = _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])

    r = client.post(f"/api/users/{juan['id']}/reset-password",
                    json={"password": "PasswordReseteada1"})
    assert r.status_code == 200

    # Juan se loguea con la nueva
    client.cookies.clear()
    assert _login(client, "juan", "PasswordReseteada1")


def test_password_demasiado_corta_se_rechaza(client):
    _login(client, "admin", "Admin123!")
    r = client.post("/api/users", json={
        "username": "test", "password": "abc",  # < 8 chars
        "rol": "viewer", "modulos": [],
    })
    assert r.status_code == 422   # validation error de Pydantic


# ──────────────────────────────────────────────────────────────────────────────
# 7. Audit log
# ──────────────────────────────────────────────────────────────────────────────


def test_audit_log_registra_creacion_de_user(client):
    _login(client, "admin", "Admin123!")
    juan = _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])

    r = client.get("/api/users/_audit/log")
    assert r.status_code == 200
    eventos = r.json()["eventos"]
    creacion = [e for e in eventos if e["accion"] == "user.create"
                and e["target_label"] == "juan"]
    assert len(creacion) == 1
    assert creacion[0]["actor_username"] == "admin"
    assert creacion[0]["detalle"]["rol"] == "Rol.VIEWER" or "viewer" in str(creacion[0]["detalle"]).lower()


def test_audit_log_registra_borrado(client):
    _login(client, "admin", "Admin123!")
    juan = _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])
    client.delete(f"/api/users/{juan['id']}")

    r = client.get("/api/users/_audit/log")
    eventos = r.json()["eventos"]
    deletes = [e for e in eventos if e["accion"] == "user.delete"]
    assert len(deletes) >= 1
    assert deletes[0]["target_label"] == "juan"


def test_audit_log_solo_admin(client):
    """Endpoint del audit log es admin-only."""
    _login(client, "admin", "Admin123!")
    _crear_user(client, "juan", "Juan12345", "viewer", ["findrisc"])
    client.cookies.clear()
    _login(client, "juan", "Juan12345")
    r = client.get("/api/users/_audit/log")
    assert r.status_code == 403
