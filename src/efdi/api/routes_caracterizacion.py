"""Endpoints REST para el módulo Caracterización Familiar (base sibacom).

Filtro único: rango de fecha_reg. Sin factura, sin régimen.
"""
import math
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, APIRouter, BackgroundTasks, HTTPException, Query, status
from efdi.api.dependencies import require_modulo, require_no_viewer
from fastapi.responses import FileResponse

from efdi.api.schemas import CrearExtraccionReq, ExtraccionResp, RenombrarJobReq
from efdi.config import settings
from efdi.domain.models import EstadoExtraccion, Extraccion, ExtraccionTipo, Lote, ModoPdf, estado_label, safe_filename
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository_caracterizacion import get_caracterizacion_repository
from efdi.services.extraction_caracterizacion import ejecutar_extraccion_caracterizacion

router = APIRouter(prefix="/caracterizacion-familiar", tags=["caracterizacion-familiar"], dependencies=[Depends(require_modulo("caracterizacion-familiar"))])


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
    summary="Conteo previo de FAMILIAS de Caracterización Familiar (unidad de PDF y de paginación)",
)
async def contar_registros_caracterizacion(
    desde: date = Query(...),
    hasta: date = Query(...),
    regimen: str | None = Query(
        None,
        description=(
            "Si viene 'SUBSIDIADO' o 'CONTRIBUTIVO', cuenta solo familias cuyo "
            "JEFE DE FAMILIA tenga ese régimen (regla de negocio del módulo)."
        ),
    ),
) -> dict:
    if hasta < desde:
        raise HTTPException(status_code=400, detail="hasta debe ser >= desde")
    reg = (regimen or "").strip().upper() or None
    if reg is not None and reg not in ("SUBSIDIADO", "CONTRIBUTIVO"):
        raise HTTPException(status_code=400, detail="regimen debe ser SUBSIDIADO o CONTRIBUTIVO")
    repo = get_caracterizacion_repository()
    total = repo.get_total(desde, hasta, regimen=reg)
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
    summary="Crear extracción de PDFs de Caracterización Familiar",
    dependencies=[Depends(require_no_viewer)],
)
async def crear_extraccion_caracterizacion(
    req: CrearExtraccionReq,
    background: BackgroundTasks,
) -> ExtraccionResp:
    """Crea una extracción de Caracterización Familiar.

    Acepta `regimen` ('SUBSIDIADO' o 'CONTRIBUTIVO') para filtrar familias
    según el régimen del JEFE DE FAMILIA. Sin régimen, trae todas las familias.
    Este módulo NO usa factura.

    `limite` y `tamano_lote` se expresan en FAMILIAS: el repositorio pagina
    con DENSE_RANK y nunca parte una familia entre lotes.
    """
    reg = (req.regimen or "").strip().upper() or None
    if reg is not None and reg not in ("SUBSIDIADO", "CONTRIBUTIVO"):
        raise HTTPException(status_code=400, detail="regimen debe ser SUBSIDIADO o CONTRIBUTIVO")

    limite = req.limite
    if limite is None:
        repo = get_caracterizacion_repository()
        total = repo.get_total(req.desde, req.hasta, regimen=reg)
        if total <= 0:
            sufijo = f" con régimen {reg}" if reg else ""
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No se encontraron familias para el rango indicado{sufijo}. "
                    "Verifica el conteo previo y la conexión a la base de datos sibacom."
                ),
            )
        limite = total

    tamano_lote = req.tamano_lote or _auto_tamano_lote(limite)

    nombre_default = (
        f"CARACT. FAM. {req.desde}—{req.hasta} · {reg}"
        if reg else
        f"CARACT. FAM. {req.desde}—{req.hasta}"
    )

    job = Extraccion(
        id=uuid4(),
        desde=req.desde,
        hasta=req.hasta,
        limite=limite,
        tamano_lote=tamano_lote,
        tipo=ExtraccionTipo.CARACTERIZACION_FAMILIAR,
        modo_pdf=ModoPdf.UNO_POR_ATENCION,
        nombre=nombre_default,
        regimen=reg,
        creado_en=datetime.now(),
    )
    store.save(job)
    background.add_task(ejecutar_extraccion_caracterizacion, job)
    return ExtraccionResp(**job.model_dump())


@router.get(
    "/extractions",
    response_model=list[ExtraccionResp],
    summary="Listar extracciones de Caracterización Familiar",
)
async def listar_extracciones_caracterizacion() -> list[ExtraccionResp]:
    return [
        ExtraccionResp(**j.model_dump())
        for j in store.list_by_tipo(ExtraccionTipo.CARACTERIZACION_FAMILIAR)
    ]


@router.get(
    "/extractions/{job_id}",
    response_model=ExtraccionResp,
    summary="Estado de una extracción de Caracterización Familiar",
)
async def obtener_extraccion_caracterizacion(job_id: UUID) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    return ExtraccionResp(**job.model_dump())


