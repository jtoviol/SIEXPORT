"""Endpoints REST para el módulo Vacunación.

A diferencia de los otros 4 módulos: NO hay consulta SQL. El operador sube un
.xlsx, el archivo se guarda en data/uploads/vacunacion/<uuid>.xlsx, y los jobs
de extracción leen del Excel filtrando por régimen.

Flujo:
1. POST /vacunacion/uploads  (multipart .xlsx)  →  upload_id + resumen
2. POST /vacunacion/extractions  (upload_id, regimenes)  →  1 o 2 jobs
3. GET .../{job_id}, .../lotes, .../download, etc. — igual a los otros módulos
"""
from __future__ import annotations

import math
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from efdi.api.schemas import (
    CrearVacunacionReq,
    ExtraccionResp,
    RenombrarJobReq,
    VacunacionUploadResp,
)
from efdi.config import settings
from efdi.domain.models import (
    EstadoExtraccion,
    Extraccion,
    ExtraccionTipo,
    Lote,
    ModoPdf,
    estado_label,
    safe_filename,
)
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository_vacunacion import get_vacunacion_repository
from efdi.services.extraction_vacunacion import ejecutar_extraccion_vacunacion

router = APIRouter(prefix="/vacunacion", tags=["vacunacion"])


# ─── Helpers ────────────────────────────────────────────────────────────────


def _uploads_dir() -> Path:
    """Directorio donde se guardan los .xlsx subidos."""
    d = settings.data_dir / "uploads" / "vacunacion"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _excel_path_for(upload_id: UUID) -> Path:
    return _uploads_dir() / f"{upload_id}.xlsx"


def _auto_tamano_lote(limite: int) -> int:
    """Misma curva que los otros módulos — coherencia operativa."""
    if limite <= 50:      return limite
    if limite <= 500:     return max(1, limite // 5)
    if limite <= 5_000:   return 500
    if limite <= 50_000:  return 1_000
    if limite <= 100_000: return 5_000
    if limite <= 400_000: return 8_000
    return 12_000


# ─── Upload ─────────────────────────────────────────────────────────────────


@router.post(
    "/uploads",
    response_model=VacunacionUploadResp,
    status_code=status.HTTP_201_CREATED,
    summary="Subir un .xlsx con datos de vacunación",
)
async def subir_excel_vacunacion(
    file: UploadFile = File(..., description="Archivo .xlsx exportado del sistema"),
) -> VacunacionUploadResp:
    """Recibe el .xlsx vía multipart, lo guarda en data/uploads/vacunacion/<uuid>.xlsx
    y devuelve un resumen (filas totales, distribución por régimen, afiliados únicos)."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Solo se acepta .xlsx (Excel moderno). Convertí si el archivo es .xls o .csv.",
        )

    upload_id = uuid4()
    dest = _excel_path_for(upload_id)
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        size = dest.stat().st_size

        repo = get_vacunacion_repository()
        resumen = repo.resumen(dest)
        return VacunacionUploadResp(
            upload_id=upload_id,
            filename=file.filename,
            size_bytes=size,
            total_filas=resumen["total_filas"],
            por_regimen=resumen["por_regimen"],
            afiliados_por_regimen=resumen["afiliados_por_regimen"],
        )
    except ValueError as e:
        # Falta de columnas requeridas u otro error de validación: borrar el archivo
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Error procesando el Excel: {e}") from e


@router.get(
    "/uploads/{upload_id}",
    response_model=VacunacionUploadResp,
    summary="Resumen de un upload existente",
)
async def obtener_upload_vacunacion(upload_id: UUID) -> VacunacionUploadResp:
    dest = _excel_path_for(upload_id)
    if not dest.exists():
        raise HTTPException(status_code=404, detail="Upload no encontrado")
    repo = get_vacunacion_repository()
    resumen = repo.resumen(dest)
    return VacunacionUploadResp(
        upload_id=upload_id,
        filename=dest.name,
        size_bytes=dest.stat().st_size,
        total_filas=resumen["total_filas"],
        por_regimen=resumen["por_regimen"],
        afiliados_por_regimen=resumen["afiliados_por_regimen"],
    )


@router.delete(
    "/uploads/{upload_id}",
    summary="Borrar un upload (libera disco)",
)
async def borrar_upload_vacunacion(upload_id: UUID) -> dict:
    dest = _excel_path_for(upload_id)
    if not dest.exists():
        raise HTTPException(status_code=404, detail="Upload no encontrado")
    dest.unlink()
    return {"upload_id": str(upload_id), "borrado": True}


# ─── Extracciones ───────────────────────────────────────────────────────────


@router.post(
    "/extractions",
    response_model=list[ExtraccionResp],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear 1 o 2 jobs (uno por régimen) sobre un upload",
)
async def crear_extraccion_vacunacion(
    req: CrearVacunacionReq,
    background: BackgroundTasks,
) -> list[ExtraccionResp]:
    """Crea 1 job por cada régimen en `req.regimenes` (uno o ambos). Cada job
    procesa el mismo Excel filtrando por su régimen."""
    excel_path = _excel_path_for(req.upload_id)
    if not excel_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Upload {req.upload_id} no existe. Subí primero el .xlsx.",
        )

    repo = get_vacunacion_repository()
    jobs: list[ExtraccionResp] = []
    for regimen in req.regimenes:
        total = repo.get_total(excel_path, regimen=regimen)
        if total <= 0:
            # No hay filas para este régimen — saltamos sin error duro
            continue
        tamano_lote = req.tamano_lote or _auto_tamano_lote(total)
        nombre_default = req.nombre or f"VACUNACION · {regimen}"
        hoy = date.today()
        job = Extraccion(
            id=uuid4(),
            # `desde`/`hasta` son obligatorios en el modelo Extraccion (ge=1 en limite),
            # pero no aplican a Vacunación. Usamos la fecha de hoy como placeholder
            # para no tocar el modelo común; el servicio NO los usa.
            desde=hoy,
            hasta=hoy,
            limite=total,
            tamano_lote=tamano_lote,
            tipo=ExtraccionTipo.VACUNACION,
            modo_pdf=ModoPdf.UNO_POR_ATENCION,
            nombre=nombre_default,
            regimen=regimen,
            excel_path=str(excel_path),
            creado_en=datetime.now(),
        )
        store.save(job)
        background.add_task(ejecutar_extraccion_vacunacion, job)
        jobs.append(ExtraccionResp(**job.model_dump()))

    if not jobs:
        raise HTTPException(
            status_code=400,
            detail="El Excel no tiene filas para los regímenes solicitados.",
        )
    return jobs


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

    import re
    from collections import defaultdict
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
