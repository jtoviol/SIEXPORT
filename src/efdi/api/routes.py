"""Endpoints REST."""
import math
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from efdi import __version__
from efdi.api.dependencies import current_user, require_modulo, require_no_viewer
from efdi.api.schemas import (
    ConteoFacturasResp,
    CrearExtraccionReq,
    DiagCheck,
    DiagnosticsResp,
    ExtraccionResp,
    HealthResp,
    RenombrarJobReq,
)
from efdi.config import settings
from efdi.domain.models import User, Atencion, EstadoExtraccion, Extraccion, ExtraccionTipo, Lote, estado_label, safe_filename
from efdi.infrastructure.db import db
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository import SqlServerRepository, get_repository
from efdi.services.extraction import ejecutar_extraccion

# `router` = endpoints meta (sin gating de módulo): /health, /db/ping, /diagnostics.
# Cualquier usuario autenticado puede consultar estos endpoints.
router = APIRouter()

# `router_di` = endpoints del módulo Demanda Inducida (/extractions/*). Aplicamos
# require_modulo("demanda-inducida") a nivel router; los POST/PATCH/DELETE de
# mutación adicionalmente requieren require_no_viewer en cada endpoint.
router_di = APIRouter(dependencies=[Depends(require_modulo("demanda-inducida"))])


