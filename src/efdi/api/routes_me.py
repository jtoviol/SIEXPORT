"""Endpoints de perfil propio: cualquier usuario logueado puede usarlos."""
from fastapi import APIRouter, Depends, HTTPException

from efdi.api.dependencies import current_user
from efdi.api.schemas import CambiarPasswordReq, UserPublic
from efdi.domain.models import Rol, User
from efdi.infrastructure.audit_log import write_audit
from efdi.services.auth_service import cambiar_password

router = APIRouter(prefix="/api/me", tags=["me"])


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


@router.get("", response_model=UserPublic, summary="Mi perfil")
async def mi_perfil(user: User = Depends(current_user)) -> UserPublic:
    return _to_public(user)


@router.put("/password", summary="Cambiar mi password")
async def cambiar_mi_password(
    req: CambiarPasswordReq,
    user: User = Depends(current_user),
) -> dict:
    if req.password_actual == req.password_nueva:
        raise HTTPException(status_code=400, detail="La password nueva debe ser distinta de la actual")
    try:
        ok = cambiar_password(user.id, req.password_actual, req.password_nueva)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=401, detail="Password actual incorrecta")
    write_audit(
        actor=user.username, accion="me.change_password",
        target_type="user", target_id=str(user.id), target_label=user.username,
    )
    return {"actualizada": True}
