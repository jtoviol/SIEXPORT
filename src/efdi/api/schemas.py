"""Schemas request/response de la API."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from efdi.domain.models import EstadoExtraccion, ExtraccionTipo, ModoPdf


class CrearExtraccionReq(BaseModel):
    desde: date = Field(description="Fecha inicial del rango (FEC_REGISTRO_INFORMACION)")
    hasta: date = Field(description="Fecha final del rango")
    limite: int | None = Field(default=None, ge=1, le=600_000, description="None=Auto: trae todos los registros del rango (máx 600K)")
    tamano_lote: int | None = Field(
        default=None, ge=1, le=50_000,
        description="None=Auto-calculado según el total de registros",
    )
    modo_pdf: ModoPdf = Field(default=ModoPdf.UNO_POR_ATENCION)
    # ── Cruce por factura (Fase 2 DI) ──
    numero_factura: str | None = Field(
        default=None,
        description="Sufijo numérico de la factura (ej: '11502'). El backend arma CAB{n}+FAB{n}.",
    )
    regimen: str | None = Field(
        default=None,
        description=(
            "SUBSIDIADO o CONTRIBUTIVO. En DI es obligatorio si viene numero_factura. "
            "En FINDRISC se acepta solo (sin numero_factura) y filtra por NRO_FACTURA LIKE CAB%/FAB%."
        ),
    )

    @model_validator(mode="after")
    def validar_rango(self) -> "CrearExtraccionReq":
        if self.hasta < self.desde:
            raise ValueError("hasta debe ser ≥ desde")
        return self

    @model_validator(mode="after")
    def validar_factura(self) -> "CrearExtraccionReq":
        # numero_factura SIEMPRE requiere regimen (DI Fase 2).
        # regimen sin numero_factura SÍ es válido (FINDRISC y otros módulos
        # que solo filtran por régimen vía AVS_REGISTROS_AP, sin sufijo).
        if self.numero_factura is not None and self.regimen is None:
            raise ValueError("numero_factura requiere regimen")
        if self.regimen is not None:
            r = self.regimen.strip().upper()
            if r not in ("SUBSIDIADO", "CONTRIBUTIVO"):
                raise ValueError("regimen debe ser SUBSIDIADO o CONTRIBUTIVO")
            self.regimen = r
        if self.numero_factura is not None:
            n = self.numero_factura.strip().upper()
            # Si el usuario pegó "CAB11502" o "FAB11502" → quedarse con el sufijo
            if n.startswith("CAB") or n.startswith("FAB"):
                n = n[3:]
            if not n:
                raise ValueError("numero_factura no puede ser vacío")
            self.numero_factura = n
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"desde": "2026-04-01", "hasta": "2026-05-28", "limite": 25, "tamano_lote": 25},
                {"desde": "2026-01-01", "hasta": "2026-06-30", "limite": 400_000, "tamano_lote": 10_000},
            ]
        }
    }


class ExtraccionResp(BaseModel):
    id: UUID
    desde: date
    hasta: date
    limite: int
    tamano_lote: int
    total_lotes: int
    tipo: ExtraccionTipo
    modo_pdf: ModoPdf
    nombre: str | None = None
    regimen: str | None = None
    facturas: list[str] | None = None
    estado: EstadoExtraccion
    total_atenciones: int
    total_afiliados: int
    total_pdfs: int
    creado_en: datetime
    completado_en: datetime | None = None
    mensaje_error: str | None = None


class RenombrarJobReq(BaseModel):
    nombre: str = Field(default="", max_length=100, strip_whitespace=True)


class ConteoFacturaItem(BaseModel):
    total_filas: int
    documentos_unicos: int


class ConteoFacturasResp(BaseModel):
    """Resumen de conteo para uno o varios códigos de factura."""

    total_filas: int = Field(description="COUNT(*) global sobre la lista de códigos")
    documentos_unicos: int = Field(description="COUNT(DISTINCT num_tipo_identificacion) global")
    por_codigo: dict[str, ConteoFacturaItem] = Field(
        description="Desglose por código de factura, incluyendo los que dieron cero",
    )


class HealthResp(BaseModel):
    status: str = "ok"
    version: str
    modo: str


class DiagCheck(BaseModel):
    """Resultado de un check de diagnóstico."""

    ok: bool
    descripcion: str
    detalle: str | None = None


class DiagnosticsResp(BaseModel):
    status: str  # "ok" | "warning" | "error"
    version: str
    modo: str
    checks: dict[str, DiagCheck]
    metricas: dict[str, int]
    advertencias: list[str] = []