def _auto_tamano_lote(limite: int) -> int:
    if limite <= 50:      return limite
    if limite <= 500:     return max(1, limite // 5)
    if limite <= 5_000:   return 500
    if limite <= 50_000:  return 1_000
    if limite <= 100_000: return 5_000
    if limite <= 400_000: return 8_000
    return 12_000


@router.get("/health", response_model=HealthResp, tags=["meta"])
async def health() -> HealthResp:
    return HealthResp(
        version=__version__,
        modo="mock" if settings.use_mock else "sqlserver",
    )


@router.get("/db/ping", tags=["meta"], summary="Test de conectividad a SQL Server")
async def db_ping() -> dict[str, object]:
    """Ejecuta SELECT 1 contra SQL Server. No depende del modo mock."""
    repo = SqlServerRepository()
    ok = repo.ping()
    return {
        "host": settings.db_host,
        "database": settings.db_name,
        "driver": settings.db_driver,
        "ok": ok,
    }


@router.get(
    "/diagnostics",
    response_model=DiagnosticsResp,
    tags=["meta"],
    summary="Diagnóstico completo del sistema (DB, disco, modo, métricas)",
)
async def diagnostics() -> DiagnosticsResp:
    """Verifica todos los puntos críticos y reporta el estado completo."""
    checks: dict[str, DiagCheck] = {}
    advertencias: list[str] = []

    # 1. SQLite operativo
    try:
        with db.connect() as conn:
            conn.execute("SELECT COUNT(*) FROM extracciones").fetchone()
        checks["sqlite"] = DiagCheck(ok=True, descripcion="SQLite operativo")
    except Exception as e:
        checks["sqlite"] = DiagCheck(ok=False, descripcion="SQLite no responde", detalle=str(e)[:200])

    # 2. Data dir escribible
    try:
        test_file = settings.data_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        checks["data_dir"] = DiagCheck(
            ok=True, descripcion=f"Directorio de datos escribible ({settings.data_dir})"
        )
    except Exception as e:
        checks["data_dir"] = DiagCheck(
            ok=False, descripcion="No se puede escribir en data_dir", detalle=str(e)[:200]
        )

    # 3. SQL Server (solo si no es mock)
    if not settings.use_mock:
        try:
            ok_sql = SqlServerRepository().ping()
            checks["sqlserver"] = DiagCheck(
                ok=ok_sql,
                descripcion=f"{'Conexión OK' if ok_sql else 'Sin conexión'} a {settings.db_host}",
                detalle=None if ok_sql else "Verificar VPN/firewall/credenciales",
            )
        except Exception as e:
            checks["sqlserver"] = DiagCheck(
                ok=False, descripcion="Error al conectar a SQL Server", detalle=str(e)[:200]
            )
    else:
        checks["modo_mock"] = DiagCheck(
            ok=True, descripcion="Modo MOCK activo (datos falsos, no conecta a SQL Server)"
        )
        advertencias.append("Estás en modo MOCK — los datos generados son ficticios")

    # 4. Métricas operativas
    jobs = store.list_all()
    metricas = {
        "total_extracciones": len(jobs),
        "extracciones_activas": sum(
            1 for j in jobs if j.estado in (EstadoExtraccion.PENDING, EstadoExtraccion.RUNNING)
        ),
        "extracciones_fallidas": sum(1 for j in jobs if j.estado == EstadoExtraccion.FAILED),
        "extracciones_completadas": sum(
            1 for j in jobs if j.estado == EstadoExtraccion.COMPLETED
        ),
    }

    # 5. Inconsistencias: jobs completados sin archivos en disco
    jobs_huerfanos = 0
    for j in jobs:
        if j.estado == EstadoExtraccion.COMPLETED:
            job_dir = settings.data_dir / f"job_{j.id}"
            if not job_dir.exists():
                jobs_huerfanos += 1
    if jobs_huerfanos > 0:
        advertencias.append(
            f"{jobs_huerfanos} extracción(es) completada(s) sin archivos en disco — "
            f"los datos pueden haberse eliminado manualmente"
        )

    # 6. Lotes fallidos en jobs marcados como completed
    jobs_con_lotes_fallidos = 0
    for j in jobs:
        if j.estado == EstadoExtraccion.COMPLETED:
            lotes = store.list_lotes(j.id)
            if any(l.estado == EstadoExtraccion.FAILED for l in lotes):
                jobs_con_lotes_fallidos += 1
    if jobs_con_lotes_fallidos > 0:
        advertencias.append(
            f"{jobs_con_lotes_fallidos} extracción(es) completaron con lotes fallidos — "
            f"revisar el detalle de cada una"
        )

    # Estado global
    if any(not c.ok for c in checks.values()):
        status = "error"
    elif advertencias:
        status = "warning"
    else:
        status = "ok"

    return DiagnosticsResp(
        status=status,
        version=__version__,
        modo="mock" if settings.use_mock else "sqlserver",
        checks=checks,
        metricas=metricas,
        advertencias=advertencias,
    )


@router_di.get(
    "/extractions/count",
    tags=["extracciones"],
    summary="Conteo previo de registros para un rango de fechas",
)
async def contar_registros(
    desde: date = Query(..., description="Fecha inicial (YYYY-MM-DD)"),
    hasta: date = Query(..., description="Fecha final (YYYY-MM-DD)"),
    numero_factura: str | None = Query(
        None,
        description="Sufijo numérico del código de régimen (ej '11502'). Backend arma CABn+FABn.",
    ),
) -> dict:
    """Consulta cuántos registros existen en la DB para el rango sin lanzar extracción.
    Útil para que el usuario confirme el volumen antes de generar.

    Si viene `numero_factura`, el conteo se restringe a los afiliados que están en
    CABn/FABn como Demanda Inducida (cod_diag_principal='Z048' vía _FACTURA_EXISTS),
    igual que lo va a hacer la extracción real."""
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
    repo = get_repository()
    total = repo.get_total(desde, hasta, facturas=facturas)
    if total <= 0:
        return {"total_en_db": 0, "limite_efectivo": 0, "tamano_lote": 0, "lotes_estimados": 0, "capeado": False}
    # Sin cap — el sistema procesa todo el universo que el filtro devuelva.
    # `capeado` se mantiene en la respuesta por compat con el frontend, siempre False.
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


def _validar_pares_facturas(codigos: list[str]) -> list[str]:
    """Normaliza y valida los códigos de factura.

    Reglas:
    - Cada código empieza por CAB o FAB y trae al menos 1 carácter después.
    - Sin duplicados.
    - Cada CAB exige un FAB con el mismo sufijo (y viceversa).
    """
    normalizados: list[str] = []
    for c in codigos:
        cn = (c or "").strip().upper()
        if not cn:
            continue
        if not (cn.startswith("CAB") or cn.startswith("FAB")):
            raise HTTPException(
                status_code=400,
                detail=f"Código '{c}' inválido: debe empezar por CAB o FAB.",
            )
        if len(cn) <= 3:
            raise HTTPException(
                status_code=400,
                detail=f"Código '{c}' inválido: falta el número después del prefijo.",
            )
        normalizados.append(cn)

    if not normalizados:
        raise HTTPException(status_code=400, detail="Debe enviar al menos un código de factura.")
    if len(set(normalizados)) != len(normalizados):
        raise HTTPException(status_code=400, detail="Hay códigos de factura repetidos.")

    cabs = {c[3:] for c in normalizados if c.startswith("CAB")}
    fabs = {c[3:] for c in normalizados if c.startswith("FAB")}
    faltantes: list[str] = []
    for n in sorted(cabs - fabs):
        faltantes.append(f"FAB{n} (falta el par de CAB{n})")
    for n in sorted(fabs - cabs):
        faltantes.append(f"CAB{n} (falta el par de FAB{n})")
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail="Códigos sin pareja: " + "; ".join(faltantes),
        )

    return normalizados


