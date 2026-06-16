"""Repositorio Caracterización Familiar.

Origen: base sibacom (servidor propio, ver DB_*_SIBACOM en .env).
Tablas: SBW_PERSONA_CARACTERIZADA + SBW_UBICACION_FAMILIA + SBW_OCUPACION
        + tabla_institucion.
Filtro único: rango de fecha_reg. Sin factura, sin régimen.
Política de fidelidad total: la query del usuario tal cual — cada campo se
guarda como string literal, sin parseo ni decodificación.
"""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import RegistroCaracterizacion

log = logging.getLogger(__name__)


class CaracterizacionRepository(Protocol):
    """`limite` y `offset` se expresan en FAMILIAS (no en filas-persona)."""

    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
    ) -> list[RegistroCaracterizacion]: ...

    def get_total(self, desde: date, hasta: date) -> int: ...


# === Query principal paginada POR FAMILIA =====================================
# Paginación por FAMILIA (DENSE_RANK sobre la jerarquía completa): cada lote
# trae familias COMPLETAS — una familia nunca queda partida entre dos lotes.
# `limite` y `offset` se expresan en familias.
#
# Política de fidelidad legible:
#   - Códigos crudos (parentes, programas, etnia, discap, codniv1/2, codniv3,
#     tipousua, ocupacio, tipofami) se resuelven a su DESCRIPCIÓN vía LEFT JOIN
#     a los catálogos correspondientes — con COALESCE al código por si la BD
#     trae un valor no catalogado.
#   - Teléfonos con '-1' o vacíos se normalizan a 'N/A' en el SQL.
#   - Correo vacío también 'N/A'.
# `_parentes_cod` se expone solo para ordenar dentro de cada familia (JEFE
# DE FAMILIA primero, después cónyuge, hijos, etc.); no llega al modelo.
QUERY_CARACTERIZACION = """
WITH X AS (
    SELECT
        DENSE_RANK() OVER (
            ORDER BY PC.[codniv1], PC.[codniv2], PC.[codniv3], PC.[codniv4],
                     PC.[codniv5], PC.[codniv6], PC.[codvivi], PC.[codfami],
                     PC.ciuf
        ) AS FAM_NUM,
        PC.parentes AS _parentes_cod,
        --AREA GEOGRAFICA con descripciones
        COALESCE(D.DES_DEPARTAMENTO, PC.codniv1)               AS departamento,
        COALESCE(M.DES_MUNICIPIO, PC.codniv1 + PC.codniv2)     AS municipio,
        CASE PC.codniv3 WHEN 'U' THEN 'URBANA'
                        WHEN 'R' THEN 'RURAL'
                        ELSE PC.codniv3 END                    AS area,
        PC.codniv4 AS corregimiento,
        PC.codniv5 AS barrio_vereda,
        PC.codniv6 AS manzana,
        PC.codvivi AS vivienda,
        PC.codfami AS familia,
        COALESCE(TF.DES_TIPO_FAMILIA, '')                      AS tipo_familia,
        PC.ciuf AS ciuf,
        PC.tipodocu  AS tipo_documento,
        PC.numdocu   AS num_documento,
        CONCAT(PC.primer_nombre,' ',PC.segundo_nombre,' ',
               PC.primer_apellido,' ',PC.segundo_apellido)     AS nombres_apellidos,
        PC.sexo      AS sexo,
        PC.fechanac  AS fecha_nacimiento,
        PC.edad      AS edad,
        PC.edaduni   AS unidades,
        COALESCE(P.parentesco, PC.parentes)                    AS parentesco,
        PC.estudia   AS estudia,
        PC.grado     AS anos_aprobados,
        COALESCE(OI.DES_OCUPACION_INGRESO, PC.ocupacio)        AS nombre_ocupacion,
        R.DES_TIPO_REGIMEN                                     AS descripcion_regimen,
        I.desc_ins                                             AS nombre_institucion,
        COALESCE(E.etnia, PC.etnia)                            AS etnia,
        PC.gae       AS gae,
        COALESCE(PG.nombre, PC.programas)                      AS programa,
        COALESCE(TD.DES_TIPO_DISCAPACIDAD, PC.discap)          AS discapacidad,
        UF.fecha_reg AS fecha_registro,
        CONCAT(UF.LAT_GRA,' ',UF.LAT_MIN,' ',UF.LAT_SEN)       AS latitud,
        CONCAT(UF.LON_GRA,' ',UF.LON_MIN,' ',UF.LON_SEG)       AS longitud,
        UF.cohorte   AS cohorte,
        UF.visita    AS visita,
        UF.sisb_grupo AS sisben_grupo,
        UF.sisb_subgr AS sisben_subgrupo,
        UF.direccion  AS direccion,
        CASE WHEN UF.telefono  IN ('-1','') OR UF.telefono  IS NULL
             THEN 'N/A' ELSE UF.telefono  END                  AS telefono_1,
        CASE WHEN UF.telefono2 IN ('-1','') OR UF.telefono2 IS NULL
             THEN 'N/A' ELSE UF.telefono2 END                  AS telefono_2,
        COALESCE(NULLIF(UF.correo,''), 'N/A')                  AS correo
    FROM SBW_PERSONA_CARACTERIZADA PC
    LEFT JOIN SBW_UBICACION_FAMILIA   UF ON UF.UID = PC.uid AND UF.ciuf = PC.ciuf
    LEFT JOIN AVS_OCUPACION_INGRESO   OI ON OI.COD_OCUPACION_INGRESO = PC.ocupacio
    LEFT JOIN tabla_institucion       I  ON I.cod_inst         = PC.instusua
    LEFT JOIN SBW_TIPO_REGIMEN_SGSSS  R  ON R.COD_TIPO_REGIMEN = PC.tipousua
    LEFT JOIN parentes                P  ON P.codigo           = PC.parentes
    LEFT JOIN programas               PG ON PG.codigo          = PC.programas
    LEFT JOIN etnia                   E  ON E.codigo           = PC.etnia
    LEFT JOIN AVS_DEPARTAMENTO_SALUD  D  ON D.COD_DEPARTAMENTO = PC.codniv1
    LEFT JOIN AVS_MUNICIPIO_SALUD     M  ON M.COD_MUNICIPIO    = PC.codniv1 + PC.codniv2
    LEFT JOIN AVS_TIPO_FAMILIA        TF ON TF.COD_TIPO_FAMILIA = UF.tipofami
    LEFT JOIN SBW_TIPO_DISCAPACIDAD   TD ON TD.COD_TIPO_DISCAPACIDAD = PC.discap
    WHERE UF.fecha_reg >= ?
      AND UF.fecha_reg <= ?
)
SELECT *
FROM X
WHERE X.FAM_NUM > ? AND X.FAM_NUM <= ?
ORDER BY X.FAM_NUM, X._parentes_cod, X.num_documento
"""

