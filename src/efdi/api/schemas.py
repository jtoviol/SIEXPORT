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

    @model_validator(mode="after")
    def validar_rango(self) -> "CrearExtraccionReq":
        if self.hasta < self.desde:
            raise ValueError("hasta debe ser ≥ desde")
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
    estado: EstadoExtraccion
    total_atenciones: int
    total_afiliados: int
    total_pdfs: int
    creado_en: datetime
    completado_en: datetime | None = None
    mensaje_error: str | None = None


class RenombrarJobReq(BaseModel):
    nombre: str = Field(default="", max_length=100, strip_whitespace=True)


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
