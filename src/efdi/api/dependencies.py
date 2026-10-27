"""FastAPI dependencies para autenticación y autorización (RBAC).

El token de sesión sigue siendo cookie HMAC firmada (mismo formato que antes).
Lo nuevo es que el username se valida contra la tabla `users` en DB en cada
request, y se chequea rol + módulo permitido para el endpoint.
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status

from efdi.config import settings
from efdi.domain.models import MODULOS_VALIDOS, Rol, User
from efdi.infrastructure.user_store import users_store

log = logging.getLogger(__name__)


_SECRET_FILE_NAME = ".auth_secret"


def _cargar_secreto() -> bytes:
    """Clave HMAC de las cookies de sesión.

    Antes se derivaba de AUTH_USER + AUTH_PASSWORD + AUTH_SECRET; sin esas
    variables en el .env quedaban los defaults del código (públicos en el repo)
    y cualquiera podía firmar una cookie válida para cualquier usuario.

    Ahora: si AUTH_SECRET viene en el .env se usa ese. Si no, se genera uno
    aleatorio la primera vez y se guarda en DATA_DIR/.auth_secret, que es
    volumen persistente en Docker — las sesiones sobreviven a reinicios y el
    secreto nunca depende de la contraseña. O_EXCL evita que dos workers de
    uvicorn generen secretos distintos al arrancar a la vez."""
    if settings.auth_secret:
        if len(settings.auth_secret) < 32:
            log.warning("auth: AUTH_SECRET tiene menos de 32 caracteres; use uno aleatorio más largo")
        return hashlib.sha256(f"siexport-v2:{settings.auth_secret}".encode()).digest()

    path = settings.data_dir / _SECRET_FILE_NAME
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Otro worker pudo crearlo hace milisegundos y aún no termina de escribir.
        for _ in range(50):
            contenido = path.read_text(encoding="ascii").strip()
            if contenido:
                return bytes.fromhex(contenido)
            time.sleep(0.1)
        raise RuntimeError(f"auth: {path} existe pero está vacío; bórrelo y reinicie") from None
    secreto = secrets.token_bytes(32)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(secreto.hex())
    log.info("auth: AUTH_SECRET no definido; se generó un secreto aleatorio en %s", path)
    return secreto


_SECRET = _cargar_secreto()
_SESSION_TTL = timedelta(hours=8)
COOKIE_NAME = "siexport_session"


def make_token(username: str) -> str:
    """Crea token firmado con expiración. Mismo formato que el legacy."""
    expiry = int((datetime.now() + _SESSION_TTL).timestamp())
    payload = f"{username}|{expiry}"
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def verify_token(token: str) -> str | None:
    """Devuelve el username si el token es válido y no expiró. None si no."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        *parts, sig = decoded.split("|")
        payload = "|".join(parts)
        expected = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected):
            return None
        username, expiry_str = parts
        if datetime.now().timestamp() > float(expiry_str):
            return None
        return username
    except Exception:
        return None


def _unauthorized(detail: str = "No autenticado") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Cookie"},
    )


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# ─── Dependencies ──────────────────────────────────────────────────────────


def current_user(request: Request) -> User:
    """Resuelve el usuario logueado desde la cookie. 401 si no hay sesión."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthorized()
    username = verify_token(token)
    if username is None:
        raise _unauthorized("Sesión inválida o expirada")
    user = users_store.get_by_username(username)
    if user is None or not user.activo:
        raise _unauthorized("Usuario no encontrado o inactivo")
    return user


def require_admin(request: Request) -> User:
    """Solo ADMIN puede acceder. 403 si no."""
    user = current_user(request)
    rol = user.rol if isinstance(user.rol, str) else user.rol.value
    if rol != Rol.ADMIN.value:
        raise _forbidden("Requiere rol ADMIN")
    return user


def require_no_viewer(request: Request) -> User:
    """ADMIN u OPERADOR. Bloquea a los VIEWER (que son read-only)."""
    user = current_user(request)
    if not user.puede_modificar():
        raise _forbidden("Tu rol no permite modificar (eres viewer)")
    return user


def require_modulo(modulo: str):
    """Factory: dependency que verifica que el user tenga acceso a `modulo`.

    Pensado para usarse como `dependencies=[Depends(require_modulo("X"))]` en
    el APIRouter de cada módulo. Aplica a todos los endpoints del router.
    """
    if modulo not in MODULOS_VALIDOS:
        raise ValueError(f"Módulo desconocido: {modulo!r}")

    def _dep(request: Request) -> User:
        user = current_user(request)
        if modulo not in user.modulos_efectivos():
            raise _forbidden(f"No tienes acceso al módulo '{modulo}'")
        return user

    return _dep
