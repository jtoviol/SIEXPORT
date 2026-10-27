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


def _a_date(v) -> date:
    """SQL Server devuelve DATE como `date`; se acepta texto ISO por robustez."""
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _a_datetime(v) -> datetime | None:
    if v is None:
        return None
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


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
        desde=_a_date(row["desde"]),
        hasta=_a_date(row["hasta"]),
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
        creado_en=_a_datetime(row["creado_en"]),
        completado_en=_a_datetime(row["completado_en"]),
        zip_path=row["zip_path"],
        mensaje_error=row["mensaje_error"],
        created_by_username=row["created_by_username"] if "created_by_username" in cols else None,
        origen_job_id=UUID(row["origen_job_id"]) if ("origen_job_id" in cols and row["origen_job_id"]) else None,
        resumen_json=row["resumen_json"] if "resumen_json" in cols else None,
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
        iniciado_en=_a_datetime(row["iniciado_en"]),
        completado_en=_a_datetime(row["completado_en"]),
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
            # UPDLOCK+HOLDLOCK: bloquea la fila (o el hueco si no existe) hasta el
            # COMMIT, así el "leer estado → decidir → escribir" es atómico también
            # entre procesos (el `cancel` de un request vs. el hilo del job).
            existing = conn.execute(
                "SELECT estado FROM extracciones WITH (UPDLOCK, HOLDLOCK) WHERE id = ?", (str(job.id),)
            ).fetchone()
            estado_a_guardar = job.estado.value if hasattr(job.estado, "value") else str(job.estado)
            if existing and existing["estado"] == "cancelled" and estado_a_guardar in ("running", "pending"):
                estado_a_guardar = "cancelled"

            tipo_val = job.tipo.value if hasattr(job.tipo, "value") else str(job.tipo)

            facturas_csv = ",".join(job.facturas) if job.facturas else None
            if existing:
                conn.execute(
                    """
                    UPDATE extracciones SET
                        total_lotes=?, tipo=?, estado=?,
                        total_atenciones=?, total_afiliados=?, total_pdfs=?,
                        completado_en=?, mensaje_error=?, zip_path=?, resumen_json=?
                    WHERE id=?
                    """,
                    (
                        job.total_lotes, tipo_val, estado_a_guardar,
                        job.total_atenciones, job.total_afiliados, job.total_pdfs,
                        job.completado_en, job.mensaje_error, job.zip_path, job.resumen_json,
                        str(job.id),
                    ),
                )
                return
            conn.execute(
                """
                INSERT INTO extracciones (
                    id, desde, hasta, limite, tamano_lote, total_lotes,
                    tipo, modo_pdf, nombre, regimen, facturas, estado,
                    total_atenciones, total_afiliados, total_pdfs,
                    creado_en, completado_en, mensaje_error, zip_path,
                    created_by_username, origen_job_id, resumen_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(job.id), job.desde, job.hasta,
                    job.limite, job.tamano_lote, job.total_lotes,
                    tipo_val,
                    job.modo_pdf.value if hasattr(job.modo_pdf, "value") else str(job.modo_pdf),
                    job.nombre,
                    job.regimen,
                    facturas_csv,
                    estado_a_guardar,
                    job.total_atenciones, job.total_afiliados, job.total_pdfs,
                    job.creado_en,
                    job.completado_en,
                    job.mensaje_error, job.zip_path,
                    job.created_by_username,
                    str(job.origen_job_id) if job.origen_job_id else None,
                    job.resumen_json,
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

    def list_by_tipos(self, tipos: list[ExtraccionTipo]) -> list[Extraccion]:
        """Como `list_by_tipo` pero aceptando varios tipos relacionados — usado
        por Soporte Unificado para listar, en la misma consulta, también los
        jobs de Ajuste de Soportes que se originan de él."""
        if not tipos:
            return []
        placeholders = ",".join("?" * len(tipos))
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM extracciones WHERE tipo IN ({placeholders}) ORDER BY creado_en DESC",
                tuple(t.value for t in tipos),
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
        estado_val = lote.estado.value if hasattr(lote.estado, "value") else str(lote.estado)
        with db.transaction() as conn:
            existing = conn.execute(
                "SELECT 1 AS hay FROM lotes WITH (UPDLOCK, HOLDLOCK) WHERE job_id = ? AND numero = ?",
                (str(lote.job_id), lote.numero),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE lotes SET
                        estado=?, fase=?,
                        total_atenciones=?, total_afiliados=?, total_pdfs=?,
                        zip_path=?, iniciado_en=?, completado_en=?, mensaje_error=?
                    WHERE job_id=? AND numero=?
                    """,
                    (
                        estado_val, lote.fase,
                        lote.total_atenciones, lote.total_afiliados, lote.total_pdfs,
                        lote.zip_path, lote.iniciado_en, lote.completado_en, lote.mensaje_error,
                        str(lote.job_id), lote.numero,
                    ),
                )
                return
            conn.execute(
                """
                INSERT INTO lotes (
                    job_id, numero, offset_inicio, tamano, estado, fase,
                    total_atenciones, total_afiliados, total_pdfs,
                    zip_path, iniciado_en, completado_en, mensaje_error
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(lote.job_id), lote.numero, lote.offset_inicio, lote.tamano,
                    estado_val,
                    lote.fase,
                    lote.total_atenciones, lote.total_afiliados, lote.total_pdfs,
                    lote.zip_path,
                    lote.iniciado_en,
                    lote.completado_en,
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
