"""Modelos de dominio — contrato de datos que el SQL debe respetar."""
from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TipoDocumento(str, Enum):
    CC = "CC"
    TI = "TI"
    MS = "MS"
    RC = "RC"
    CE = "CE"
    PA = "PA"


class Sexo(str, Enum):
    M = "M"
    F = "F"


class Regimen(str, Enum):
    CONTRIBUTIVO = "CONTRIBUTIVO"
    SUBSIDIADO = "SUBSIDIADO"
    VINCULADO = "VINCULADO"


class ModoIngreso(str, Enum):
    COMUNIDAD = "COMUNIDAD"
    TELEFONICO = "TELEFONICO"
    VIRTUAL = "VIRTUAL"


class Atencion(BaseModel):
    """Una fila del SELECT de la query — equivale a una demanda inducida."""

    model_config = ConfigDict(use_enum_values=True, str_strip_whitespace=True)

    # === IDENTIFICACIÓN AFILIADO ===
    seq_seragil: int = Field(description="SEQ_SERAGIL — id único de la atención")
    consecutivo: int = Field(description="NUM_REGISTRO — número correlativo en el resultado")
    tipo_documento: TipoDocumento = Field(description="COD_TIPO_IDENTIFICACION")
    num_documento: str = Field(description="NRO_TIPO_IDENTIFICACION")
    primer_nombre: str = Field(description="AFL_PRIMER_NOMBRE")
    segundo_nombre: str | None = Field(default=None, description="AFL_SEGUNDO_NOMBRE")
    primer_apellido: str = Field(description="AFL_PRIMER_APELLIDO")
    segundo_apellido: str | None = Field(default=None, description="AFL_SEGUNDO_APELLIDO")
    sexo: Sexo = Field(description="DES_GENERO normalizado a M/F")
    edad: int = Field(ge=0, le=120, description="VLR_EDAD_ACTUAL")
    fecha_nacimiento: date = Field(description="FEC_NACIMIENTO_PERSONA")
    direccion: str | None = Field(default=None, description="DES_DIRECCION_ACTUAL")
    telefono_1: str | None = Field(default=None, description="DES_TELEFONO_UNO")
    telefono_2: str | None = Field(default=None, description="DES_TELEFONO_DOS")
    correo: str | None = Field(default=None, description="DES_CORREO_ELECTRONICO")
    departamento: str | None = Field(default=None, description="DES_DEPARTAMENTO")
    municipio: str | None = Field(default=None, description="DES_MUNICIPIO")
    curso_vida: str | None = Field(default=None, description="DES_CURSO_VIDA_ASOCIADO")
    regimen: Regimen | None = Field(default=None, description="REGIMEN")

    # === ATENCIÓN ===
    fecha_registro: date = Field(description="FEC_REGISTRO_INFORMACION")
    fecha_atencion: date | None = Field(default=None, description="FEC_REAL_EJECUCION")
    cod_programa: str = Field(description="COD_PROGRAMA_DEMIND (ej: '41')")
    des_programa: str = Field(description="DES_PROGRAMA_DEMIND")
    ips_remite: str | None = Field(default=None, description="DES_PRESTADOR_SERVICIOS")
    ips_atiende: str | None = Field(default=None, description="DES_PRESTADOR_EJECUCION")
    modo_ingreso: ModoIngreso | None = Field(default=None, description="FLG_MODO_INGRESO")

    # === REMITENTE ===
    cod_remitente: str | None = Field(default=None, description="COD_TIPO_REMITENTE_INICIAL")
    des_remitente: str | None = Field(default=None, description="DES_REMITENTE_INICIAL")
    des_otro_remitente: str | None = Field(default=None, description="DES_OTRO_REMITENTE_INICIAL")

    # === ENCUESTADOR ===
    encuestador_nombre: str | None = Field(default=None, description="ENCUESTADOR (nombre completo)")
    cargo_encuestador: str | None = Field(default=None, description="DES_CARGO_USUARIO")

    # === RIAS ===
    rias_grupo_riesgo: str | None = Field(default=None, description="DES_RIAS_GRUPO_RIESGO")
    otra_rias: str | None = Field(default=None, description="DES_OTRA_RIAS_GRUPO_RIESGO")

    # === FLAGS ===
    notificacion_obligatoria: bool = Field(default=False)
    recuperacion_urgencias: bool = Field(default=False)
    recuperacion_consulta_externa: bool = Field(default=False)

    @property
    def doc_key(self) -> str:
        """Llave única del afiliado para agrupar — usada como nombre de carpeta."""
        return f"{self.tipo_documento}_{self.num_documento}"