@router_di.get(
    "/extractions/facturas/count",
    response_model=ConteoFacturasResp,
    tags=["extracciones"],
    summary="Preview: cuenta filas y documentos únicos para una lista de códigos de factura",
)
async def contar_por_facturas(
    codigos: list[str] = Query(
        ...,
        description=(
            "Códigos de factura (CAB/FAB). Repetir el parámetro por cada código, "
            "o pasar uno solo separado por coma. Deben venir en pares CAB+FAB con el mismo número."
        ),
    ),
    cod_diag: str | None = Query(
        None,
        description=(
            "CIEX del módulo que invoca el preview, para que el conteo refleje SOLO "
            "lo que ese módulo va a generar. Z048=Demanda Inducida, Z131=FINDRISC, "
            "Z309=Planificación Familiar. Si no se pasa, cuenta todas las filas AP."
        ),
    ),
) -> ConteoFacturasResp:
    # Soporte "?codigos=CAB1,FAB1,CAB2,FAB2" además del repetido tradicional.
    aplanados: list[str] = []
    for raw in codigos:
        aplanados.extend(part for part in (raw or "").split(",") if part.strip())

    normalizados = _validar_pares_facturas(aplanados)
    repo = get_repository()
    resultado = repo.contar_por_facturas(normalizados, cod_diag=cod_diag)
    return ConteoFacturasResp(**resultado)


@router_di.post(
    "/extractions",
    response_model=ExtraccionResp,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["extracciones"],
    summary="Crear una nueva extracción de PDFs (se procesa en lotes)",
    dependencies=[Depends(require_no_viewer)],
)
async def crear_extraccion(
    req: CrearExtraccionReq,
    background: BackgroundTasks,
    current: User = Depends(current_user)
) -> ExtraccionResp:
    """Dispara la generación de PDFs en background.

    Si `limite > tamano_lote`, el job se divide en N lotes que se procesan
    secuencialmente. Cada lote produce su propio zip descargable.
    """
    # Construye lista CAB/FAB cuando viene factura
    facturas: list[str] | None = None
    nombre_default: str | None = None
    if req.numero_factura is not None:
        facturas = [f"CAB{req.numero_factura}", f"FAB{req.numero_factura}"]
        # Nombre default que distingue jobs sub vs cont en el sidebar
        nombre_default = f"DI {req.desde}—{req.hasta} · {req.regimen}"

    limite = req.limite
    if limite is None:
        repo = get_repository()
        total = repo.get_total(req.desde, req.hasta, facturas=facturas)  # type: ignore[attr-defined]
        if total <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se encontraron registros para el rango/factura indicados. "
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
        modo_pdf=req.modo_pdf,
        nombre=nombre_default,
        regimen=req.regimen,
        facturas=facturas,
        creado_en=datetime.now(),
        created_by_username=current.username,
    )
    store.save(job)
    background.add_task(ejecutar_extraccion, job)
    return ExtraccionResp(**job.model_dump())


