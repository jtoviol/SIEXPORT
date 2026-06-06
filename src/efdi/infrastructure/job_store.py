"""JobStore — persistencia de extracciones, lotes y atenciones."""
from datetime import date, datetime
from threading import Lock
from uuid import UUID

from efdi.domain.models import (
    Atencion,
    EstadoExtraccion,
    Extraccion,
    ExtraccionTipo,
    Lote,
    ModoPdf,
)
from efdi.infrastructure.db import db


def _row_to_extraccion(row) -> Extraccion:
    cols = row.keys()
    tipo_raw = row["tipo"] if "tipo" in cols else "demanda_inducida"
    try:
        tipo = ExtraccionTipo(tipo_raw)
    except ValueError:
        tipo = ExtraccionTipo.DEMANDA_INDUCIDA
    regimen = row["regimen"] if "regimen" in cols else None
    facturas_raw = row["facturas"] if "facturas" in cols else None
    facturas = [c for c in (facturas_raw or "").split(",") if c.strip()] or None
    return Extraccion(
        id=UUID(row["id"]),
        desde=date.fromisoformat(row["desde"]),
        hasta=date.fromisoformat(row["hasta"]),
        limite=row["limite"],
        tamano_lote=row["tamano_lote"],
        total_lotes=row["total_lotes"],
        tipo=tipo,
        modo_pdf=ModoPdf(row["modo_pdf"]),
        nombre=row["nombre"] if "nombre" in cols else None,
        regimen=regimen,
        facturas=facturas,
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
    cols = row.keys()
    fase = row["fase"] if "fase" in cols else ""
    return Lote(
        job_id=UUID(row["job_id"]),
        numero=row["numero"],
        offset_inicio=row["offset_inicio"],
        tamano=row["tamano"],
        estado=EstadoExtraccion(row["estado"]),
        fase=fase,
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
        """Guarda el job preservando el estado CANCELLED si ya existe en disco."""
        with db.transaction() as conn:
            existing = conn.execute(
                "SELECT estado FROM extracciones WHERE id = ?", (str(job.id),)
            ).fetchone()
            estado_a_guardar = job.estado.value if hasattr(job.estado, "value") else str(job.estado)
            if existing and existing["estado"] == "cancelled" and estado_a_guardar in ("running", "pending"):
                estado_a_guardar = "cancelled"

            tipo_val = job.tipo.value if hasattr(job.tipo, "value") else str(job.tipo)

            facturas_csv = ",".join(job.facturas) if job.facturas else None
            conn.execute(
                """
                INSERT INTO extracciones (
                    id, desde, hasta, limite, tamano_lote, total_lotes,
                    tipo, modo_pdf, nombre, regimen, facturas, estado,
                    total_atenciones, total_afiliados, total_pdfs,
                    creado_en, completado_en, mensaje_error, zip_path
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    total_lotes=excluded.total_lotes,
                    tipo=excluded.tipo,
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
                    tipo_val,
                    job.modo_pdf.value if hasattr(job.modo_pdf, "value") else str(job.modo_pdf),
                    job.nombre,
                    job.regimen,
                    facturas_csv,
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

    def list_by_tipo(self, tipo: ExtraccionTipo) -> list[Extraccion]:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM extracciones WHERE tipo = ? ORDER BY creado_en DESC",
                (tipo.value,),
            ).fetchall()
            return [_row_to_extraccion(r) for r in rows]

    def rename(self, job_id: UUID, nombre: str | None) -> bool:
        with db.transaction() as conn:
            cur = conn.execute(
                "UPDATE extracciones SET nombre = ? WHERE id = ?",
                (nombre or None, str(job_id)),
            )
            return cur.rowcount > 0

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
                    job_id, numero, offset_inicio, tamano, estado, fase,
                    total_atenciones, total_afiliados, total_pdfs,
                    zip_path, iniciado_en, completado_en, mensaje_error
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(job_id, numero) DO UPDATE SET
                    estado=excluded.estado,
                    fase=excluded.fase,
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
                    lote.fase,
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
        with self._atenciones_lock:
            self._atenciones[job_id] = atenciones[:5000]

    def get_atenciones(self, job_id: UUID) -> list[Atencion]:
        with self._atenciones_lock:
            return list(self._atenciones.get(job_id, []))


store = JobStore()
