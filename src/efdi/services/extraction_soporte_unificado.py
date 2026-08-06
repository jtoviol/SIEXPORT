"""Soporte Unificado — recolector cross-módulo (Fase 1).

Este módulo NO tiene query ni generador propios: orquesta los 8 módulos
existentes y reindexa TODO por afiliado (`doc_key`).

Filtro nativo de cada módulo (no se toca la lógica de ninguno):
- Facturables (factura + su CIEX propio, vía repo): Demanda Inducida, FINDRISC,
  Planificación Familiar, Pruebas Rápidas, Gestión Captación.
- Régimen (fecha + régimen): Caracterización Familiar, Educación Grupal.
- Excel (upload + régimen): Vacunación (solo si se sube el .xlsx).

Universo = unión de todos: una persona entra al índice si aparece en CUALQUIER
módulo. Caracterización se ancla al JEFE de familia (parentesco = "JEFE DE
FAMILIA"); su PDF de familia queda solo en la carpeta del jefe.

Fase 1: construye el índice y lo resume (cuántas personas, cuántos soportes por
módulo). NO genera PDFs — eso llega en la Fase 2.
"""
from __future__ import annotations

import logging
import math
import multiprocessing as mp
import os
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from efdi.config import settings
from efdi.domain import services
from efdi.domain.models import (
    EstadoExtraccion,
    Extraccion,
    FamiliaCaracterizada,
    Lote,
    RegistroCaracterizacion,
)
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository import get_repository
from efdi.infrastructure.repository_captacion import get_captacion_repository
from efdi.infrastructure.repository_caracterizacion import get_caracterizacion_repository
from efdi.infrastructure.repository_educacion_grupal import get_educacion_grupal_repository
from efdi.infrastructure.repository_findrisc import get_findrisc_repository
from efdi.infrastructure.repository_planfami import get_planfami_repository
from efdi.infrastructure.repository_pruebas import get_pruebas_repository
from efdi.infrastructure.repository_vacunacion import get_vacunacion_repository
from efdi.pdf.parallel_soporte_unificado import _worker as pdf_worker_unificado

log = logging.getLogger(__name__)

# Etiqueta legible por id de módulo (tab-id del frontend).
MODULO_LABEL: dict[str, str] = {
    "demanda-inducida":        "Demanda Inducida",
    "findrisc":                "FINDRISC",
    "planificacion-familiar":  "Planificación Familiar",
    "pruebas-rapidas":         "Pruebas Rápidas",
    "gestion-captacion":       "Gestión Captación",
    "caracterizacion-familiar":"Caracterización Familiar",
    "educacion-grupal":        "Educación Grupal",
    "vacunacion":              "Vacunación",
}

# (id_módulo, factory del repo, método de fetch, función de agrupación).
# Facturables: filtran por `facturas` y devuelven objetos-afiliado con `.doc_key`.
# Cada uno aplica además su CIEX propio dentro del EXISTS contra AVS_REGISTROS_AP.
_FACTURABLES: list[tuple] = [
    ("demanda-inducida",       get_repository,            "obtener_atenciones", services.agrupar_por_afiliado),
    ("findrisc",               get_findrisc_repository,   "obtener_registros",  services.agrupar_por_afiliado_findrisc),
    ("planificacion-familiar", get_planfami_repository,   "obtener_registros",  services.agrupar_por_afiliado_planfami),
    ("pruebas-rapidas",        get_pruebas_repository,    "obtener_respuestas", services.agrupar_por_afiliado_pruebas),
]

# Régimen (fecha + régimen) que ya agrupan por afiliado con `.doc_key`.
# Gestión Captación va aquí (NO se factura: el SP prGeneraRips no la procesa),
# usando el filtro `regimen` que se le agregó a su repo (AFIC_REGIMEN).
_REGIMEN_SIMPLE: list[tuple] = [
    ("gestion-captacion", get_captacion_repository,        "obtener_registros", services.agrupar_por_afiliado_captacion),
    ("educacion-grupal",  get_educacion_grupal_repository, "obtener_registros", services.agrupar_por_afiliado_educacion_grupal),
]