@router_di.get(
    "/extractions",
    response_model=list[ExtraccionResp],
    tags=["extracciones"],
    summary="Listar extracciones",
)
async def listar_extracciones() -> list[ExtraccionResp]:
    return [
        ExtraccionResp(**j.model_dump())
        for j in store.list_by_tipo(ExtraccionTipo.DEMANDA_INDUCIDA)
    ]


@router_di.get(
    "/extractions/{job_id}",
    response_model=ExtraccionResp,
    tags=["extracciones"],
    summary="Estado de una extracción",
)
async def obtener_extraccion(job_id: UUID) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    return ExtraccionResp(**job.model_dump())


@router_di.get(
    "/extractions/{job_id}/atenciones",
    response_model=list[Atencion],
    tags=["extracciones"],
    summary="Datos crudos de cada atención del job (máx 5000 del primer lote)",
)
async def obtener_atenciones(job_id: UUID) -> list[Atencion]:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    return store.get_atenciones(job_id)


@router_di.get(
    "/extractions/{job_id}/lotes",
    response_model=list[Lote],
    tags=["extracciones", "lotes"],
    summary="Listar lotes de una extracción con estado individual",
)
async def listar_lotes(job_id: UUID) -> list[Lote]:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    return store.list_lotes(job_id)


@router_di.get(
    "/extractions/{job_id}/lotes/{numero}",
    response_model=Lote,
    tags=["extracciones", "lotes"],
    summary="Estado de un lote específico",
)
async def obtener_lote(job_id: UUID, numero: int) -> Lote:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    return lote


@router_di.get(
    "/extractions/{job_id}/lotes/{numero}/download",
    tags=["extracciones", "lotes"],
    summary="Descargar el zip de un lote individual",
    response_class=FileResponse,
)
async def descargar_lote(job_id: UUID, numero: int) -> FileResponse:
    lote = store.get_lote(job_id, numero)
    if lote is None:
        raise HTTPException(status_code=404, detail=f"Lote {numero} no existe")
    if lote.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Lote {numero} en estado '{estado_label(lote.estado)}' — aún no descargable",
        )
    if not lote.zip_path or not Path(lote.zip_path).exists():
        raise HTTPException(status_code=410, detail="Zip del lote no disponible")
    job = store.get(job_id)
    base = safe_filename(job.nombre if job else None, f"lote_{numero:03d}_{job_id}")
    if job and job.nombre:
        base = f"{base}_lote_{numero:03d}"
    return FileResponse(
        path=lote.zip_path,
        filename=f"{base}.zip",
        media_type="application/zip",
    )


def _borrar_artefactos_extraccion(job_id: UUID) -> dict[str, int]:
    """Borra del disco: carpeta job_<id>/ y zip extraccion_<id>.zip. Idempotente."""
    borrados = {"carpetas": 0, "zips": 0}
    job_dir = settings.data_dir / f"job_{job_id}"
    if job_dir.exists() and job_dir.is_dir():
        shutil.rmtree(job_dir, ignore_errors=True)
        borrados["carpetas"] = 1
    zip_path = settings.data_dir / f"extraccion_{job_id}.zip"
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)
        borrados["zips"] = 1
    return borrados


