"""Endpoints REST para el módulo Soporte Unificado.

Módulo transversal: NO tiene query ni generador propios. Orquesta los otros 8
módulos y reorganiza la salida por afiliado (una carpeta por documento, con un
PDF por módulo donde la persona tenga soportes).

Universo = factura ∪ raros (una persona sale si aparece en CUALQUIER módulo).
Régimen en corridas separadas. Vacunación entra por consulta SQL (régimen + fecha).
"""
from __future__ import annotations

import logging
import math
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from efdi.api._files_util import listar_arbol_anidado
from efdi.api.dependencies import current_user, require_modulo, require_no_viewer
from efdi.api.schemas import (
    CrearAjusteSoportesReq,
    CrearSoporteUnificadoReq,
    ExtraccionResp,
    RenombrarJobReq,
)
from efdi.config import settings
from efdi.domain.models import (
    EstadoExtraccion,
    Extraccion,
    ExtraccionTipo,
    Lote,
    ModoPdf,
    User,
    estado_label,
    safe_filename,
)
from efdi.infrastructure.job_store import store
from efdi.services.extraction_ajuste_soportes import ejecutar_ajuste_soportes
from efdi.services.extraction_soporte_unificado import (
    MODULO_LABEL,
    conteo_por_modulo,
    ejecutar_extraccion_soporte_unificado,
)

# Tipos que comparten almacenamiento/descarga (Ajuste de Soportes opera sobre
# los archivos que ya dejó un Soporte Unificado, en la misma carpeta de datos).
_TIPOS_MODULO = (ExtraccionTipo.SOPORTE_UNIFICADO, ExtraccionTipo.AJUSTE_SOPORTES)

router = APIRouter(
    prefix="/soporte-unificado",
    tags=["soporte-unificado"],
    dependencies=[Depends(require_modulo("soporte-unificado"))],
)

log = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _facturas_de(numero: str) -> list[str]:
    """Arma el par CAB{n}+FAB{n} desde el sufijo numérico (ya normalizado)."""
    return [f"CAB{numero}", f"FAB{numero}"]


def _default_tamano_lote() -> int:
    """Lote en unidad de AFILIADOS (no registros). 1000 personas por lote."""
    return 1000


def _get_job_del_modulo(job_id: UUID) -> Extraccion:
    """Busca un job de Soporte Unificado o de Ajuste de Soportes (comparten
    almacenamiento/descarga — ver `_TIPOS_MODULO`). 404 si no existe o es de
    otro módulo."""
    job = store.get(job_id)
    if job is None or job.tipo not in _TIPOS_MODULO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
    return job


# ─── Conteo previo (rápido, por módulo) ──────────────────────────────────────

@router.get(
    "/extractions/count",
    summary="Conteo previo rápido por módulo (soportes ≈ PDFs, sin deduplicar)",
)
async def contar_soporte_unificado(
    desde: date = Query(...),
    hasta: date = Query(...),
    numero_factura: str | None = Query(None, description="Sufijo numérico (ej '11502'). Backend arma CABn+FABn."),
    regimen: str | None = Query(None, description="SUBSIDIADO o CONTRIBUTIVO"),
) -> dict:
    if hasta < desde:
        raise HTTPException(status_code=400, detail="hasta debe ser >= desde")
    r: str | None = None
    if regimen:
        r = regimen.strip().upper()
        if r not in ("SUBSIDIADO", "CONTRIBUTIVO"):
            raise HTTPException(status_code=400, detail="regimen debe ser SUBSIDIADO o CONTRIBUTIVO")
    facturas: list[str] | None = None
    if numero_factura:
        n = numero_factura.strip().upper()
        if n.startswith("CAB") or n.startswith("FAB"):
            n = n[3:]
        if n:
            facturas = _facturas_de(n)

    conteo = await run_in_threadpool(conteo_por_modulo, desde, hasta, facturas=facturas, regimen=r)
    por_modulo = [
        {"modulo": mod_id, "label": MODULO_LABEL.get(mod_id, mod_id), "soportes": total}
        for mod_id, total in conteo.items()
        if total > 0
    ]
    total_soportes = sum(conteo.values())
    tamano = _default_tamano_lote()
    lotes = math.ceil(total_soportes / tamano) if total_soportes else 0
    # Campos estándar (total_en_db, limite_efectivo, …) para que el render genérico
    # del preview los entienda; `por_modulo`/`total_soportes` son el desglose extra.
    return {
        "total_en_db": total_soportes,
        "limite_efectivo": total_soportes,
        "tamano_lote": tamano,
        "lotes_estimados": lotes,
        "capeado": False,
        "total_soportes": total_soportes,
        "por_modulo": por_modulo,
        "nota": "El total es cota superior de personas distintas; el número exacto se sabe al correr.",
    }


# ─── Crear extracción ────────────────────────────────────────────────────────