@dataclass
class PersonaSoportes:
    """Todos los soportes de una persona, por módulo.

    `modulos[<id>]` es la lista de objetos-afiliado ya agrupados de ese módulo
    (listos para pasar al generador en la Fase 2). Casi siempre 1 elemento; en
    DI/FINDRISC/PlanFami/Captación puede haber varios (uno por fecha).
    """

    doc_key: str
    nombre: str | None = None
    modulos: dict[str, list] = field(default_factory=dict)

    def agregar(self, mod_id: str, obj: object, nombre: str | None) -> None:
        self.modulos.setdefault(mod_id, []).append(obj)
        if not self.nombre and nombre:
            self.nombre = nombre

    @property
    def total_soportes(self) -> int:
        return sum(len(v) for v in self.modulos.values())


@dataclass
class IndiceUnificado:
    """Universo completo indexado por documento."""

    personas: dict[str, PersonaSoportes] = field(default_factory=dict)

    def agregar(self, doc_key: str, mod_id: str, obj: object, nombre: str | None = None) -> None:
        p = self.personas.get(doc_key)
        if p is None:
            p = PersonaSoportes(doc_key=doc_key)
            self.personas[doc_key] = p
        p.agregar(mod_id, obj, nombre)

    # ── Métricas para validación ──────────────────────────────────────────
    @property
    def total_personas(self) -> int:
        return len(self.personas)

    @property
    def total_soportes(self) -> int:
        return sum(p.total_soportes for p in self.personas.values())

    def personas_por_modulo(self) -> dict[str, int]:
        """Cuántas personas tienen al menos un soporte de cada módulo."""
        out: dict[str, int] = {}
        for p in self.personas.values():
            for mod_id in p.modulos:
                out[mod_id] = out.get(mod_id, 0) + 1
        return out

    def soportes_por_modulo(self) -> dict[str, int]:
        """Cuántos soportes (≈ PDFs futuros) genera cada módulo en total."""
        out: dict[str, int] = {}
        for p in self.personas.values():
            for mod_id, objs in p.modulos.items():
                out[mod_id] = out.get(mod_id, 0) + len(objs)
        return out


def conteo_por_modulo(
    desde: date,
    hasta: date,
    *,
    facturas: list[str] | None,
    regimen: str | None,
    excel_path: Path | None = None,
) -> dict[str, int]:
    """Conteo RÁPIDO por módulo (solo COUNTs, sin traer filas ni deduplicar).

    Es un desglose de soportes ≈ PDFs por módulo. El total es cota superior de
    personas distintas (una persona en N módulos cuenta N veces). Barato: se usa
    en el preview antes de generar.
    """
    out: dict[str, int] = {}
    for mod_id, getter, _, _ in _FACTURABLES:
        try:
            out[mod_id] = getter().get_total(desde, hasta, facturas=facturas)
        except Exception:  # noqa: BLE001
            log.exception("soporte_unif.conteo_falló", extra={"modulo": mod_id})
            out[mod_id] = 0
    for mod_id, getter, _, _ in _REGIMEN_SIMPLE:
        try:
            out[mod_id] = getter().get_total(desde, hasta, regimen=regimen)
        except Exception:  # noqa: BLE001
            log.exception("soporte_unif.conteo_falló", extra={"modulo": mod_id})
            out[mod_id] = 0
    try:
        out["caracterizacion-familiar"] = get_caracterizacion_repository().get_total(
            desde, hasta, regimen=regimen
        )
    except Exception:  # noqa: BLE001
        log.exception("soporte_unif.conteo_falló", extra={"modulo": "caracterizacion-familiar"})
        out["caracterizacion-familiar"] = 0
    if excel_path is not None:
        try:
            out["vacunacion"] = get_vacunacion_repository().get_total(excel_path, regimen=regimen)
        except Exception:  # noqa: BLE001
            log.exception("soporte_unif.conteo_falló", extra={"modulo": "vacunacion"})
            out["vacunacion"] = 0
    return out