@router_di.post(
    "/extractions/{job_id}/cancel",
    tags=["extracciones"],
    summary="Cancelar una extracción en curso (no la elimina, queda como 'cancelled')",
    dependencies=[Depends(require_no_viewer)],
)
async def cancelar_extraccion(job_id: UUID) -> dict[str, object]:
    """Marca el job como cancelado. El worker lo detecta entre lotes y aborta.

    Lo ya generado queda accesible (carpetas y zips de los lotes completados).
    """
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    if job.estado not in (EstadoExtraccion.PENDING, EstadoExtraccion.RUNNING):
        raise HTTPException(
            status_code=409,
            detail=f"No se puede cancelar — la extracción está en estado '{estado_label(job.estado)}'",
        )
    job.estado = EstadoExtraccion.CANCELLED
    job.mensaje_error = "Cancelación solicitada por el usuario"
    store.save(job)
    return {
        "id": str(job_id),
        "cancelado": True,
        "mensaje": "La cancelación se aplicará al terminar el lote actual",
    }


@router_di.patch(
    "/extractions/{job_id}/nombre",
    response_model=ExtraccionResp,
    tags=["extracciones"],
    summary="Renombrar una extracción",
    dependencies=[Depends(require_no_viewer)],
)
async def renombrar_extraccion(job_id: UUID, req: RenombrarJobReq) -> ExtraccionResp:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    store.rename(job_id, req.nombre or None)
    job = store.get(job_id)
    return ExtraccionResp(**job.model_dump())


@router_di.delete(
    "/extractions/{job_id}",
    tags=["extracciones"],
    summary="Eliminar una extracción (SQLite + archivos en disco)",
    dependencies=[Depends(require_no_viewer)],
)
async def eliminar_extraccion(job_id: UUID) -> dict[str, object]:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    artefactos = _borrar_artefactos_extraccion(job_id)
    store.delete(job_id)
    return {"id": str(job_id), "borrado": True, **artefactos}


@router_di.delete(
    "/extractions",
    tags=["extracciones"],
    summary="Limpieza masiva — borrar extracciones por antigüedad o estado",
    dependencies=[Depends(require_no_viewer)],
)
async def limpiar_extracciones(
    older_than_days: int | None = Query(None, ge=0, description="Borrar las creadas hace ≥ N días"),
    estado: str | None = Query(None, description="Borrar solo las que estén en este estado"),
    confirmar: bool = Query(False, description="Sin esto en true, hace dry-run"),
) -> dict[str, object]:
    """Sin parámetros → dry-run que reporta TODAS las extracciones a borrar.

    Con `older_than_days=30` → solo las viejas. Con `estado=failed` → solo fallidas.
    Pasar `confirmar=true` para ejecutar realmente.
    """
    todas = store.list_all()
    candidatas = todas
    if older_than_days is not None:
        umbral = datetime.now() - timedelta(days=older_than_days)
        candidatas = [j for j in candidatas if j.creado_en < umbral]
    if estado is not None:
        candidatas = [j for j in candidatas if (j.estado.value if hasattr(j.estado, "value") else j.estado) == estado]

    resumen = {
        "modo": "ejecutado" if confirmar else "dry_run",
        "total_candidatas": len(candidatas),
        "ids": [str(j.id) for j in candidatas[:20]],
        "borradas": 0,
        "carpetas_borradas": 0,
        "zips_borrados": 0,
    }
    if confirmar:
        for j in candidatas:
            artefactos = _borrar_artefactos_extraccion(j.id)
            store.delete(j.id)
            resumen["borradas"] += 1
            resumen["carpetas_borradas"] += artefactos["carpetas"]
            resumen["zips_borrados"] += artefactos["zips"]
    return resumen