# Mismo universo que el FETCH pero contando FAMILIAS (la unidad de PDF y de
# paginación). El CONCAT replica exactamente las columnas del DENSE_RANK.
# No incluye los joins de catálogos: no afectan la cantidad de familias.
QUERY_CARACTERIZACION_COUNT = """
SELECT COUNT(DISTINCT CONCAT(
    PC.[codniv1], '|', PC.[codniv2], '|', PC.[codniv3], '|', PC.[codniv4], '|',
    PC.[codniv5], '|', PC.[codniv6], '|', PC.[codvivi], '|', PC.[codfami], '|',
    PC.ciuf
)) AS total
FROM SBW_PERSONA_CARACTERIZADA PC
LEFT JOIN SBW_UBICACION_FAMILIA UF ON UF.UID = PC.uid AND UF.ciuf = PC.ciuf
WHERE UF.fecha_reg >= ?
  AND UF.fecha_reg <= ?
"""


# ─── helpers ──────────────────────────────────────────────────────────────────

def _str(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _fechas_dt(desde: date, hasta: date):
    from datetime import datetime as _dt
    return (
        _dt(desde.year, desde.month, desde.day, 0, 0, 0),
        _dt(hasta.year, hasta.month, hasta.day, 23, 59, 59),
    )


_CAMPOS = [
    "departamento", "municipio", "area", "corregimiento", "barrio_vereda",
    "manzana", "vivienda", "familia", "tipo_familia", "ciuf",
    "tipo_documento", "num_documento", "nombres_apellidos", "sexo",
    "fecha_nacimiento", "edad", "unidades", "parentesco", "estudia",
    "anos_aprobados", "nombre_ocupacion",
    "nombre_institucion", "descripcion_regimen",
    "etnia", "gae", "programa", "discapacidad",
    "fecha_registro", "latitud", "longitud", "cohorte", "visita",
    "sisben_grupo", "sisben_subgrupo", "direccion", "telefono_1",
    "telefono_2", "correo",
]


def _fila_a_registro(r: dict) -> RegistroCaracterizacion:
    return RegistroCaracterizacion(**{c: _str(r.get(c)) for c in _CAMPOS})


# ─── Mock para desarrollo ─────────────────────────────────────────────────────

class MockCaracterizacionRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
    ) -> list[RegistroCaracterizacion]:
        import random
        from datetime import timedelta

        # Catálogos en descripción legible (igual que el repo real con los joins).
        nombres = ["JOSE", "MARIA", "LUIS", "ANA", "CARLOS", "ROSA", "PEDRO", "LUZ"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
        # Parentesco: el primero (m==0) siempre JEFE DE FAMILIA; el resto rota.
        parentescos_otros = ["CONYUGE", "HIJO", "OTROS PARIENTES (Padres, Suegros, etc)",
                             "OTROS MIEMBROS, NO PARIENTES"]
        ocupaciones = ["TRABAJANDO", "ESTUDIANDO", "OFICIOS DEL HOGAR",
                       "JUBILADO,PENSIONADO", "NO APLICA, POR EDAD", "SIN OCUPACION/INGRESO"]
        etnias = ["NINGUNO", "INDIGENA", "AFRODESCENDIENTES-NEGROS-RAIZALES"]
        programas_mock = ["NO PERTENECE A NINGUN PROGRAMA", "MAS FAMILIAS EN ACCION",
                          "JOVENES EN ACCION", "HOGAR DE BIENESTAR FAMILIAR"]
        discapacidades_mock = ["NINGUNA", "AUDITIVA:SORDA", "VISUAL:CIEGA TOTAL",
                               "FISICA:AMPUTACION", "DISCAPACIDAD MENTAL"]
        tipos_familia = ["NUCLEAR", "EXTENSA - COMPUESTA", "MONOPARENTAL"]
        # Catálogo SBW_TIPO_REGIMEN_SGSSS — régimen a NIVEL PERSONA: cada
        # integrante puede tener uno distinto (familias mixtas ~4% reales).
        regimenes_desc = ["SUBSIDIADO", "CONTRIBUTIVO", "POBRE NO ASEGURADO",
                          "OTRO (Regimen especial)", "PARTICULAR"]
        regimenes_pesos = [0.95, 0.04, 0.003, 0.002, 0.005]

        regs: list[RegistroCaracterizacion] = []
        # limite/offset en FAMILIAS (igual que el repo real): cada familia trae
        # 4 integrantes completos — una familia nunca se parte entre lotes.
        for f in range(limite):
            n_familia = offset + f
            for m in range(4):
                seq = n_familia * 4 + m
                # rng_fam: campos compartidos por la familia (geografía, ubicación).
                # rng: campos propios de cada integrante.
                rng_fam = random.Random(n_familia * 31)
                rng = random.Random(seq * 17)
                fecha_r = desde + timedelta(days=rng_fam.randint(0, max((hasta - desde).days, 0)))
                des_reg = rng.choices(regimenes_desc, weights=regimenes_pesos, k=1)[0]
                es_cabeza = m == 0
                # Teléfonos: a veces vienen como N/A simulando datos sin teléfono.
                tel1 = "N/A" if rng_fam.random() < 0.1 else f"30{rng_fam.randint(0, 9)}{rng_fam.randint(1000000, 9999999)}"
                regs.append(RegistroCaracterizacion(
                    # Descripciones ya legibles (como las devuelve el SQL real).
                    departamento="BOLIVAR", municipio=f"MUNICIPIO {rng_fam.randint(1, 99):03d}",
                    area=rng_fam.choice(["URBANA", "RURAL"]), corregimiento="00",
                    barrio_vereda=f"{rng_fam.randint(1, 50):03d}", manzana=f"{rng_fam.randint(1, 20):02d}",
                    vivienda=f"{n_familia % 999 + 1:04d}", familia=f"{n_familia % 9 + 1}",
                    tipo_familia=rng_fam.choice(tipos_familia),
                    ciuf=str(100000 + n_familia),
                    tipo_documento=rng.choice(["CC", "TI", "RC"]) if not es_cabeza else "CC",
                    num_documento=str(1_000_000_000 + seq),
                    nombres_apellidos=f"{rng.choice(nombres)} {rng.choice(apellidos)} {rng.choice(apellidos)}",
                    sexo=rng.choice(["M", "F"]),
                    fecha_nacimiento=f"19{rng.randint(40, 99):02d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                    edad=str(rng.randint(1, 90)), unidades="A",
                    parentesco="JEFE DE FAMILIA" if es_cabeza else rng.choice(parentescos_otros),
                    estudia=rng.choice(["SI", "NO"]), anos_aprobados=str(rng.randint(0, 11)),
                    nombre_ocupacion=rng.choice(ocupaciones),
                    nombre_institucion="ASOCIACION MUTUAL SER - EMPRESA SOLIDARIA DE SALUD E.S.S.",
                    descripcion_regimen=des_reg,
                    etnia=rng.choice(etnias), gae=rng.choice(["0", "1"]),
                    programa=rng.choice(programas_mock),
                    discapacidad=rng.choice(discapacidades_mock),
                    fecha_registro=str(fecha_r),
                    latitud=f"{rng_fam.randint(8, 10)} {rng_fam.randint(0, 59)} N",
                    longitud=f"{rng_fam.randint(74, 76)} {rng_fam.randint(0, 59)} W",
                    cohorte=str(rng_fam.randint(1, 5)), visita=str(rng_fam.randint(1, 3)),
                    sisben_grupo=rng_fam.choice(["A", "B", "C"]), sisben_subgrupo=str(rng_fam.randint(1, 9)),
                    direccion=f"CALLE {rng_fam.randint(1, 99)} # {rng_fam.randint(1, 99)}-{rng_fam.randint(1, 99)}",
                    telefono_1=tel1,
                    telefono_2="N/A", correo="N/A",
                ))
        return regs

    def get_total(self, desde: date, hasta: date) -> int:
        return 200   # familias (la unidad de paginación), no filas-persona


# ─── SQL Server real (sibacom) ────────────────────────────────────────────────

class SqlServerCaracterizacionRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
    ) -> list[RegistroCaracterizacion]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        log.info("caracterizacion.query", extra={"desde": str(desde), "hasta": str(hasta),
                                                 "familias": limite, "offset": offset})

        with pyodbc.connect(settings.db_dsn_sibacom, timeout=60) as conn:
            cur = conn.cursor()
            # Rango de familias: FAM_NUM en (offset, offset + limite]
            cur.execute(QUERY_CARACTERIZACION, fecha_inicio, fecha_final, offset, offset + limite)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        registros = [_fila_a_registro(r) for r in rows]
        log.info("caracterizacion.fetched", extra={"rows": len(registros)})
        return registros

    def get_total(self, desde: date, hasta: date) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        try:
            with pyodbc.connect(settings.db_dsn_sibacom, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(QUERY_CARACTERIZACION_COUNT, fecha_inicio, fecha_final)
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            log.exception("caracterizacion.get_total failed")
            return 0


def get_caracterizacion_repository() -> CaracterizacionRepository:
    if settings.use_mock:
        log.info("caracterizacion repo: MOCK")
        return MockCaracterizacionRepository()
    log.info("caracterizacion repo: SQL Server (sibacom)")
    return SqlServerCaracterizacionRepository()
