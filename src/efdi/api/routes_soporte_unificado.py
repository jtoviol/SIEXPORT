"""Endpoints REST para el módulo Soporte Unificado.

Módulo transversal: NO tiene query ni generador propios. Orquesta los otros 8
módulos y reorganiza la salida por afiliado (una carpeta por documento, con un
PDF por módulo donde la persona tenga soportes).

Universo = factura ∪ raros (una persona sale si aparece en CUALQUIER módulo).
Régimen en corridas separadas. Vacunación entra solo si se sube su Excel.
"""
from __future__ import annotations

import math
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from efdi.api.dependencies import current_user, require_modulo, require_no_viewer
from efdi.api.schemas import (
    CrearSoporteUnificadoReq,
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
    User,
    estado_label,
    safe_filename,
)
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository_vacunacion import get_vacunacion_repository
from efdi.services.extraction_soporte_unificado import (
    MODULO_LABEL,
    conteo_por_modulo,
    ejecutar_extraccion_soporte_unificado,
)

router = APIRouter(
    prefix="/soporte-unificado",
    tags=["soporte-unificado"],
    dependencies=[Depends(require_modulo("soporte-unificado"))],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _facturas_de(numero: str) -> list[str]:
    """Arma el par CAB{n}+FAB{n} desde el sufijo numérico (ya normalizado)."""
    return [f"CAB{numero}", f"FAB{numero}"]


def _uploads_dir() -> Path:
    d = settings.data_dir / "uploads" / "soporte_unificado"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _excel_path_for(upload_id: UUID) -> Path:
    return _uploads_dir() / f"{upload_id}.xlsx"


def _default_tamano_lote() -> int:
    """Lote en unidad de AFILIADOS (no registros). 1000 personas por lote."""
    return 1000


# ─── Upload opcional del Excel de vacunación ─────────────────────────────────

@router.post(
    "/uploads",
    response_model=VacunacionUploadResp,
    status_code=status.HTTP_201_CREATED,
    summary="Subir el .xlsx de vacunación para incluirlo en el soporte unificado",
    dependencies=[Depends(require_no_viewer)],
)
async def subir_excel_soporte_unificado(
    file: UploadFile = File(..., description="Archivo .xlsx de vacunación"),
) -> VacunacionUploadResp:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Solo se acepta .xlsx (Excel moderno).")
    upload_id = uuid4()
    dest = _excel_path_for(upload_id)
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        repo = get_vacunacion_repository()
        resumen = repo.resumen(dest)
        return VacunacionUploadResp(
            upload_id=upload_id,
            filename=file.filename,
            size_bytes=dest.stat().st_size,
            total_filas=resumen["total_filas"],
            por_regimen=resumen["por_regimen"],
            afiliados_por_regimen=resumen["afiliados_por_regimen"],
        )
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Error procesando el Excel: {e}") from e


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
    upload_id: UUID | None = Query(None, description="UUID del .xlsx de vacunación (opcional)"),
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

    excel_path: Path | None = None
    if upload_id is not None:
        excel_path = _excel_path_for(upload_id)
        if not excel_path.exists():
            raise HTTPException(status_code=404, detail=f"Upload {upload_id} no existe")

    conteo = conteo_por_modulo(desde, hasta, facturas=facturas, regimen=r, excel_path=excel_path)
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
    excel_path: Path | None = None
    if req.upload_id is not None:
        excel_path = _excel_path_for(req.upload_id)
        if not excel_path.exists():
            raise HTTPException(status_code=404, detail=f"Upload {req.upload_id} no existe. Subí primero el .xlsx.")

    facturas = _facturas_de(req.numero_factura)
    # `limite` = estimación de soportes (el orquestador no lo usa para cortar; procesa
    # todo el universo). Sirve para mostrarlo en la UI.
    conteo = conteo_por_modulo(req.desde, req.hasta, facturas=facturas, regimen=req.regimen, excel_path=excel_path)
    limite = max(1, sum(conteo.values()))

    nombre = req.nombre or f"Soporte Unificado {req.desde}—{req.hasta} · {req.regimen} · F{req.numero_factura}"

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
        excel_path=str(excel_path) if excel_path else None,
        creado_en=datetime.now(),
        created_by_username=current.username,
    )
    store.save(job)
    background.add_task(ejecutar_extraccion_soporte_unificado, job)
    return ExtraccionResp(**job.model_dump())


# ─── Listar / estado / lotes ─────────────────────────────────────────────────

@router.get("/extractions", response_model=list[ExtraccionResp], summary="Listar extracciones")
async def listar_extracciones_soporte_unificado() -> list[ExtraccionResp]:
    return [ExtraccionResp(**j.model_dump()) for j in store.list_by_tipo(ExtraccionTipo.SOPORTE_UNIFICADO)]


@router.get("/extractions/{job_id}", response_model=ExtraccionResp, summary="Estado de una extracción")
async def obtener_extraccion_soporte_unificado(job_id: UUID) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
    return ExtraccionResp(**job.model_dump())


@router.get("/extractions/{job_id}/lotes", response_model=list[Lote], summary="Listar lotes")
async def listar_lotes_soporte_unificado(job_id: UUID) -> list[Lote]:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
    return store.list_lotes(job_id)


@router.get("/extractions/{job_id}/lotes/{numero}", response_model=Lote, summary="Estado de un lote")
async def obtener_lote_soporte_unificado(job_id: UUID, numero: int) -> Lote:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
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
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
    store.rename(job_id, req.nombre or None)
    job = store.get(job_id)
    return ExtraccionResp(**job.model_dump())


@router.post(
    "/extractions/{job_id}/cancel",
    summary="Cancelar extracción en curso",
    dependencies=[Depends(require_no_viewer)],
)
async def cancelar_extraccion_soporte_unificado(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
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
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
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
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
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
        filename=f"{safe_filename(job.nombre, f'soporte_unificado_{job_id}')}.zip",
        media_type="application/zip",
    )


@router.get("/extractions/{job_id}/files", summary="Árbol de archivos (carpeta por afiliado)")
async def listar_archivos_soporte_unificado(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")
    if job.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Extracción en estado '{estado_label(job.estado)}'")

    job_dir = settings.data_dir / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    from collections import defaultdict
    # Agrupamos por carpeta de afiliado (doc_key); cada PDF es un módulo.
    por_afiliado: dict[str, list[dict]] = defaultdict(list)
    for pdf in job_dir.rglob("*.pdf"):
        doc_key = pdf.parent.name  # carpeta = <doc_key>
        por_afiliado[doc_key].append({"name": pdf.name, "size": pdf.stat().st_size})

    folders = [
        {"name": doc_key, "doc_key": doc_key, "files": sorted(items, key=lambda x: x["name"])}
        for doc_key, items in sorted(por_afiliado.items())
    ]
    return {"job_id": str(job_id), "folders": folders, "total": sum(len(f["files"]) for f in folders)}


@router.get(
    "/extractions/{job_id}/files/{afiliado}/{filename}",
    summary="Descargar un PDF individual",
    response_class=FileResponse,
)
async def descargar_pdf_soporte_unificado(job_id: UUID, afiliado: str, filename: str) -> FileResponse:
    job = store.get(job_id)
    if job is None or job.tipo != ExtraccionTipo.SOPORTE_UNIFICADO:
        raise HTTPException(status_code=404, detail="Extracción Soporte Unificado no encontrada")

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
