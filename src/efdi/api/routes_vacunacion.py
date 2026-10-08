"""Endpoints REST para el módulo Vacunación.

Consulta SQL Server (AVS_REGISTRO_SERAGIL + AVS_PROGRAMA_ASOCIADO_DEMIND
filtrado por códigos de programa de vacunación) — filtro por fecha + régimen,
sin factura. Mismo patrón que Educación Grupal/Gestión Captación.

Antes este módulo requería subir un .xlsx porque no había query conectada;
ese flujo (uploads, CrearVacunacionReq, VacunacionUploadResp) ya no existe.
"""
from __future__ import annotations

import logging
import math
import re
import shutil
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, APIRouter, BackgroundTasks, HTTPException, Query, status
from efdi.api.dependencies import current_user, require_modulo, require_no_viewer
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from efdi.api.schemas import CrearExtraccionReq, ExtraccionResp, RenombrarJobReq
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
from efdi.infrastructure.errors import RepositorioNoDisponibleError
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository_vacunacion import get_vacunacion_repository
from efdi.services.extraction_vacunacion import ejecutar_extraccion_vacunacion

router = APIRouter(prefix="/vacunacion", tags=["vacunacion"], dependencies=[Depends(require_modulo("vacunacion"))])

log = logging.getLogger(__name__)


def _auto_tamano_lote(limite: int) -> int:
    if limite <= 50:      return limite
    if limite <= 500:     return max(1, limite // 5)
    if limite <= 5_000:   return 500
    if limite <= 50_000:  return 1_000
    if limite <= 100_000: return 5_000
    if limite <= 400_000: return 8_000
    return 12_000


@router.get(
    "/extractions/count",
    summary="Conteo previo de registros de Vacunación para un rango de fechas",
)
async def contar_registros_vacunacion(
    desde: date = Query(...),
    hasta: date = Query(...),
    regimen: str | None = Query(None, description="SUBSIDIADO o CONTRIBUTIVO"),
) -> dict:
    if hasta < desde:
        raise HTTPException(status_code=400, detail="hasta debe ser >= desde")
    if regimen:
        r = regimen.strip().upper()
        if r not in ("SUBSIDIADO", "CONTRIBUTIVO"):
            raise HTTPException(status_code=400, detail="regimen debe ser SUBSIDIADO o CONTRIBUTIVO")
        regimen = r
    repo = get_vacunacion_repository()
    try:
        total = await run_in_threadpool(repo.get_total, desde, hasta, regimen=regimen)
    except RepositorioNoDisponibleError as e:
        raise HTTPException(
            status_code=503,
            detail="No se pudo conectar a la base de datos. Verifica la conexión/VPN e intenta de nuevo.",
        ) from e
    if total <= 0:
        return {"total_en_db": 0, "limite_efectivo": 0, "tamano_lote": 0, "lotes_estimados": 0, "capeado": False}
    limite_efectivo = total
    tamano = _auto_tamano_lote(limite_efectivo)
    lotes = math.ceil(limite_efectivo / tamano)
    return {
        "total_en_db": total,
        "limite_efectivo": limite_efectivo,
        "tamano_lote": tamano,
        "lotes_estimados": lotes,
        "capeado": False,
    }


@router.post(
    "/extractions",
    response_model=ExtraccionResp,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear extracción de PDFs de Vacunación",
    dependencies=[Depends(require_no_viewer)],
)
async def crear_extraccion_vacunacion(
    req: CrearExtraccionReq,
    background: BackgroundTasks,
    current: User = Depends(current_user),
) -> ExtraccionResp:
    regimen: str | None = None
    if req.regimen:
        r = req.regimen.strip().upper()
        if r not in ("SUBSIDIADO", "CONTRIBUTIVO"):
            raise HTTPException(status_code=400, detail="regimen debe ser SUBSIDIADO o CONTRIBUTIVO")
        regimen = r

    limite = req.limite
    if limite is None:
        repo = get_vacunacion_repository()
        try:
            total = await run_in_threadpool(repo.get_total, req.desde, req.hasta, regimen=regimen)
        except RepositorioNoDisponibleError as e:
            raise HTTPException(
                status_code=503,
                detail="No se pudo conectar a la base de datos. Verifica la conexión/VPN e intenta de nuevo.",
            ) from e
        if total <= 0:
            raise HTTPException(
                status_code=400,
                detail="No se encontraron registros de Vacunación para el rango indicado.",
            )
        limite = total

    tamano_lote = req.tamano_lote or _auto_tamano_lote(limite)

    nombre_base = f"Vacunación {req.desde}—{req.hasta}"
    if regimen:
        nombre_base += f" · {regimen}"

    job = Extraccion(
        id=uuid4(),
        desde=req.desde,
        hasta=req.hasta,
        limite=limite,
        tamano_lote=tamano_lote,
        tipo=ExtraccionTipo.VACUNACION,
        modo_pdf=ModoPdf.UNO_POR_ATENCION,
        nombre=nombre_base,
        regimen=regimen,
        creado_en=datetime.now(),
        created_by_username=current.username,
    )
    store.save(job)
    background.add_task(ejecutar_extraccion_vacunacion, job)
    return ExtraccionResp(**job.model_dump())


@router.get(
    "/extractions",
    response_model=list[ExtraccionResp],
    summary="Listar extracciones de Vacunación",
)
async def listar_extracciones_vacunacion() -> list[ExtraccionResp]:
    return [
        ExtraccionResp(**j.model_dump())
        for j in store.list_by_tipo(ExtraccionTipo.VACUNACION)
    ]


@router.get(
    "/extractions/{job_id}",
    response_model=ExtraccionResp,
    summary="Estado de una extracción Vacunación",
)
async def obtener_extraccion_vacunacion(job_id: UUID) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
    return ExtraccionResp(**job.model_dump())


@router.get(
    "/extractions/{job_id}/lotes",
    response_model=list[Lote],
    summary="Listar lotes de una extracción Vacunación",
)
async def listar_lotes_vacunacion(job_id: UUID) -> list[Lote]:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
    return store.list_lotes(job_id)


@router.get(
    "/extractions/{job_id}/lotes/{numero}",
    response_model=Lote,
    summary="Estado de un lote Vacunación",
)
async def obtener_lote_vacunacion(job_id: UUID, numero: int) -> Lote:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    return lote


@router.get(
    "/extractions/{job_id}/lotes/{numero}/download",
    summary="Descargar ZIP de un lote Vacunación",
    response_class=FileResponse,
)
async def descargar_lote_vacunacion(job_id: UUID, numero: int) -> FileResponse:
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    if lote.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Lote {numero} aún no descargable")
    if not lote.zip_path or not Path(lote.zip_path).exists():
        raise HTTPException(status_code=410, detail="ZIP no disponible")
    job = store.get(job_id)
    base = safe_filename(job.nombre if job else None, f"vacunacion_lote_{numero:03d}_{job_id}")
    if job and job.nombre:
        base = f"{base}_lote_{numero:03d}"
    return FileResponse(
        path=lote.zip_path,
        filename=f"{base}.zip",
        media_type="application/zip",
    )


@router.patch(
    "/extractions/{job_id}/nombre",
    response_model=ExtraccionResp,
    summary="Renombrar una extracción Vacunación",
    dependencies=[Depends(require_no_viewer)],
)
async def renombrar_extraccion_vacunacion(
    job_id: UUID, req: RenombrarJobReq,
) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
    store.rename(job_id, req.nombre or None)
    job = store.get(job_id)
    return ExtraccionResp(**job.model_dump())


@router.post(
    "/extractions/{job_id}/cancel",
    summary="Cancelar extracción Vacunación en curso",
    dependencies=[Depends(require_no_viewer)],
)
async def cancelar_extraccion_vacunacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
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
    summary="Eliminar extracción Vacunación",
    dependencies=[Depends(require_no_viewer)],
)
async def eliminar_extraccion_vacunacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
    job_dir = settings.data_dir / f"job_{job_id}"
    carpetas = 0
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
        carpetas = 1
    store.delete(job_id)
    return {"id": str(job_id), "borrado": True, "carpetas": carpetas}