class AfiliadoConAtenciones(BaseModel):
    """Agrupación: un afiliado + fecha de registro con sus N atenciones de ese día."""

    doc_key: str
    tipo_documento: TipoDocumento
    num_documento: str
    nombre_completo: str
    fecha_registro: date
    atenciones: list[Atencion]

    @property
    def total_atenciones(self) -> int:
        return len(self.atenciones)

    @property
    def pdf_key(self) -> str:
        """Nombre del PDF: tipo_documento_numero_fecha."""
        return f"{self.doc_key}_{self.fecha_registro}"


class EstadoExtraccion(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Etiquetas en español para mensajes al usuario
ESTADO_LABEL: dict[str, str] = {
    "pending":   "Pendiente",
    "running":   "En curso",
    "completed": "Completado",
    "failed":    "Fallido",
    "cancelled": "Cancelado",
}


def estado_label(estado: "EstadoExtraccion | str") -> str:
    """Devuelve el texto en español de un EstadoExtraccion."""
    v = estado.value if hasattr(estado, "value") else str(estado)
    return ESTADO_LABEL.get(v, v)


def safe_filename(nombre: str | None, fallback: str) -> str:
    """Sanitiza un nombre custom para usarlo como nombre de archivo.

    - Reemplaza caracteres inválidos para filesystem (/, \\, :, *, ?, ", <, >, |) por _.
    - Colapsa espacios y guiones bajos múltiples.
    - Limita a 80 caracteres.
    - Si el nombre queda vacío o no se pasó, devuelve `fallback`.
    """
    import re
    if not nombre or not str(nombre).strip():
        return fallback
    s = str(nombre).strip()
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("._-")
    s = s[:80].rstrip("._-")
    return s or fallback


class ExtraccionTipo(str, Enum):
    DEMANDA_INDUCIDA = "demanda_inducida"
    FINDRISC = "findrisc"
    GESTION_CAPTACION = "gestion_captacion"
    PLANIFICACION_FAMILIAR = "planificacion_familiar"


# ─── Factores Clínicos del módulo Seguimiento Planificación Familiar ────────
# 13 banderas FIC (Factores de Inclusión Clínica). La SQL las devuelve tal cual
# vienen de la BD; cualquier valor no vacío se considera "marcado".
PLANFAMI_FACTORES_CLINICOS: list[tuple[str, str]] = [
    ("fic_dtc_dm",       "Diabetes Mellitus"),
    ("fic_dtc_hta",      "Hipertensión Arterial"),
    ("fic_artritis",     "Artritis"),
    ("fic_cancer",       "Cáncer"),
    ("fic_epilepsia",    "Epilepsia"),
    ("fic_epoc",         "EPOC"),
    ("fic_hemofilia",    "Hemofilia"),
    ("fic_huerfanas",    "Enfermedades huérfanas"),
    ("fic_renal",        "Enfermedad renal"),
    ("fic_salud_mental", "Salud mental"),
    ("fic_trasplante",   "Trasplante"),
    ("fic_victimas",     "Víctimas"),
    ("fic_vih",          "VIH"),
]


# ─── Programas/banderas del módulo Gestión Captación ────────────────────────
# Orden canónico para el grid del PDF. La SQL devuelve cada uno con "SI" o vacío.
CAPTACION_PROGRAMAS: list[tuple[str, str]] = [
    ("flg_gestantes",     "Gestantes"),
    ("flg_hta",           "HTA"),
    ("flg_mujer_sana",    "Mujer sana"),
    ("flg_ser_joven",     "Ser joven"),
    ("flg_salud_mental",  "Salud mental"),
    ("flg_victimas",      "Víctimas"),
    ("flg_epoc",          "EPOC"),
    ("flg_amarte",        "Amarte"),
    ("flg_renal",         "Renal"),
    ("flg_vih",           "VIH"),
    ("flg_hemofilia",     "Hemofilia"),
    ("flg_salud_sexual",  "Salud sexual"),
    ("flg_cancer",        "Cáncer"),
    ("flg_tuberculosis",  "Tuberculosis"),
    ("flg_lepra",         "Lepra"),
    ("flg_epilepsia",     "Epilepsia"),
    ("flg_huerfanas",     "Enfermedades huérfanas"),
    ("flg_desnutricion",  "Desnutrición"),
    ("flg_obesidad",      "Obesidad"),
]


class RegistroFindrisc(BaseModel):
    """Una fila del reporte FINDRISC — 20 campos del reporte + metadata interna."""

    model_config = ConfigDict(use_enum_values=True, str_strip_whitespace=True)

    # ── Metadata interna (no va al reporte; usada para agrupar/nombrar archivos) ──
    seq_seragil: int
    tipo_documento: TipoDocumento
    fecha_registro: date

    # ── 20 columnas del reporte ───────────────────────────────────────────────
    nombre_completo: str
    sexo: str | None = None
    edad: int = Field(default=0, ge=0, le=120)
    municipio: str | None = None
    ips: str | None = None
    tipo_identificacion_desc: str | None = None       # "CEDULA DE CIUDADANIA"
    num_documento: str
    telefono_1: str | None = None
    telefono_2: str | None = None
    correo: str | None = None
    # Valores antropométricos como string literal de la BD (sin parseo)
    peso: str | None = None
    talla: str | None = None
    imc: str | None = None
    perimetro_cintura: str | None = None
    actividad_fisica: bool = False
    frecuencia_verduras: str | None = None            # "TODOS LOS DIAS" / "NO TODOS LOS DIAS"
    medicamentos_hipertension: bool = False
    glucosa_alta: bool = False
    antecedente_diabetes: str | None = None           # texto decodificado
    puntaje_total: int = 0

    @property
    def doc_key(self) -> str:
        return f"{self.tipo_documento}_{self.num_documento}"


class AfiliadoConFindrisc(BaseModel):
    """Un afiliado con sus registros FINDRISC agrupados por fecha."""

    doc_key: str
    tipo_documento: TipoDocumento
    num_documento: str
    nombre_completo: str
    fecha_registro: date
    registros: list[RegistroFindrisc]

    @property
    def pdf_key(self) -> str:
        return f"{self.doc_key}_{self.fecha_registro}"


class RegistroCaptacion(BaseModel):
    """Una fila del reporte Gestión Captación Afiliados.

    Política: todos los campos se almacenan tal cual vienen de la BD (string literal),
    salvo la fecha de captación que se parsea para poder agrupar/nombrar archivos.
    """

    model_config = ConfigDict(use_enum_values=True, str_strip_whitespace=True)

    # ── Metadata interna (no va al reporte; usada para agrupar/nombrar archivos) ──
    seq_captacion_afiliado: int
    tipo_documento: TipoDocumento
    fecha_captacion: date

    # ── Identificación ──────────────────────────────────────────────────────
    tipo_identificacion_desc: str | None = None
    num_documento: str
    nombre_completo: str
    genero: str | None = None
    fec_nacimiento: str | None = None                  # literal de BD ("YYYY-MM-DD" o "")
    edad: str | None = None                             # literal de BD ("23 AÑOS", "6 MESES", "15 DIAS")

    # ── Captación ──────────────────────────────────────────────────────────
    funcionario: str | None = None
    fecha_captacion_str: str | None = None              # literal de BD para mostrar tal cual
    estado: str | None = None
    fuente_captacion: str | None = None

    # ── Ubicación / Contacto ───────────────────────────────────────────────
    regional: str | None = None
    departamento: str | None = None
    municipio: str | None = None
    direccion: str | None = None
    telefono_celular: str | None = None
    telefono_fijo: str | None = None
    telefono_familiar: str | None = None
    correo: str | None = None
    prestador_servicios: str | None = None

    # ── 19 banderas de programas (vienen como "SI" o cadena vacía) ─────────
    flg_gestantes: str | None = None
    flg_hta: str | None = None
    flg_mujer_sana: str | None = None
    flg_ser_joven: str | None = None
    flg_salud_mental: str | None = None
    flg_victimas: str | None = None
    flg_epoc: str | None = None
    flg_amarte: str | None = None
    flg_renal: str | None = None
    flg_vih: str | None = None
    flg_hemofilia: str | None = None
    flg_salud_sexual: str | None = None
    flg_cancer: str | None = None
    flg_tuberculosis: str | None = None
    flg_lepra: str | None = None
    flg_epilepsia: str | None = None
    flg_huerfanas: str | None = None
    flg_desnutricion: str | None = None
    flg_obesidad: str | None = None

    @property
    def doc_key(self) -> str:
        return f"{self.tipo_documento}_{self.num_documento}"

    def flag_marcado(self, attr: str) -> bool:
        """True solo si la BD trae exactamente 'SI' (case-insensitive, trim)."""
        v = getattr(self, attr, None) or ""
        return v.strip().upper() == "SI"


class AfiliadoConCaptacion(BaseModel):
    """Un afiliado con sus registros de Captación agrupados por fecha."""

    doc_key: str
    tipo_documento: TipoDocumento
    num_documento: str
    nombre_completo: str
    fecha_captacion: date
    registros: list[RegistroCaptacion]

    @property
    def pdf_key(self) -> str:
        return f"{self.doc_key}_{self.fecha_captacion}"


class RegistroPlanFamiliar(BaseModel):
    """Una fila del reporte Seguimiento Planificación Familiar.

    Política: campos literales de la BD. Solo `fecha_gestion` se parsea para
    agrupar/nombrar archivos.
    """

    model_config = ConfigDict(use_enum_values=True, str_strip_whitespace=True)

    # ── Metadata interna ──────────────────────────────────────────────────
    seq_poblacion_riesgo: int
    tipo_documento: TipoDocumento
    fecha_gestion: date            # fec_gestion_seguimiento parseada

    # ── Ubicación ─────────────────────────────────────────────────────────
    regional: str | None = None
    municipio: str | None = None
    departamento: str | None = None

    # ── Período / Población ───────────────────────────────────────────────
    anio: str | None = None
    trimestre: str | None = None
    tipo_poblacion: str | None = None    # ADOLESCENTE / MULTIPARA / COHORTE DE RIESGO / SIN DEFINIR

    # ── Encuestador ───────────────────────────────────────────────────────
    encuestador: str | None = None
    fecha_gestion_str: str | None = None    # literal de BD

    # ── Identificación afiliada ───────────────────────────────────────────
    tipo_identificacion_desc: str | None = None
    num_documento: str
    nombre_completo: str
    fecha_nacimiento: str | None = None     # literal de BD
    edad: str | None = None                  # literal de BD (puede ser cadena con espacios)
    telefono: str | None = None
    regimen: str | None = None

    # ── Planificación actual ──────────────────────────────────────────────
    flg_planifica: str | None = None
    motivo_no_planifica: str | None = None
    flg_desea_utilizar_metodo: str | None = None
    metodo_anticonceptivo: str | None = None
    fec_inicio_planfami: str | None = None
    flg_inicio_preconcepcional: str | None = None
    metodo_planificacion: str | None = None   # des_metodo_planificacion

    # ── Eventos obstétricos / planificación previa ────────────────────────
    nro_eventos_obstetricos: str | None = None
    flg_fuente_evento_obstetrico: str | None = None
    fec_evento_planificacion: str | None = None
    cod_producto_ev_planificacion: str | None = None
    nom_producto_ev_planificacion: str | None = None
    fec_planificacion_202: str | None = None
    var_planificacion_202: str | None = None
    fec_planificacion_temporal: str | None = None
    cod_fuente_planificacion_temporal: str | None = None
    des_metodo_planificacion_temporal: str | None = None

    # ── 13 banderas FIC (cualquier valor no vacío = marcado) ──────────────
    fic_dtc_dm: str | None = None
    fic_dtc_hta: str | None = None
    fic_artritis: str | None = None
    fic_cancer: str | None = None
    fic_epilepsia: str | None = None
    fic_epoc: str | None = None
    fic_hemofilia: str | None = None
    fic_huerfanas: str | None = None
    fic_renal: str | None = None
    fic_salud_mental: str | None = None
    fic_trasplante: str | None = None
    fic_victimas: str | None = None
    fic_vih: str | None = None

    # ── Estado y seguimiento ──────────────────────────────────────────────
    estado: str | None = None                       # NO INTERVENIDA / PENDIENTE / CERRADA
    tipo_seguimiento: str | None = None             # TELEFONICO / DOMICILIARIO
    flg_contactada: str | None = None
    flg_visita_domiciliaria: str | None = None
    flg_cierra_seguimiento: str | None = None
    motivo_nocontacto: str | None = None
    observaciones: str | None = None

    @property
    def doc_key(self) -> str:
        return f"{self.tipo_documento}_{self.num_documento}"

    def factor_marcado(self, attr: str) -> bool:
        """True si el campo FIC trae cualquier valor no vacío de la BD."""
        v = getattr(self, attr, None) or ""
        return bool(v.strip())


class AfiliadoConPlanFamiliar(BaseModel):
    """Un afiliado con sus registros de PlanFami agrupados por fecha de gestión."""

    doc_key: str
    tipo_documento: TipoDocumento
    num_documento: str
    nombre_completo: str
    fecha_gestion: date
    registros: list[RegistroPlanFamiliar]

    @property
    def pdf_key(self) -> str:
        return f"{self.doc_key}_{self.fecha_gestion}"


class ModoPdf(str, Enum):
    UNO_POR_ATENCION = "uno_por_atencion"


class Lote(BaseModel):
    """Un lote dentro de una extracción — chunk procesable de N registros."""

    job_id: UUID
    numero: int = Field(ge=1, description="Índice 1-based del lote dentro de la extracción")
    offset_inicio: int = Field(ge=0)
    tamano: int = Field(ge=1)
    estado: EstadoExtraccion = EstadoExtraccion.PENDING
    fase: str = ""
    total_atenciones: int = 0
    total_afiliados: int = 0
    total_pdfs: int = 0
    zip_path: str | None = None
    iniciado_en: datetime | None = None
    completado_en: datetime | None = None
    mensaje_error: str | None = None


class Extraccion(BaseModel):
    """Job de generación de PDFs."""

    id: UUID
    desde: date
    hasta: date
    limite: int = Field(ge=1, le=600_000, description="Total de registros a generar (sumando lotes)")
    tamano_lote: int = Field(default=10_000, ge=1, le=50_000, description="Registros por lote")
    total_lotes: int = 0
    tipo: ExtraccionTipo = ExtraccionTipo.DEMANDA_INDUCIDA
    modo_pdf: ModoPdf = ModoPdf.UNO_POR_ATENCION
    nombre: str | None = None
    estado: EstadoExtraccion = EstadoExtraccion.PENDING
    total_atenciones: int = 0
    total_afiliados: int = 0
    total_pdfs: int = 0
    creado_en: datetime
    completado_en: datetime | None = None
    zip_path: str | None = None
    mensaje_error: str | None = None