@router_di.get(
    "/extractions/{job_id}/download",
    tags=["extracciones"],
    summary="Descargar mega-zip con TODOS los lotes (puede ser muy grande)",
    response_class=FileResponse,
)
async def descargar_extraccion(job_id: UUID) -> FileResponse:
    """Descarga el zip global. Para extracciones grandes (>50K) preferir descargar
    lote por lote vía `/extractions/{id}/lotes/{n}/download`."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    if job.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Extracción en estado '{estado_label(job.estado)}' — aún no descargable",
        )
    # Si no hay zip global pero hay lotes, lo construimos on-demand combinando los lotes
    if not job.zip_path or not Path(job.zip_path).exists():
        lotes = store.list_lotes(job_id)
        zips_lotes = [Path(l.zip_path) for l in lotes if l.zip_path and Path(l.zip_path).exists()]
        if not zips_lotes:
            raise HTTPException(status_code=410, detail="No hay zips disponibles")
        mega_zip = settings.data_dir / f"extraccion_{job_id}.zip"
        import zipfile as _zf
        with _zf.ZipFile(mega_zip, "w", _zf.ZIP_STORED) as out:
            for lz in zips_lotes:
                with _zf.ZipFile(lz) as inp:
                    for name in inp.namelist():
                        out.writestr(f"{lz.stem}/{name}", inp.read(name))
        job.zip_path = str(mega_zip)
        store.save(job)
    return FileResponse(
        path=job.zip_path,
        filename=f"{safe_filename(job.nombre, f'extraccion_{job_id}')}.zip",
        media_type="application/zip",
    )


@router_di.get(
    "/extractions/{job_id}/files",
    tags=["extracciones"],
    summary="Árbol de archivos de una extracción completada",
)
async def listar_archivos(job_id: UUID) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")
    if job.estado != EstadoExtraccion.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Extracción en estado '{estado_label(job.estado)}'")

    job_dir = settings.data_dir / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    # Estructura nueva (1 PDF por afiliado): job_xxx/lote_NNN/CC_xxx.pdf
    # Cada archivo es directamente el PDF multipágina del afiliado.
    # Lo agrupamos por "tipo de documento" para mantener el árbol con secciones.
    from collections import defaultdict
    import re
    agrupado: dict[str, list[dict]] = defaultdict(list)

    for pdf in job_dir.rglob("*.pdf"):
        nombre = pdf.stem  # ej: "CC_11434102145"
        match = re.match(r"^([A-Z]{2})_(.+)$", nombre)
        if not match:
            continue
        tipo_doc = match.group(1)
        # El "lote" del que vino (carpeta padre)
        lote_dir = pdf.parent
        lote_name = lote_dir.name if lote_dir.name.startswith("lote_") else ""
        agrupado[tipo_doc].append({
            "name": pdf.name,
            "doc_key": nombre,
            "size": pdf.stat().st_size,
            "lote": lote_name,
        })

    folders = []
    for tipo, items in sorted(agrupado.items()):
        files = sorted(items, key=lambda x: x["doc_key"])
        # Estructura compatible con frontend: "name" del folder = tipo doc
        # cada "file" tiene name (filename) y doc_key (sin extensión)
        folders.append({"name": tipo, "files": files})

    return {"job_id": str(job_id), "folders": folders, "total": sum(len(f["files"]) for f in folders)}


@router_di.get(
    "/extractions/{job_id}/files/{afiliado}/{filename}",
    tags=["extracciones"],
    summary="Descargar PDF individual de una extracción",
    response_class=FileResponse,
)
async def descargar_pdf_individual(job_id: UUID, afiliado: str, filename: str) -> FileResponse:
    """Descarga el PDF de un afiliado. El segundo segmento de URL (afiliado)
    se mantiene por compatibilidad pero el filename ahora es CC_xxx.pdf."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Extracción no encontrada")

    job_dir = settings.data_dir.resolve() / f"job_{job_id}"
    if not job_dir.exists():
        raise HTTPException(status_code=410, detail="Directorio no disponible")

    # Buscar el archivo por filename (la estructura nueva es: lote_NNN/CC_xxx.pdf)
    candidates = list(job_dir.rglob(filename))
    if not candidates:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    file_path = candidates[0].resolve()
    if not file_path.is_relative_to(job_dir):
        raise HTTPException(status_code=400, detail="Ruta inválida")

    return FileResponse(path=file_path, filename=filename, media_type="application/pdf")