@router.post(
    "/extractions",
    response_model=ExtraccionResp,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear extracción de Soporte Unificado",
    dependencies=[Depends(require_no_viewer)],
)
async def crear_extraccion_soporte_unificado(
    req: CrearSoporteUnificadoReq,
    background: BackgroundTasks,
    current: User = Depends(current_user),
) -> ExtraccionResp:
    facturas = _facturas_de(req.numero_factura) if req.numero_factura else None
    # `limite` = estimación de soportes (el orquestador no lo usa para cortar; procesa
    # todo el universo). Sirve para mostrarlo en la UI.
    conteo = await run_in_threadpool(conteo_por_modulo, req.desde, req.hasta, facturas=facturas, regimen=req.regimen)
    limite = max(1, sum(conteo.values()))

    sufijo_factura = f" · F{req.numero_factura}" if req.numero_factura else ""
    nombre = req.nombre or f"Soporte Unificado {req.desde}—{req.hasta} · {req.regimen}{sufijo_factura}"

    job = Extraccion(
        id=uuid4(),
        desde=req.desde,
        hasta=req.hasta,
        limite=limite,
        tamano_lote=req.tamano_lote or _default_tamano_lote(),
        tipo=ExtraccionTipo.SOPORTE_UNIFICADO,
        modo_pdf=ModoPdf.UNO_POR_ATENCION,
        nombre=nombre,
        regimen=req.regimen,
        facturas=facturas,
        creado_en=datetime.now(),
        created_by_username=current.username,
    )
    store.save(job)
    background.add_task(ejecutar_extraccion_soporte_unificado, job)
    return ExtraccionResp(**job.model_dump())


# ─── Ajuste de Soportes (fusión + renombrado HEV_<nit>_<factura>_<tipo><num>) ─

@router.post(
    "/extractions/{job_id}/ajuste-soportes",
    response_model=ExtraccionResp,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Fusionar y renombrar los PDFs de un Soporte Unificado ya completado",
    dependencies=[Depends(require_no_viewer)],
)
async def crear_ajuste_soportes(
    job_id: UUID,
    req: CrearAjusteSoportesReq,
    background: BackgroundTasks,
    current: User = Depends(current_user),
) -> ExtraccionResp:
    origen = store.get(job_id)
    if origen is None or origen.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
    if origen.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La extracción de origen está en estado '{estado_label(origen.estado)}' — "
                "debe estar completada antes de ajustar sus soportes"
            ),
        )

    job = Extraccion(
        id=uuid4(),
        desde=origen.desde,
        hasta=origen.hasta,
        limite=max(1, origen.total_afiliados),
        tamano_lote=origen.tamano_lote,
        tipo=ExtraccionTipo.AJUSTE_SOPORTES,
        modo_pdf=ModoPdf.UNO_POR_ATENCION,
        nombre=f"Ajuste de Soportes · {origen.regimen} · F{req.numero_factura}",
        regimen=origen.regimen,
        facturas=_facturas_de(req.numero_factura),
        origen_job_id=origen.id,
        creado_en=datetime.now(),
        created_by_username=current.username,
    )
    store.save(job)
    background.add_task(ejecutar_ajuste_soportes, job)
    return ExtraccionResp(**job.model_dump())


# ─── Listar / estado / lotes ─────────────────────────────────────────────────

@router.get("/extractions", response_model=list[ExtraccionResp], summary="Listar extracciones")
async def listar_extracciones_soporte_unificado() -> list[ExtraccionResp]:
    return [ExtraccionResp(**j.model_dump()) for j in store.list_by_tipos(list(_TIPOS_MODULO))]


@router.get("/extractions/{job_id}", response_model=ExtraccionResp, summary="Estado de una extracción")
async def obtener_extraccion_soporte_unificado(job_id: UUID) -> ExtraccionResp:
    job = _get_job_del_modulo(job_id)
    return ExtraccionResp(**job.model_dump())


@router.get("/extractions/{job_id}/lotes", response_model=list[Lote], summary="Listar lotes")
async def listar_lotes_soporte_unificado(job_id: UUID) -> list[Lote]:
    _get_job_del_modulo(job_id)
    return store.list_lotes(job_id)


@router.get("/extractions/{job_id}/lotes/{numero}", response_model=Lote, summary="Estado de un lote")
async def obtener_lote_soporte_unificado(job_id: UUID, numero: int) -> Lote:
    _get_job_del_modulo(job_id)
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    return lote


@router.get(
    "/extractions/{job_id}/lotes/{numero}/download",
    summary="Descargar ZIP de un lote",
    response_class=FileResponse,
)
async def descargar_lote_soporte_unificado(job_id: UUID, numero: int) -> FileResponse:
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    if lote.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Lote {numero} aún no descargable")
    if not lote.zip_path or not Path(lote.zip_path).exists():
        raise HTTPException(status_code=410, detail="ZIP no disponible")
    job = store.get(job_id)
    base = safe_filename(job.nombre if job else None, f"soporte_unificado_lote_{numero:03d}_{job_id}")
    if job and job.nombre:
        base = f"{base}_lote_{numero:03d}"
    return FileResponse(path=lote.zip_path, filename=f"{base}.zip", media_type="application/zip")


