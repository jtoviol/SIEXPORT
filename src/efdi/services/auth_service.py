"""Servicio de autenticación: hashing bcrypt, login, bootstrap del primer admin."""
import logging
from datetime import datetime
from uuid import uuid4

import bcrypt

from efdi.config import settings
from efdi.domain.models import MODULOS_VALIDOS, Rol, User
from efdi.infrastructure.user_store import users_store

log = logging.getLogger(__name__)


# bcrypt limita a 72 bytes (resto se ignora). Documentamos y validamos.
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 72


def hash_password(plain: str) -> str:
    """Hashea con bcrypt + salt. Trunca a 72 bytes (límite bcrypt)."""
    if not plain:
        raise ValueError("password vacío")
    data = plain.encode("utf-8")[:PASSWORD_MAX_LEN]
    return bcrypt.hashpw(data, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Compara password en plano contra hash bcrypt. False ante cualquier error."""
    if not plain or not hashed:
        return False
    try:
        data = plain.encode("utf-8")[:PASSWORD_MAX_LEN]
        return bcrypt.checkpw(data, hashed.encode("utf-8"))
    except Exception:
        log.exception("verify_password failed")
        return False


def autenticar(username: str, password: str) -> User | None:
    """Login: devuelve el user si username + password son válidos y está activo.
    Actualiza ultimo_login_en en caso exitoso."""
    if not username or not password:
        return None
    u = users_store.get_by_username(username.strip())
    if u is None or not u.activo:
        return None
    if not verify_password(password, u.password_hash):
        return None
    users_store.update_last_login(u.id, datetime.now())
    return u


def bootstrap_admin_si_vacio() -> User | None:
    """Si la tabla users está vacía, crea un admin con las credenciales del .env.

    - Username = settings.auth_user
    - Password = settings.auth_password (hasheada con bcrypt)
    - Rol      = ADMIN, todos los módulos
    Una vez creado, el .env queda como referencia pero ya no es la fuente de auth.

    Devuelve el user creado, o None si ya había usuarios.
    """
    if users_store.count() > 0:
        return None

    if not settings.auth_user or not settings.auth_password:
        log.warning("bootstrap_admin: AUTH_USER/AUTH_PASSWORD vacíos en .env, no se crea admin")
        return None

    now = datetime.now()
    admin = User(
        id=uuid4(),
        username=settings.auth_user.strip(),
        nombre="Administrador",
        email=None,
        password_hash=hash_password(settings.auth_password),
        rol=Rol.ADMIN,
        modulos=list(MODULOS_VALIDOS),   # admin ve todos, pero lo dejamos explícito
        activo=True,
        creado_en=now,
        actualizado_en=now,
        creado_por="system:bootstrap",
    )
    users_store.save(admin)
    log.info("bootstrap_admin: creado admin '%s' (tabla users estaba vacía)", admin.username)
    return admin


def cambiar_password(user_id, password_actual: str, password_nueva: str) -> bool:
    """Cambia la password del usuario verificando la actual. False si la actual no coincide."""
    if len(password_nueva or "") < PASSWORD_MIN_LEN:
        raise ValueError(f"La password nueva debe tener al menos {PASSWORD_MIN_LEN} caracteres")
    u = users_store.get(user_id)
    if u is None or not u.activo:
        return False
    if not verify_password(password_actual, u.password_hash):
        return False
    users_store.update_password(user_id, hash_password(password_nueva))
    return True


def resetear_password(user_id, password_nueva: str) -> bool:
    """Reset por admin: setea password sin verificar la anterior."""
    if len(password_nueva or "") < PASSWORD_MIN_LEN:
        raise ValueError(f"La password debe tener al menos {PASSWORD_MIN_LEN} caracteres")
    u = users_store.get(user_id)
    if u is None:
        return False
    users_store.update_password(user_id, hash_password(password_nueva))
    return True