def _jefe_doc_key(fam: FamiliaCaracterizada) -> tuple[str, str] | None:
    """Devuelve (doc_key, nombre) del jefe de la familia, o None si no se puede.

    El jefe es el integrante con parentesco 'JEFE DE FAMILIA'. Si no hay uno
    explícito, cae al primer integrante con documento (misma tolerancia que el
    repo real: "familias sin jefe caen al primer integrante por orden natural").
    """
    jefe: RegistroCaracterizacion | None = None
    for r in fam.registros:
        if (r.parentesco or "").strip().upper() == "JEFE DE FAMILIA":
            jefe = r
            break
    if jefe is None:
        jefe = next((r for r in fam.registros if r.num_documento), None)
    if jefe is None or not jefe.num_documento:
        return None
    tipo = (jefe.tipo_documento or "CC").strip()
    doc_key = f"{tipo}_{jefe.num_documento}"
    return doc_key, (jefe.nombres_apellidos or "").strip() or None


def recolectar_universo(
    desde: date,
    hasta: date,
    *,
    facturas: list[str] | None,
    regimen: str | None,
    excel_path: Path | None = None,
) -> IndiceUnificado:
    """Recorre los 8 módulos con su filtro nativo y arma el índice por afiliado.

    No genera PDFs. Registra en log el conteo por módulo para validación.
    """
    idx = IndiceUnificado()

    # ── Facturables (factura + CIEX propio del repo) ──────────────────────
    for mod_id, getter, metodo, agrupar in _FACTURABLES:
        try:
            repo = getter()
            total = repo.get_total(desde, hasta, facturas=facturas)
            if total <= 0:
                continue
            filas = getattr(repo, metodo)(desde, hasta, limite=total, offset=0, facturas=facturas)
            for g in agrupar(filas):
                idx.agregar(g.doc_key, mod_id, g, nombre=getattr(g, "nombre_completo", None))
            log.info("soporte_unif.modulo", extra={"modulo": mod_id, "filas": len(filas)})
        except Exception:  # noqa: BLE001
            log.exception("soporte_unif.modulo_falló", extra={"modulo": mod_id})

    # ── Régimen simple (fecha + régimen) ──────────────────────────────────
    for mod_id, getter, metodo, agrupar in _REGIMEN_SIMPLE:
        try:
            repo = getter()
            total = repo.get_total(desde, hasta, regimen=regimen)
            if total <= 0:
                continue
            filas = getattr(repo, metodo)(desde, hasta, limite=total, offset=0, regimen=regimen)
            for g in agrupar(filas):
                idx.agregar(g.doc_key, mod_id, g, nombre=getattr(g, "nombre_completo", None))
            log.info("soporte_unif.modulo", extra={"modulo": mod_id, "filas": len(filas)})
        except Exception:  # noqa: BLE001
            log.exception("soporte_unif.modulo_falló", extra={"modulo": mod_id})

    # ── Caracterización (familia → jefe) ──────────────────────────────────
    try:
        repo = get_caracterizacion_repository()
        total = repo.get_total(desde, hasta, regimen=regimen)  # unidad = familias
        if total > 0:
            filas = repo.obtener_registros(desde, hasta, limite=total, offset=0, regimen=regimen)
            familias = services.agrupar_por_familia_caracterizacion(filas)
            anclados = 0
            for fam in familias:
                jefe = _jefe_doc_key(fam)
                if jefe is None:
                    continue
                doc_key, nombre = jefe
                idx.agregar(doc_key, "caracterizacion-familiar", fam, nombre=nombre)
                anclados += 1
            log.info("soporte_unif.modulo", extra={"modulo": "caracterizacion-familiar", "familias": len(familias), "anclados": anclados})
    except Exception:  # noqa: BLE001
        log.exception("soporte_unif.modulo_falló", extra={"modulo": "caracterizacion-familiar"})

    # ── Vacunación (solo si hay Excel) ────────────────────────────────────
    if excel_path is not None:
        try:
            repo = get_vacunacion_repository()
            total = repo.get_total(excel_path, regimen=regimen)
            if total > 0:
                filas = repo.obtener_registros(excel_path=excel_path, regimen=regimen, limite=total, offset=0)
                for g in services.agrupar_por_afiliado_vacunacion(filas):
                    idx.agregar(g.doc_key, "vacunacion", g, nombre=getattr(g, "nombre_completo", None))
                log.info("soporte_unif.modulo", extra={"modulo": "vacunacion", "filas": len(filas)})
        except Exception:  # noqa: BLE001
            log.exception("soporte_unif.modulo_falló", extra={"modulo": "vacunacion"})

    log.info(
        "soporte_unif.universo",
        extra={
            "personas": idx.total_personas,
            "soportes": idx.total_soportes,
            "por_modulo": idx.soportes_por_modulo(),
        },
    )
    return idx