# ─── Renombrar / cancelar / eliminar ─────────────────────────────────────────

@router.patch(
    "/extractions/{job_id}/nombre",
    response_model=ExtraccionResp,
    summary="Renombrar una extracción",
    dependencies=[Depends(require_no_viewer)],
)
async def renombrar_extraccion_soporte_unificado(job_id: UUID, req: RenombrarJobReq) -> ExtraccionResp:
    _get_job_del_modulo(job_id)
    store.rename(job_id, req.nombre or None)
    job = store.get(job_id)
    return ExtraccionResp(**job.model_dump())


@router.post(
    "/extractions/{job_id}/cancel",
    summary="Cancelar extracción en curso",
    dependencies=[Depends(require_no_viewer)],
)
async def cancelar_extraccion_soporte_unificado(job_id: UUID) -> dict:
    job = _get_job_del_modulo(job_id)
    if job.estado not in (EstadoExtraccion.PENDING, EstadoExtraccion.RUNNING):
        raise HTTPException(
            status_code=409,
            detail=f"No se puede cancelar — la extracción está en estado '{estado_label(job.estado)}'",
        )
    job.estado = EstadoExtraccion.CANCELLED
    job.mensaje_error = "Cancelación solicitada por el usuario"
    store.save(job)
    return {"id": str(job_id), "cancelado": True}


@router.delete(
    "/extractions/{job_id}",
    summary="Eliminar extracción",
    dependencies=[Depends(require_no_viewer)],
)
async def eliminar_extraccion_soporte_unificado(job_id: UUID) -> dict:
    _get_job_del_modulo(job_id)
    job_dir = settings.data_dir / f"job_{job_id}"
    carpetas = 0
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
        carpetas = 1
    store.delete(job_id)
    return {"id": str(job_id), "borrado": True, "carpetas": carpetas}


# ─── Descargas (mega-zip + árbol + PDF individual) ───────────────────────────

@router.get(
    "/extractions/{job_id}/download",
    summary="Mega-ZIP con todos los lotes",
    response_class=FileResponse,
)
async def descargar_extraccion_soporte_unificado(job_id: UUID) -> FileResponse:
    job = _get_job_del_modulo(job_id)
    if job.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Extracción en estado '{estado_label(job.estado)}'")

    if not job.zip_path or not Path(job.zip_path).exists():
        lotes = store.list_lotes(job_id)
        zips_lotes = [Path(l.zip_path) for l in lotes if l.zip_path and Path(l.zip_path).exists()]
        if not zips_lotes:
            raise HTTPException(status_code=410, detail="No hay ZIPs disponibles")
        import zipfile as _zf
        mega_zip = settings.data_dir / f"extraccion_{job_id}.zip"
        with _zf.ZipFile(mega_zip, "w", _zf.ZIP_STORED) as out:
            for lz in zips_lotes:
                with _zf.ZipFile(lz) as inp:
                    for name in inp.namelist():
                        out.writestr(name, inp.read(name))  # aplanado: sin carpeta lote_NNN, los doc_key no se repiten entre lotes
        job.zip_path = str(mega_zip)
        store.save(job)

    return FileResponse(
        path=job.zip_path,
        filename=f"{safe_filename(job.nombre, f'soporte_unificado_{job_id}')}.zip",
        media_type="application/zip",
    )


@router.get("/extractions/{job_id}/files", summary="Árbol de archivos (carpeta por afiliado)")
async def listar_archivos_soporte_unificado(
    job_id: UUID,
    limit: int = Query(500, ge=1, le=5000, description="Máximo de carpetas (afiliados) a devolver"),
    offset: int = Query(0, ge=0),
) -> dict:
    job = _get_job_del_modulo(job_id)
    if job.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Extracción en estado '{estado_label(job.estado)}'")

    job_dir = settings.data_dir / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    def _build() -> dict:
        return listar_arbol_anidado(job_dir, job_id=str(job_id), limit=limit, offset=offset)

    return await run_in_threadpool(_build)


@router.get(
    "/extractions/{job_id}/files/{afiliado}/{filename}",
    summary="Descargar un PDF individual",
    response_class=FileResponse,
)
async def descargar_pdf_soporte_unificado(job_id: UUID, afiliado: str, filename: str) -> FileResponse:
    _get_job_del_modulo(job_id)

    job_dir = settings.data_dir.resolve() / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    candidates = [p for p in job_dir.rglob(filename) if p.parent.name == afiliado]
    if not candidates:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    file_path = candidates[0].resolve()
    if not file_path.is_relative_to(job_dir):
        raise HTTPException(status_code=400, detail="Ruta inválida")

    return FileResponse(path=file_path, filename=filename, media_type="application/pdf")
