"""JobStore — persistencia de extracciones, lotes y atenciones.

Las extracciones y lotes viven en SQLite (sobreviven a reinicios).
Las atenciones (datos crudos para la vista de detalle) viven en memoria
porque pueden ser muchas (hasta 1M) y solo se necesitan mientras el usuario
las consulta inmediatamente después de generar.
"""
import json
from datetime import date, datetime
from threading import Lock
from uuid import UUID

from efdi.domain.models import (
    Atencion,
    EstadoExtraccion,
    Extraccion,
    Lote,
    ModoPdf,
)
from efdi.infrastructure.db import db


def _row_to_extraccion(row) -> Extraccion:
    return Extraccion(
        id=UUID(row["id"]),
        desde=date.fromisoformat(row["desde"]),
        hasta=date.fromisoformat(row["hasta"]),
        limite=row["limite"],
        tamano_lote=row["tamano_lote"],
        total_lotes=row["total_lotes"],
        modo_pdf=ModoPdf(row["modo_pdf"]),
        estado=EstadoExtraccion(row["estado"]),
        total_atenciones=row["total_atenciones"],
        total_afiliados=row["total_afiliados"],
        total_pdfs=row["total_pdfs"],
        creado_en=datetime.fromisoformat(row["creado_en"]),
        completado_en=datetime.fromisoformat(row["completado_en"]) if row["completado_en"] else None,
        zip_path=row["zip_path"],
        mensaje_error=row["mensaje_error"],
    )


def _row_to_lote(row) -> Lote:
    return Lote(
        job_id=UUID(row["job_id"]),
        numero=row["numero"],
        offset_inicio=row["offset_inicio"],
        tamano=row["tamano"],
        estado=EstadoExtraccion(row["estado"]),
        total_atenciones=row["total_atenciones"],
        total_afiliados=row["total_afiliados"],
        total_pdfs=row["total_pdfs"],
        zip_path=row["zip_path"],
        iniciado_en=datetime.fromisoformat(row["iniciado_en"]) if row["iniciado_en"] else None,
        completado_en=datetime.fromisoformat(row["completado_en"]) if row["completado_en"] else None,
        mensaje_error=row["mensaje_error"],
    )


class JobStore:
    def __init__(self) -> None:
        self._atenciones: dict[UUID, list[Atencion]] = {}
        self._atenciones_lock = Lock()

    # ============================================================
    # EXTRACCIONES
    # ============================================================
    def save(self, job: Extraccion) -> None:
        """Guarda el job. Si el job en disco ya está CANCELLED, NO sobreescribe el estado.

        Esto evita race condition: el worker sigue corriendo lote y guardando métricas,
        pero el usuario pudo haber cancelado entre medio. CANCELLED es estado terminal
        respetado por el worker hasta que el check entre lotes lo detecte y aborte.
        """
        with db.transaction() as conn:
            existing = conn.execute(
                "SELECT estado FROM extracciones WHERE id = ?", (str(job.id),)
            ).fetchone()
            estado_a_guardar = job.estado.value if hasattr(job.estado, "value") else str(job.estado)
            # Si en disco está CANCELLED y vamos a sobreescribir con running/pending → mantener CANCELLED
            if existing and existing["estado"] == "cancelled" and estado_a_guardar in ("running", "pending"):
                estado_a_guardar = "cancelled"

            conn.execute(
                """
                INSERT INTO extracciones (
                    id, desde, hasta, limite, tamano_lote, total_lotes,
                    modo_pdf, estado, total_atenciones, total_afiliados, total_pdfs,
                    creado_en, completado_en, mensaje_error, zip_path
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    total_lotes=excluded.total_lotes,
                    estado=excluded.estado,
                    total_atenciones=excluded.total_atenciones,
                    total_afiliados=excluded.total_afiliados,
                    total_pdfs=excluded.total_pdfs,
                    completado_en=excluded.completado_en,
                    mensaje_error=excluded.mensaje_error,
                    zip_path=excluded.zip_path
                """,
                (
                    str(job.id), job.desde.isoformat(), job.hasta.isoformat(),
                    job.limite, job.tamano_lote, job.total_lotes,
                    job.modo_pdf.value if hasattr(job.modo_pdf, "value") else str(job.modo_pdf),
                    estado_a_guardar,
                    job.total_atenciones, job.total_afiliados, job.total_pdfs,
                    job.creado_en.isoformat(),
                    job.completado_en.isoformat() if job.completado_en else None,
                    job.mensaje_error, job.zip_path,
                ),
            )

    def get(self, job_id: UUID) -> Extraccion | None:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM extracciones WHERE id = ?", (str(job_id),)
            ).fetchone()
            return _row_to_extraccion(row) if row else None

    def list_all(self) -> list[Extraccion]:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM extracciones ORDER BY creado_en DESC"
            ).fetchall()
            return [_row_to_extraccion(r) for r in rows]

    def delete(self, job_id: UUID) -> bool:
        with db.transaction() as conn:
            cur = conn.execute("DELETE FROM extracciones WHERE id = ?", (str(job_id),))
            return cur.rowcount > 0

    # ============================================================
    # LOTES
    # ============================================================
    def save_lote(self, lote: Lote) -> None:
        with db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO lotes (
                    job_id, numero, offset_inicio, tamano, estado,
                    total_atenciones, total_afiliados, total_pdfs,
                    zip_path, iniciado_en, completado_en, mensaje_error
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(job_id, numero) DO UPDATE SET
                    estado=excluded.estado,
                    total_atenciones=excluded.total_atenciones,
                    total_afiliados=excluded.total_afiliados,
                    total_pdfs=excluded.total_pdfs,
                    zip_path=excluded.zip_path,
                    iniciado_en=excluded.iniciado_en,
                    completado_en=excluded.completado_en,
                    mensaje_error=excluded.mensaje_error
                """,
                (
                    str(lote.job_id), lote.numero, lote.offset_inicio, lote.tamano,
                    lote.estado.value if hasattr(lote.estado, "value") else str(lote.estado),
                    lote.total_atenciones, lote.total_afiliados, lote.total_pdfs,
                    lote.zip_path,
                    lote.iniciado_en.isoformat() if lote.iniciado_en else None,
                    lote.completado_en.isoformat() if lote.completado_en else None,
                    lote.mensaje_error,
                ),
            )

    def list_lotes(self, job_id: UUID) -> list[Lote]:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lotes WHERE job_id = ? ORDER BY numero ASC",
                (str(job_id),),
            ).fetchall()
            return [_row_to_lote(r) for r in rows]

    def get_lote(self, job_id: UUID, numero: int) -> Lote | None:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM lotes WHERE job_id = ? AND numero = ?",
                (str(job_id), numero),
            ).fetchone()
            return _row_to_lote(row) if row else None

    # ============================================================
    # ATENCIONES (en memoria, solo para vista de detalle reciente)
    # ============================================================
    def save_atenciones(self, job_id: UUID, atenciones: list[Atencion]) -> None:
        # Solo guardamos hasta 5000 para no explotar memoria con jobs grandes
        with self._atenciones_lock:
            self._atenciones[job_id] = atenciones[:5000]

    def get_atenciones(self, job_id: UUID) -> list[Atencion]:
        with self._atenciones_lock:
            return list(self._atenciones.get(job_id, []))


store = JobStore()