# ═══════════════════════════════════════════════════════════════════════════
# FASE 2 — Emisor: por cada persona, carpeta + 1 PDF por módulo → ZIP por lote.
# ═══════════════════════════════════════════════════════════════════════════

def _nombre_archivo(mod_id: str, obj: object) -> str:
    """Nombre del PDF de un módulo DENTRO de la carpeta de la persona.

    Los módulos por-fecha (DI/FINDRISC/PlanFami/Captación) llevan la fecha en el
    nombre para no colisionar entre sí; los de 1-PDF-por-persona no.
    """
    slug = mod_id.replace("-", "_")
    if mod_id == "demanda-inducida":
        return f"{slug}_{obj.fecha_registro}.pdf"
    if mod_id == "findrisc":
        return f"{slug}_{obj.fecha_registro}.pdf"
    if mod_id == "planificacion-familiar":
        return f"{slug}_{obj.fecha_gestion}.pdf"
    if mod_id == "gestion-captacion":
        return f"{slug}_{obj.fecha_captacion}.pdf"
    # vacunacion, educacion-grupal, caracterizacion-familiar → 1 PDF por persona
    return f"{slug}.pdf"


def _tareas_de_persona(persona: PersonaSoportes, persona_dir: Path) -> list[tuple]:
    """Expande una persona a tareas (mod_id, obj, ruta). 1 tarea = 1 PDF.

    Pruebas Rápidas genera 1 PDF consolidado por afiliado con todas sus pruebas.
    """
    tareas: list[tuple] = []
    for mod_id, objs in persona.modulos.items():
        for obj in objs:
            if mod_id == "pruebas-rapidas":
                tareas.append((mod_id, obj, persona_dir / "pruebas_rapidas.pdf"))
            else:
                tareas.append((mod_id, obj, persona_dir / _nombre_archivo(mod_id, obj)))
    return tareas


