"""Endpoints REST para el módulo Gestión Captación Afiliados."""
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
from efdi.infrastructure.repository_captacion import get_captacion_repository
from efdi.services.extraction_captacion import ejecutar_extraccion_captacion

router = APIRouter(prefix="/gestion-captacion", tags=["gestion-captacion"], dependencies=[Depends(require_modulo("gestion-captacion"))])


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
    summary="Conteo previo de registros de Captación para un rango de fechas",
)
async def contar_registros_captacion(
    desde: date = Query(...),
    hasta: date = Query(...),
    numero_factura: str | None = Query(
        None,
        description="Sufijo del código de régimen (ej '11502'). Backend arma CABn+FABn.",
    ),
) -> dict:
    if hasta < desde:
        raise HTTPException(status_code=400, detail="hasta debe ser >= desde")
    facturas: list[str] | None = None
    if numero_factura:
        n = numero_factura.strip().upper()
        if n.startswith("CAB") or n.startswith("FAB"):
            n = n[3:]
        if not n:
            raise HTTPException(status_code=400, detail="numero_factura no puede ser vacío")
        facturas = [f"CAB{n}", f"FAB{n}"]
    repo = get_captacion_repository()
    total = repo.get_total(desde, hasta, facturas=facturas)
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
    summary="Crear extracción de PDFs de Gestión Captación",
    dependencies=[Depends(require_no_viewer)],
)
async def crear_extraccion_captacion(
    req: CrearExtraccionReq,
    background: BackgroundTasks,
) -> ExtraccionResp:
    # Mismo patrón que DI/FINDRISC: CAB+N / FAB+N es el código de régimen.
    facturas: list[str] | None = None
    nombre_default: str | None = None
    if req.numero_factura is not None:
        facturas = [f"CAB{req.numero_factura}", f"FAB{req.numero_factura}"]
        nombre_default = f"CAPTACION {req.desde}—{req.hasta} · {req.regimen}"

    limite = req.limite
    if limite is None:
        repo = get_captacion_repository()
        total = repo.get_total(req.desde, req.hasta, facturas=facturas)
        if total <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se encontraron registros de Captación para el rango/código indicados. "
                    "Verifica el conteo previo y la conexión a la base de datos."
                ),
            )
        limite = total

    tamano_lote = req.tamano_lote or _auto_tamano_lote(limite)

    job = Extraccion(
        id=uuid4(),
        desde=req.desde,
        hasta=req.hasta,
        limite=limite,
        tamano_lote=tamano_lote,
        tipo=ExtraccionTipo.GESTION_CAPTACION,
        modo_pdf=ModoPdf.UNO_POR_ATENCION,
        nombre=nombre_default,
        regimen=req.regimen,
        facturas=facturas,
        creado_en=datetime.now(),
    )
    store.save(job)
    background.add_task(ejecutar_extraccion_captacion, job)
    return ExtraccionResp(**job.model_dump())


@router.get(
    "/extractions",
    response_model=list[ExtraccionResp],
    summary="Listar extracciones de Gestión Captación",
)
async def listar_extracciones_captacion() -> list[ExtraccionResp]:
    return [ExtraccionResp(**j.model_dump()) for j in store.list_by_tipo(ExtraccionTipo.GESTION_CAPTACION)]


@router.get(
    "/extractions/{job_id}",
    response_model=ExtraccionResp,
    summary="Estado de una extracción de Captación",
)
async def obtener_extraccion_captacion(job_id: UUID) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
    return ExtraccionResp(**job.model_dump())


@router.get(
    "/extractions/{job_id}/lotes",
    response_model=list[Lote],
    summary="Listar lotes de una extracción de Captación",
)
async def listar_lotes_captacion(job_id: UUID) -> list[Lote]:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
    return store.list_lotes(job_id)


@router.get(
    "/extractions/{job_id}/lotes/{numero}",
    response_model=Lote,
    summary="Estado de un lote de Captación",
)
async def obtener_lote_captacion(job_id: UUID, numero: int) -> Lote:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    return lote


@router.get(
    "/extractions/{job_id}/lotes/{numero}/download",
    summary="Descargar ZIP de un lote de Captación",
    response_class=FileResponse,
)
async def descargar_lote_captacion(job_id: UUID, numero: int) -> FileResponse:
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    if lote.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Lote {numero} aún no descargable")
    if not lote.zip_path or not Path(lote.zip_path).exists():
        raise HTTPException(status_code=410, detail="ZIP no disponible")
    job = store.get(job_id)
    base = safe_filename(job.nombre if job else None, f"captacion_lote_{numero:03d}_{job_id}")
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
    summary="Renombrar una extracción de Captación",
    dependencies=[Depends(require_no_viewer)],
)
async def renombrar_extraccion_captacion(job_id: UUID, req: RenombrarJobReq) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
    store.rename(job_id, req.nombre or None)
    job = store.get(job_id)
    return ExtraccionResp(**job.model_dump())


@router.post(
    "/extractions/{job_id}/cancel",
    summary="Cancelar extracción de Captación en curso",
    dependencies=[Depends(require_no_viewer)],
)
async def cancelar_extraccion_captacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
    if job.estado not in (EstadoExtraccion.PENDING, EstadoExtraccion.RUNNING):
        raise HTTPException(status_code=409, detail=f"No se puede cancelar — la extracción está en estado '{estado_label(job.estado)}'")
    job.estado = EstadoExtraccion.CANCELLED
    job.mensaje_error = "Cancelación solicitada por el usuario"
    store.save(job)
    return {"id": str(job_id), "cancelado": True}


@router.delete(
    "/extractions/{job_id}",
    summary="Eliminar extracción de Captación",
    dependencies=[Depends(require_no_viewer)],
)
async def eliminar_extraccion_captacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
    job_dir = settings.data_dir / f"job_{job_id}"
    carpetas = 0
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
        carpetas = 1
    store.delete(job_id)
    return {"id": str(job_id), "borrado": True, "carpetas": carpetas}


@router.get(
    "/extractions/{job_id}/download",
    summary="Mega-ZIP con todos los lotes de Captación",
    response_class=FileResponse,
)
async def descargar_extraccion_captacion(job_id: UUID) -> FileResponse:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
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
        filename=f"{safe_filename(job.nombre, f'captacion_{job_id}')}.zip",
        media_type="application/zip",
    )


@router.get(
    "/extractions/{job_id}/files",
    summary="Árbol de archivos de una extracción de Captación",
)
async def listar_archivos_captacion(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")
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
    summary="Descargar PDF individual de Captación",
    response_class=FileResponse,
)
async def descargar_pdf_captacion(job_id: UUID, afiliado: str, filename: str) -> FileResponse:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.GESTION_CAPTACION:
        raise HTTPException(status_code=404, detail="Extracción de Captación no encontrada")

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