@router.get(
    "/extractions/{job_id}/lotes",
    response_model=list[Lote],
    summary="Listar lotes de una extracción de Caracterización Familiar",
)
async def listar_lotes_caracterizacion(job_id: UUID) -> list[Lote]:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    return store.list_lotes(job_id)


@router.get(
    "/extractions/{job_id}/lotes/{numero}",
    response_model=Lote,
    summary="Estado de un lote",
)
async def obtener_lote_caracterizacion(job_id: UUID, numero: int) -> Lote:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    return lote


@router.get(
    "/extractions/{job_id}/lotes/{numero}/download",
    summary="Descargar ZIP de un lote",
    response_class=FileResponse,
)
async def descargar_lote_caracterizacion(job_id: UUID, numero: int) -> FileResponse:
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    if lote.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Lote {numero} aún no descargable")
    if not lote.zip_path or not Path(lote.zip_path).exists():
        raise HTTPException(status_code=410, detail="ZIP no disponible")
    job = store.get(job_id)
    base = safe_filename(job.nombre if job else None, f"caracterizacion_lote_{numero:03d}_{job_id}")
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
    summary="Renombrar una extracción",
    dependencies=[Depends(require_no_viewer)],
)
async def renombrar_extraccion_caracterizacion(job_id: UUID, req: RenombrarJobReq) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    store.rename(job_id, req.nombre or None)
    job = store.get(job_id)
    return ExtraccionResp(**job.model_dump())


@router.post(
    "/extractions/{job_id}/cancel",
    summary="Cancelar extracción en curso",
    dependencies=[Depends(require_no_viewer)],
)
async def cancelar_extraccion_caracterizacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    if job.estado not in (EstadoExtraccion.PENDING, EstadoExtraccion.RUNNING):
        raise HTTPException(status_code=409, detail=f"No se puede cancelar — la extracción está en estado '{estado_label(job.estado)}'")
    job.estado = EstadoExtraccion.CANCELLED
    job.mensaje_error = "Cancelación solicitada por el usuario"
    store.save(job)
    return {"id": str(job_id), "cancelado": True}


@router.delete(
    "/extractions/{job_id}",
    summary="Eliminar extracción",
    dependencies=[Depends(require_no_viewer)],
)
async def eliminar_extraccion_caracterizacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    job_dir = settings.data_dir / f"job_{job_id}"
    carpetas = 0
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
        carpetas = 1
    store.delete(job_id)
    return {"id": str(job_id), "borrado": True, "carpetas": carpetas}


@router.get(
    "/extractions/{job_id}/download",
    summary="Mega-ZIP con todos los lotes",
    response_class=FileResponse,
)
async def descargar_extraccion_caracterizacion(job_id: UUID) -> FileResponse:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
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
        filename=f"{safe_filename(job.nombre, f'caracterizacion_{job_id}')}.zip",
        media_type="application/zip",
    )


@router.get(
    "/extractions/{job_id}/files",
    summary="Árbol de archivos de una extracción",
)
async def listar_archivos_caracterizacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    if job.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Extracción en estado '{estado_label(job.estado)}'")

    job_dir = settings.data_dir / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    from collections import defaultdict
    # Carpetas FAM_<clave> — se agrupan por lote para que el árbol sea navegable.
    agrupado: dict[str, list[dict]] = defaultdict(list)
    for pdf in job_dir.rglob("*.pdf"):
        lote_dir = pdf.parent.parent
        lote_name = lote_dir.name if lote_dir.name.startswith("lote_") else "lote_001"
        agrupado[lote_name].append({
            "name": pdf.name,
            "doc_key": pdf.stem,
            "size": pdf.stat().st_size,
            "lote": lote_name,
        })

    folders = [
        {"name": lote, "files": sorted(items, key=lambda x: x["doc_key"])}
        for lote, items in sorted(agrupado.items())
    ]
    return {"job_id": str(job_id), "folders": folders, "total": sum(len(f["files"]) for f in folders)}


@router.get(
    "/extractions/{job_id}/files/{familia}/{filename}",
    summary="Descargar PDF individual",
    response_class=FileResponse,
)
async def descargar_pdf_caracterizacion(job_id: UUID, familia: str, filename: str) -> FileResponse:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.CARACTERIZACION_FAMILIAR:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")

    job_dir = settings.data_dir.resolve() / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    # Estructura conocida: lote_NNN/FAM_<clave>/FAM_<clave>.pdf — el árbol /files
    # expone `familia` = carpeta del lote y `filename` = FAM_<clave>.pdf.
    # Path directo (sin rglob) para no recorrer todo el job por cada descarga.
    file_path = (job_dir / familia / Path(filename).stem / filename).resolve()
    if not file_path.is_relative_to(job_dir):
        raise HTTPException(status_code=400, detail="Ruta inválida")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    return FileResponse(path=file_path, filename=filename, media_type="application/pdf")