def _generar_pdfs_unificado(
    tareas: list[tuple], regimen: str | None, pool: "mp.pool.Pool | None" = None,
) -> int:
    """Genera todos los PDFs de una lista de tareas. Devuelve cuántos."""
    n = len(tareas)
    if settings.pdf_workers == 0 or n < settings.pdf_parallel_threshold or pool is None:
        for mod_id, obj, path in tareas:
            path.parent.mkdir(parents=True, exist_ok=True)
            pdf_worker_unificado((mod_id, obj, str(path), regimen))
        return n
    for d in {p.parent for _, _, p in tareas}:
        d.mkdir(parents=True, exist_ok=True)
    payload = [(mod_id, obj, str(path), regimen) for mod_id, obj, path in tareas]
    chunksize = max(20, n // (pool._processes * 8))  # type: ignore[attr-defined]
    results = list(pool.imap_unordered(pdf_worker_unificado, payload, chunksize=chunksize))
    return len(results)


def ejecutar_extraccion_soporte_unificado(job: Extraccion) -> None:
    """Job completo: recolecta el universo (1 vez) → lotes de afiliados → PDFs → zip."""
    try:
        job.estado = EstadoExtraccion.RUNNING
        store.save(job)

        # ── Fase A: recolectar el universo una sola vez ──
        excel = Path(job.excel_path) if job.excel_path else None
        idx = recolectar_universo(
            job.desde, job.hasta,
            facturas=job.facturas, regimen=job.regimen, excel_path=excel,
        )
        personas = sorted(idx.personas.values(), key=lambda p: p.doc_key)
        n = len(personas)
        job.total_afiliados = n
        if n == 0:
            job.estado = EstadoExtraccion.COMPLETED
            job.completado_en = datetime.now()
            job.mensaje_error = "No se encontraron afiliados para el filtro indicado"
            store.save(job)
            return

        # ── Lotes por afiliado (slice en memoria, sin re-consultar) ──
        tamano = job.tamano_lote
        n_lotes = max(1, math.ceil(n / tamano))
        job.total_lotes = n_lotes
        store.save(job)

        planificados: list[tuple[Lote, list[PersonaSoportes]]] = []
        for i in range(1, n_lotes + 1):
            offset = (i - 1) * tamano
            grupo = personas[offset:offset + tamano]
            lote = Lote(job_id=job.id, numero=i, offset_inicio=offset, tamano=max(1, len(grupo)))
            store.save_lote(lote)
            planificados.append((lote, grupo))

        # ── Pool de PDFs (mismo criterio que los otros módulos) ──
        lote_workers = max(1, settings.lote_workers)
        usa_pool = lote_workers == 1 and settings.pdf_workers != 0 and n >= settings.pdf_parallel_threshold
        pool = None
        if usa_pool:
            workers = (os.cpu_count() or 2) if settings.pdf_workers < 0 else settings.pdf_workers
            ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
            pool = ctx.Pool(processes=max(1, workers))

        _lock = threading.Lock()
        total_pdfs = 0
        lotes_fallidos = 0
        afiliados_glob: set[str] = set()
        cancelado = threading.Event()

        def _run_lote(lote: Lote, grupo: list[PersonaSoportes]) -> None:
            nonlocal total_pdfs, lotes_fallidos
            if cancelado.is_set():
                lote.estado = EstadoExtraccion.CANCELLED
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                return
            est = store.get(job.id)
            if est and est.estado == EstadoExtraccion.CANCELLED:
                cancelado.set()
                lote.estado = EstadoExtraccion.CANCELLED
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                return

            lote.estado = EstadoExtraccion.RUNNING
            lote.iniciado_en = datetime.now()
            lote.total_afiliados = len(grupo)
            lote.fase = f"Generando PDFs ({len(grupo)} afiliados)…"
            store.save_lote(lote)
            try:
                lote_dir = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}"
                lote_dir.mkdir(parents=True, exist_ok=True)

                tareas: list[tuple] = []
                for p in grupo:
                    tareas.extend(_tareas_de_persona(p, lote_dir / p.doc_key))

                pdfs = _generar_pdfs_unificado(tareas, job.regimen, pool=pool)
                lote.total_atenciones = len(tareas)
                lote.total_pdfs = pdfs

                lote.fase = "Empaquetando ZIP…"
                store.save_lote(lote)
                zip_path = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for pdf in lote_dir.rglob("*.pdf"):
                        zf.write(pdf, arcname=pdf.relative_to(lote_dir))
                lote.zip_path = str(zip_path)
                lote.estado = EstadoExtraccion.COMPLETED
                lote.completado_en = datetime.now()
                store.save_lote(lote)

                with _lock:
                    total_pdfs += pdfs
                    for p in grupo:
                        afiliados_glob.add(p.doc_key)
                    job.total_pdfs = total_pdfs
                    job.total_afiliados = len(afiliados_glob)
                    store.save(job)
            except Exception as e:  # noqa: BLE001
                log.exception("soporte_unif.lote_falló", extra={"lote": lote.numero})
                lote.estado = EstadoExtraccion.FAILED
                lote.mensaje_error = str(e)[:500]
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                with _lock:
                    lotes_fallidos += 1

        with ThreadPoolExecutor(max_workers=lote_workers) as ex:
            futs = [ex.submit(_run_lote, lote, grupo) for lote, grupo in planificados]
            for f in as_completed(futs):
                f.result()

        if pool is not None:
            pool.close()
            pool.join()

        if cancelado.is_set():
            job.completado_en = datetime.now()
            job.mensaje_error = "Cancelado por el usuario"
            store.save(job)
            return

        job.total_afiliados = len(afiliados_glob)
        job.total_pdfs = total_pdfs
        job.completado_en = datetime.now()
        if lotes_fallidos == n_lotes:
            job.estado = EstadoExtraccion.FAILED
            job.mensaje_error = "Todos los lotes fallaron"
        elif lotes_fallidos:
            job.estado = EstadoExtraccion.COMPLETED
            job.mensaje_error = f"{lotes_fallidos} de {n_lotes} lotes fallaron"
        else:
            job.estado = EstadoExtraccion.COMPLETED
        store.save(job)
        log.info(
            "soporte_unif.done",
            extra={"job": str(job.id), "afiliados": job.total_afiliados, "pdfs": total_pdfs},
        )

    except Exception as e:  # noqa: BLE001
        log.exception("soporte_unif.failed")
        job.estado = EstadoExtraccion.FAILED
        job.mensaje_error = str(e)[:500]
        job.completado_en = datetime.now()
        store.save(job)
