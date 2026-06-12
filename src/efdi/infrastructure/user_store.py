"""UserStore — persistencia de usuarios y permisos en SQLite (WAL)."""
from datetime import datetime
from uuid import UUID

from efdi.domain.models import MODULOS_VALIDOS, Rol, User
from efdi.infrastructure.db import db


def _row_to_user(row) -> User:
    cols = row.keys()
    modulos_csv = row["modulos"] if "modulos" in cols else ""
    modulos = [m for m in (modulos_csv or "").split(",") if m.strip()]
    return User(
        id=UUID(row["id"]),
        username=row["username"],
        nombre=row["nombre"],
        email=row["email"],
        password_hash=row["password_hash"],
        rol=Rol(row["rol"]),
        modulos=modulos,
        activo=bool(row["activo"]),
        creado_en=datetime.fromisoformat(row["creado_en"]),
        actualizado_en=datetime.fromisoformat(row["actualizado_en"]) if row["actualizado_en"] else None,
        ultimo_login_en=datetime.fromisoformat(row["ultimo_login_en"]) if row["ultimo_login_en"] else None,
        creado_por=row["creado_por"],
    )


class UserStore:
    """Operaciones CRUD sobre la tabla `users`. Sin lógica de auth ni hashing."""

    def save(self, user: User) -> None:
        """Insert o update por id. No toca password_hash si viene vacío en update."""
        modulos_csv = ",".join(m for m in user.modulos if m in MODULOS_VALIDOS)
        rol_val = user.rol if isinstance(user.rol, str) else user.rol.value
        with db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE id = ?", (str(user.id),)
            ).fetchone()
            params = (
                str(user.id),
                user.username,
                user.nombre,
                user.email,
                user.password_hash,
                rol_val,
                modulos_csv,
                1 if user.activo else 0,
                user.creado_en.isoformat(),
                user.actualizado_en.isoformat() if user.actualizado_en else None,
                user.ultimo_login_en.isoformat() if user.ultimo_login_en else None,
                user.creado_por,
            )
            if existing:
                conn.execute(
                    """UPDATE users SET
                        username=?, nombre=?, email=?, password_hash=?,
                        rol=?, modulos=?, activo=?,
                        creado_en=?, actualizado_en=?, ultimo_login_en=?, creado_por=?
                       WHERE id=?""",
                    (params[1], params[2], params[3], params[4], params[5],
                     params[6], params[7], params[8], params[9], params[10],
                     params[11], params[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO users (
                        id, username, nombre, email, password_hash,
                        rol, modulos, activo,
                        creado_en, actualizado_en, ultimo_login_en, creado_por
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    params,
                )

    def get(self, user_id: UUID) -> User | None:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (str(user_id),)
            ).fetchone()
            return _row_to_user(row) if row else None

    def get_by_username(self, username: str) -> User | None:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username.strip(),)
            ).fetchone()
            return _row_to_user(row) if row else None

    def list_all(self) -> list[User]:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY username COLLATE NOCASE"
            ).fetchall()
            return [_row_to_user(r) for r in rows]

    def count(self) -> int:
        with db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return int(row["n"]) if row else 0

    def delete(self, user_id: UUID) -> bool:
        with db.transaction() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (str(user_id),))
            return cur.rowcount > 0

    def update_last_login(self, user_id: UUID, ts: datetime) -> None:
        with db.transaction() as conn:
            conn.execute(
                "UPDATE users SET ultimo_login_en = ? WHERE id = ?",
                (ts.isoformat(), str(user_id)),
            )

    def update_password(self, user_id: UUID, password_hash: str) -> None:
        with db.transaction() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, actualizado_en = ? WHERE id = ?",
                (password_hash, datetime.now().isoformat(), str(user_id)),
            )


users_store = UserStore()
