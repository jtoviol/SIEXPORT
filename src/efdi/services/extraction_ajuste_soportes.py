"""Ajuste de Soportes — fusiona los PDFs de un job de Soporte Unificado ya
completado en UN SOLO PDF por afiliado, renombrado para facturación.

Puerto al backend del script externo `unificar_soportes.py` (post-proceso
manual sobre archivos ya descargados): esto opera directo sobre los PDFs que
el propio sistema ya generó para un job de Soporte Unificado, sin necesidad
de descargar ni descomprimir nada a mano.

Simplificaciones respecto al script original (ver plan de la sesión):
- El régimen NO se detecta por nombre de carpeta: cada Soporte Unificado ya
  tiene un régimen fijo y obligatorio desde que se creó — nunca hay
  "SIN_REGIMEN" posible acá.
- La factura NO se pregunta por consola: viene en el request (pre-llenada
  desde el job de origen si ya tenía una, pero siempre editable).
- El identificador de afiliado es el `doc_key` que el propio sistema ya
  armó (no hace falta parsear nombres de carpeta arbitrarios de disco), pero
  se valida con el MISMO regex que el script para excluir los mismos casos
  reales: documentos tipo MS con número alfanumérico (menores sin documento
  propio) y carpetas `FAM_<clave>` (familias de Caracterización Familiar sin
  ningún integrante con documento).
- Se omite deliberadamente el cruce "misma persona en los 2 regímenes" del
  script (exigiría comparar contra OTRO job de régimen distinto — fuera de
  alcance de esta fase).
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pypdf import PdfWriter

from efdi.config import settings
from efdi.domain.models import EstadoExtraccion, Extraccion, Lote, safe_filename
from efdi.infrastructure.job_store import store

log = logging.getLogger(__name__)

NIT_SERSOCIAL = "900422757"
PREFIJO_FIJO = "HEV"

# tipo = letras, numero = dígitos puros. Excluye a propósito doc_key tipo
# "FAM_<clave>" y "MS_<alfanumérico>" — no hay forma segura de derivar un
# <TIPODOC><NUMERODOC> válido para el nombre final en esos casos.
_PATRON_DOC_KEY = re.compile(r"^([A-Za-z]+)_(\d+)$")


def _partir_doc_key(doc_key: str) -> tuple[str, str] | None:
    """Devuelve (tipo, numero) si `doc_key` es un identificador válido, o None."""
    m = _PATRON_DOC_KEY.match(doc_key.strip())
    if not m:
        return None
    return m.group(1).upper(), m.group(2)


def numero_de_facturas(facturas: list[str] | None) -> str:
    """Extrae el sufijo numérico de la primera factura (['CAB11502','FAB11502'] -> '11502')."""
    if not facturas:
        return ""
    primera = facturas[0]
    return primera.removeprefix("CAB").removeprefix("FAB")


def nombre_pdf_salida(factura: str, tipo: str, numero: str) -> str:
    """HEV_900422757_<factura>_<TIPO><NUMERO>.pdf — mismo formato que el script."""
    factura_saneada = safe_filename(factura, "sinfactura")
    return f"{PREFIJO_FIJO}_{NIT_SERSOCIAL}_{factura_saneada}_{tipo}{numero}.pdf"


@dataclass
class ResultadoFusion:
    pdfs_ok: int = 0
    pdfs_error: int = 0
    paginas: int = 0


def fusionar_pdfs(pdfs: list[Path], destino: Path) -> ResultadoFusion:
    """Fusiona `pdfs` (en el orden recibido) en `destino`.

    Un PDF fuente corrupto/ilegible no tumba al resto: se salta y se cuenta
    como error (misma tolerancia que el script original). Si TODOS los PDFs
    de un afiliado fallan, no se escribe ningún archivo para él.
    """
    resultado = ResultadoFusion()
    writer = PdfWriter()
    try:
        for pdf in pdfs:
            try:
                writer.append(str(pdf))
                resultado.pdfs_ok += 1
            except Exception:  # noqa: BLE001
                log.exception("ajuste_soportes.pdf_fuente_falló", extra={"pdf": str(pdf)})
                resultado.pdfs_error += 1
        if resultado.pdfs_ok > 0:
            resultado.paginas = len(writer.pages)
            destino.parent.mkdir(parents=True, exist_ok=True)
            with destino.open("wb") as f:
                writer.write(f)
    finally:
        writer.close()
    return resultado


@dataclass
class _AfiliadoValido:
    doc_key: str
    tipo: str
    numero: str
    pdfs: list[Path] = field(default_factory=list)


def recolectar_afiliados(origen_dir: Path) -> tuple[list[_AfiliadoValido], list[str]]:
    """Recorre `job_<origen>/lote_*/<doc_key>/*.pdf` y separa válidos de excluidos.

    El orden de fusión dentro de cada afiliado es alfabético por nombre de
    archivo: como cada archivo ya se llama `<modulo>_<fecha_iso>.pdf` o
    `<modulo>.pdf`, ese orden agrupa por módulo y, dentro del mismo módulo,
    cronológicamente — equivalente al orden (programa, carpeta, archivo) del
    script original, sin necesitar el nivel extra de "programa".

    Devuelve (afiliados_validos, doc_keys_excluidos_por_identificador).
    """
    afiliados: list[_AfiliadoValido] = []
    excluidos: list[str] = []
    for lote_dir in sorted(origen_dir.glob("lote_*")):
        if not lote_dir.is_dir():
            continue
        for persona_dir in sorted(p for p in lote_dir.iterdir() if p.is_dir()):
            pdfs = sorted(p for p in persona_dir.iterdir() if p.suffix.lower() == ".pdf")
            if not pdfs:
                continue
            doc_key = persona_dir.name
            partido = _partir_doc_key(doc_key)
            if partido is None:
                excluidos.append(doc_key)
                continue
            tipo, numero = partido
            afiliados.append(_AfiliadoValido(doc_key=doc_key, tipo=tipo, numero=numero, pdfs=pdfs))
    return afiliados, excluidos


def ejecutar_ajuste_soportes(job: Extraccion) -> None:
    """Job completo: lee el Soporte Unificado de origen, fusiona cada afiliado
    válido en un solo PDF renombrado, empaqueta por lotes. Nunca pierde un
    afiliado en silencio: todo lo excluido/fallido queda en `job.resumen_json`.
    """
    try:
        job.estado = EstadoExtraccion.RUNNING
        store.save(job)

        origen_dir = settings.data_dir / f"job_{job.origen_job_id}"
        if not origen_dir.exists():
            raise FileNotFoundError(
                f"No se encontraron los archivos del job de origen {job.origen_job_id}"
            )

        afiliados, excluidos_identificador = recolectar_afiliados(origen_dir)
        n = len(afiliados)
        job.total_afiliados = n

        def _resumen(generados, sin_pdf_por_error, pdfs_fuente_ok, pdfs_fuente_error, paginas_totales):
            return json.dumps({
                "generados": generados,
                "excluidos_identificador": len(excluidos_identificador),
                "excluidos_identificador_detalle": excluidos_identificador[:50],
                "sin_pdf_por_error": sin_pdf_por_error,
                "pdfs_fuente_ok": pdfs_fuente_ok,
                "pdfs_fuente_error": pdfs_fuente_error,
                "paginas_totales": paginas_totales,
            }, ensure_ascii=False)

        if n == 0:
            job.estado = EstadoExtraccion.COMPLETED
            job.completado_en = datetime.now()
            job.mensaje_error = "No se encontraron afiliados válidos para ajustar"
            job.resumen_json = _resumen(0, 0, 0, 0, 0)
            store.save(job)
            return

        factura = numero_de_facturas(job.facturas)
        regimen_dir = job.regimen or "SIN_REGIMEN"

        tamano = job.tamano_lote
        n_lotes = max(1, math.ceil(n / tamano))
        job.total_lotes = n_lotes
        store.save(job)

        planificados: list[tuple[Lote, list[_AfiliadoValido]]] = []
        for i in range(1, n_lotes + 1):
            offset = (i - 1) * tamano
            grupo = afiliados[offset:offset + tamano]
            lote = Lote(job_id=job.id, numero=i, offset_inicio=offset, tamano=max(1, len(grupo)))
            store.save_lote(lote)
            planificados.append((lote, grupo))

        _lock = threading.Lock()
        total_pdfs = 0
        pdfs_fuente_ok = 0
        pdfs_fuente_error = 0
        paginas_totales = 0
        sin_pdf_por_error = 0
        lotes_fallidos = 0
        cancelado = threading.Event()

        def _run_lote(lote: Lote, grupo: list[_AfiliadoValido]) -> None:
            nonlocal total_pdfs, pdfs_fuente_ok, pdfs_fuente_error, paginas_totales, sin_pdf_por_error, lotes_fallidos
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
            lote.fase = f"Fusionando PDFs ({len(grupo)} afiliados)…"
            store.save_lote(lote)
            try:
                lote_dir = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}"
                generados_lote = 0
                for af in grupo:
                    nombre = nombre_pdf_salida(factura, af.tipo, af.numero)
                    destino = lote_dir / regimen_dir / nombre
                    res = fusionar_pdfs(af.pdfs, destino)
                    with _lock:
                        pdfs_fuente_ok += res.pdfs_ok
                        pdfs_fuente_error += res.pdfs_error
                        paginas_totales += res.paginas
                        if res.pdfs_ok == 0:
                            sin_pdf_por_error += 1
                        else:
                            generados_lote += 1
                            total_pdfs += 1

                lote.total_pdfs = generados_lote
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
                    job.total_pdfs = total_pdfs
                    store.save(job)
            except Exception as e:  # noqa: BLE001
                log.exception("ajuste_soportes.lote_falló", extra={"lote": lote.numero})
                lote.estado = EstadoExtraccion.FAILED
                lote.mensaje_error = str(e)[:500]
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                with _lock:
                    lotes_fallidos += 1

        with ThreadPoolExecutor(max_workers=max(1, settings.lote_workers)) as ex:
            futs = [ex.submit(_run_lote, lote, grupo) for lote, grupo in planificados]
            for f in as_completed(futs):
                f.result()

        if cancelado.is_set():
            job.completado_en = datetime.now()
            job.mensaje_error = "Cancelado por el usuario"
            job.resumen_json = _resumen(total_pdfs, sin_pdf_por_error, pdfs_fuente_ok, pdfs_fuente_error, paginas_totales)
            store.save(job)
            return

        job.completado_en = datetime.now()
        job.resumen_json = _resumen(total_pdfs, sin_pdf_por_error, pdfs_fuente_ok, pdfs_fuente_error, paginas_totales)
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
            "ajuste_soportes.done",
            extra={"job": str(job.id), "generados": total_pdfs, "excluidos": len(excluidos_identificador)},
        )

    except Exception as e:  # noqa: BLE001
        log.exception("ajuste_soportes.failed")
        job.estado = EstadoExtraccion.FAILED
        job.mensaje_error = str(e)[:500]
        job.completado_en = datetime.now()
        store.save(job)