@router.get(
    "/extractions/{job_id}/download",
    summary="Mega-ZIP con todos los lotes Vacunación",
    response_class=FileResponse,
)
async def descargar_extraccion_vacunacion(job_id: UUID) -> FileResponse:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
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
                        out.writestr(f"{lz.stem}/{name}", inp.read(name))
        job.zip_path = str(mega_zip)
        store.save(job)

    return FileResponse(
        path=job.zip_path,
        filename=f"{safe_filename(job.nombre, f'vacunacion_{job_id}')}.zip",
        media_type="application/zip",
    )


@router.get(
    "/extractions/{job_id}/files",
    summary="Árbol de archivos de una extracción Vacunación",
)
async def listar_archivos_vacunacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")
    if job.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Extracción en estado '{estado_label(job.estado)}'")

    job_dir = settings.data_dir / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    agrupado: dict[str, list[dict]] = defaultdict(list)
    for pdf in job_dir.rglob("*.pdf"):
        nombre = pdf.stem
        match = re.match(r"^([A-Z]{2})_(.+)$", nombre)
        if not match:
            continue
        tipo_doc = match.group(1)
        lote_dir = pdf.parent
        lote_name = lote_dir.name if lote_dir.name.startswith("lote_") else ""
        agrupado[tipo_doc].append({
            "name": pdf.name,
            "doc_key": nombre,
            "size": pdf.stat().st_size,
            "lote": lote_name,
        })

    folders = [
        {"name": tipo, "files": sorted(items, key=lambda x: x["doc_key"])}
        for tipo, items in sorted(agrupado.items())
    ]
    return {"job_id": str(job_id), "folders": folders, "total": sum(len(f["files"]) for f in folders)}


@router.get(
    "/extractions/{job_id}/files/{afiliado}/{filename}",
    summary="Descargar PDF individual Vacunación",
    response_class=FileResponse,
)
async def descargar_pdf_vacunacion(
    job_id: UUID, afiliado: str, filename: str,
) -> FileResponse:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.VACUNACION:
        raise HTTPException(status_code=404, detail="Extracción Vacunación no encontrada")

    job_dir = settings.data_dir.resolve() / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    candidates = list(job_dir.rglob(filename))
    if not candidates:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    file_path = candidates[0].resolve()
    if not file_path.is_relative_to(job_dir):
        raise HTTPException(status_code=400, detail="Ruta inválida")

    return FileResponse(path=file_path, filename=filename, media_type="application/pdf")
