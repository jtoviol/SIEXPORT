"""Endpoints REST para gestión de usuarios. Solo ADMIN."""
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from efdi.api.dependencies import require_admin
from efdi.api.schemas import ResetPasswordReq, UserCreateReq, UserPublic, UserUpdateReq
from efdi.domain.models import MODULOS_VALIDOS, Rol, User
from efdi.infrastructure.audit_log import write_audit
from efdi.infrastructure.user_store import users_store
from efdi.services.auth_service import hash_password, resetear_password

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


def _to_public(u: User) -> UserPublic:
    return UserPublic(
        id=u.id,
        username=u.username,
        nombre=u.nombre,
        email=u.email,
        rol=Rol(u.rol) if isinstance(u.rol, str) else u.rol,
        modulos=list(u.modulos),
        modulos_efectivos=u.modulos_efectivos(),
        activo=u.activo,
        creado_en=u.creado_en,
        actualizado_en=u.actualizado_en,
        ultimo_login_en=u.ultimo_login_en,
        creado_por=u.creado_por,
    )


def _validar_modulos(modulos: list[str]) -> list[str]:
    """Filtra a los módulos válidos. Útil para evitar acumular basura en DB."""
    return [m for m in (modulos or []) if m in MODULOS_VALIDOS]


@router.get("", response_model=list[UserPublic], summary="Listar todos los usuarios")
async def listar_usuarios() -> list[UserPublic]:
    return [_to_public(u) for u in users_store.list_all()]


@router.post(
    "",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario nuevo",
)
async def crear_usuario(
    req: UserCreateReq,
    admin: User = Depends(require_admin),
) -> UserPublic:
    if users_store.get_by_username(req.username) is not None:
        raise HTTPException(status_code=409, detail=f"Ya existe un usuario con username '{req.username}'")

    now = datetime.now()
    u = User(
        id=uuid4(),
        username=req.username,
        nombre=req.nombre,
        email=req.email,
        password_hash=hash_password(req.password),
        rol=req.rol,
        modulos=_validar_modulos(req.modulos),
        activo=req.activo,
        creado_en=now,
        actualizado_en=now,
        creado_por=admin.username,
    )
    users_store.save(u)
    write_audit(
        actor=admin.username, accion="user.create",
        target_type="user", target_id=str(u.id), target_label=u.username,
        detalle={"rol": str(req.rol), "modulos": list(u.modulos), "activo": u.activo},
    )
    return _to_public(u)


@router.get("/{user_id}", response_model=UserPublic, summary="Detalle de un usuario")
async def obtener_usuario(user_id: UUID) -> UserPublic:
    u = users_store.get(user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return _to_public(u)


@router.put("/{user_id}", response_model=UserPublic, summary="Actualizar un usuario")
async def actualizar_usuario(
    user_id: UUID,
    req: UserUpdateReq,
    admin: User = Depends(require_admin),
) -> UserPublic:
    u = users_store.get(user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Snapshot del estado previo para el audit detalle
    antes = {"rol": str(u.rol), "modulos": list(u.modulos), "activo": u.activo,
             "nombre": u.nombre, "email": u.email}

    if req.nombre is not None:
        u.nombre = req.nombre or None
    if req.email is not None:
        u.email = req.email or None
    if req.rol is not None:
        u.rol = req.rol
    if req.modulos is not None:
        u.modulos = _validar_modulos(req.modulos)
    if req.activo is not None:
        # Anti-self-lockout: si el admin se desactiva a sí mismo y es el único admin
        # activo en DB, lo bloqueamos para no quedar sin acceso.
        if not req.activo and u.id == admin.id:
            otros_admins = [
                x for x in users_store.list_all()
                if (x.rol == Rol.ADMIN.value or x.rol == Rol.ADMIN) and x.activo and x.id != u.id
            ]
            if not otros_admins:
                raise HTTPException(
                    status_code=409,
                    detail="No podés desactivarte: sos el único admin activo del sistema",
                )
        u.activo = req.activo
    u.actualizado_en = datetime.now()
    users_store.save(u)

    despues = {"rol": str(u.rol), "modulos": list(u.modulos), "activo": u.activo,
               "nombre": u.nombre, "email": u.email}
    cambios = {k: {"antes": antes[k], "despues": despues[k]}
               for k in antes if antes[k] != despues[k]}
    if cambios:
        write_audit(
            actor=admin.username, accion="user.update",
            target_type="user", target_id=str(u.id), target_label=u.username,
            detalle={"cambios": cambios},
        )
    return _to_public(u)


@router.delete("/{user_id}", summary="Eliminar un usuario")
async def borrar_usuario(
    user_id: UUID,
    admin: User = Depends(require_admin),
) -> dict:
    u = users_store.get(user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if u.id == admin.id:
        raise HTTPException(status_code=409, detail="No podés borrarte a vos mismo")
    rol = u.rol if isinstance(u.rol, str) else u.rol.value
    if rol == Rol.ADMIN.value:
        otros_admins = [
            x for x in users_store.list_all()
            if (x.rol == Rol.ADMIN.value or x.rol == Rol.ADMIN) and x.activo and x.id != u.id
        ]
        if not otros_admins:
            raise HTTPException(
                status_code=409,
                detail="No podés borrar al último admin activo del sistema",
            )
    users_store.delete(user_id)
    write_audit(
        actor=admin.username, accion="user.delete",
        target_type="user", target_id=str(u.id), target_label=u.username,
        detalle={"rol": str(u.rol), "modulos": list(u.modulos)},
    )
    return {"id": str(user_id), "borrado": True}


@router.post("/{user_id}/reset-password", summary="Resetear password de un usuario")
async def reset_password(
    user_id: UUID,
    req: ResetPasswordReq,
    admin: User = Depends(require_admin),
) -> dict:
    try:
        ok = resetear_password(user_id, req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u = users_store.get(user_id)
    write_audit(
        actor=admin.username, accion="user.reset_password",
        target_type="user", target_id=str(user_id),
        target_label=u.username if u else None,
    )
    return {"id": str(user_id), "password_reseteado": True}


@router.get("/_meta/modulos", summary="Lista de módulos válidos (para la UI)")
async def listar_modulos_validos() -> dict:
    """Útil para que el frontend pinte el grid de checkboxes de módulos."""
    return {"modulos": list(MODULOS_VALIDOS)}


@router.get("/_audit/log", summary="Audit log de eventos críticos (solo ADMIN)")
async def listar_audit_log(
    limit: int = 200,
    actor: str | None = None,
    target_id: str | None = None,
) -> dict:
    """Devuelve los últimos N eventos del audit log.

    Filtros opcionales: `actor` (username del que ejecutó la acción) y
    `target_id` (UUID del usuario afectado). Útil para responder
    'quién creó/borró/editó al usuario X' y para cumplimiento."""
    from efdi.infrastructure.audit_log import list_audit
    eventos = list_audit(limit=limit, actor=actor, target_id=target_id)
    return {"total": len(eventos), "eventos": eventos}
