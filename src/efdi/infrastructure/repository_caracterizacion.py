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
# El SELECT interno es la consulta entregada por el usuario, sin cambios de
# contenido. La paginación es por FAMILIA (DENSE_RANK sobre la jerarquía
# completa), no por fila: cada lote trae familias COMPLETAS — una familia nunca
# queda partida entre dos lotes (evita PDFs parciales/duplicados).
# `limite` y `offset` se expresan en familias.
QUERY_CARACTERIZACION = """
WITH X AS (
    SELECT
        DENSE_RANK() OVER (
            ORDER BY PC.[codniv1], PC.[codniv2], PC.[codniv3], PC.[codniv4],
                     PC.[codniv5], PC.[codniv6], PC.[codvivi], PC.[codfami],
                     PC.ciuf
        ) AS FAM_NUM,
        --AREA GEOGRAFICA
        PC.[codniv1] AS departamento,
        PC.[codniv2] AS municipio,
        PC.[codniv3] AS area,
        PC.[codniv4] AS corregimiento,
        PC.[codniv5] AS barrio_vereda,
        PC.[codniv6] AS manzana,
        PC.[codvivi] AS vivienda,
        PC.[codfami] AS familia,
        PC.ciuf AS ciuf,
        [tipodocu] AS tipo_documento,
        [numdocu] AS num_documento,
        CONCAT([primer_nombre],' '
              ,[segundo_nombre],' '
              ,[primer_apellido],' '
              ,[segundo_apellido]) AS nombres_apellidos,
        [sexo] AS sexo,
        [fechanac] AS fecha_nacimiento,
        [edad] AS edad,
        [edaduni] AS unidades,
        [parentes] AS parentesco,
        [estudia] AS estudia,
        [grado] AS anos_aprobados,
        [ocupacio] AS cod_ocupacion,
        O.DES_OCUPACION AS nombre_ocupacion,
        [tipousua] AS tipo_seguridad_social,
        [instusua] AS eps,
        I.desc_ins AS nombre_institucion,
        [etnia] AS etnia,
        [gae] AS gae,
        [programas] AS programa,
        [discap] AS discapacidad,
        UF.fecha_reg AS fecha_registro,
        CONCAT(UF.LAT_GRA,' ',UF.LAT_MIN,' ',UF.LAT_SEN) AS latitud,
        CONCAT(UF.LON_GRA,' ',UF.LON_MIN,' ',UF.LON_SEG) AS longitud,
        UF.cohorte AS cohorte,
        UF.visita AS visita,
        PC.tipousua AS cod_regimen,
        R.DES_TIPO_REGIMEN AS descripcion_regimen,
        UF.sisb_grupo AS sisben_grupo,
        UF.sisb_subgr AS sisben_subgrupo,
        UF.direccion AS direccion,
        UF.telefono AS telefono_1,
        UF.telefono2 AS telefono_2,
        UF.correo AS correo
    FROM [SBW_PERSONA_CARACTERIZADA] PC
    LEFT JOIN SBW_UBICACION_FAMILIA UF ON (UF.UID = PC.uid AND UF.ciuf = PC.ciuf)
    LEFT JOIN SBW_OCUPACION O ON O.COD_OCUPACION = PC.ocupacio
    LEFT JOIN tabla_institucion I ON I.cod_inst = PC.instusua
    LEFT JOIN SBW_TIPO_REGIMEN_SGSSS R ON R.COD_TIPO_REGIMEN = PC.tipousua
    WHERE UF.fecha_reg >= ?
      AND UF.fecha_reg <= ?
)
SELECT *
FROM X
WHERE X.FAM_NUM > ? AND X.FAM_NUM <= ?
ORDER BY X.FAM_NUM, X.num_documento
"""

# Mismo universo que el FETCH pero contando FAMILIAS (la unidad de PDF y de
# paginación). El CONCAT replica exactamente las columnas del DENSE_RANK.
QUERY_CARACTERIZACION_COUNT = """
SELECT COUNT(DISTINCT CONCAT(
    PC.[codniv1], '|', PC.[codniv2], '|', PC.[codniv3], '|', PC.[codniv4], '|',
    PC.[codniv5], '|', PC.[codniv6], '|', PC.[codvivi], '|', PC.[codfami], '|',
    PC.ciuf
)) AS total
FROM [SBW_PERSONA_CARACTERIZADA] PC
LEFT JOIN SBW_UBICACION_FAMILIA UF ON (UF.UID = PC.uid AND UF.ciuf = PC.ciuf)
LEFT JOIN SBW_OCUPACION O ON O.COD_OCUPACION = PC.ocupacio
LEFT JOIN tabla_institucion I ON I.cod_inst = PC.instusua
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
    "manzana", "vivienda", "familia", "ciuf",
    "tipo_documento", "num_documento", "nombres_apellidos", "sexo",
    "fecha_nacimiento", "edad", "unidades", "parentesco", "estudia",
    "anos_aprobados", "cod_ocupacion", "nombre_ocupacion",
    "tipo_seguridad_social", "eps", "nombre_institucion", "etnia", "gae",
    "programa", "discapacidad",
    "fecha_registro", "latitud", "longitud", "cohorte", "visita",
    "cod_regimen", "descripcion_regimen",
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

        nombres = ["JOSE", "MARIA", "LUIS", "ANA", "CARLOS", "ROSA", "PEDRO", "LUZ"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
        parentescos = ["CABEZA DE FAMILIA", "CONYUGE", "HIJO(A)", "NIETO(A)", "OTRO"]
        ocupaciones = [("001", "AGRICULTOR"), ("002", "AMA DE CASA"), ("003", "ESTUDIANTE"),
                       ("004", "COMERCIANTE"), ("005", "DOCENTE")]
        etnias = ["NINGUNA", "AFRODESCENDIENTE", "INDIGENA"]
        # Catálogo SBW_TIPO_REGIMEN_SGSSS (5 filas reales). El régimen es a NIVEL
        # PERSONA: cada integrante elige el suyo, por eso pueden existir familias
        # mixtas (cabeza C + hijo S, etc.) — pasa en ~4% de los casos reales.
        regimenes = [("S", "SUBSIDIADO"), ("C", "CONTRIBUTIVO"), ("N", "POBRE NO ASEGURADO"),
                     ("O", "OTRO (Regimen especial)"), ("P", "PARTICULAR")]
        regimenes_pesos = [0.95, 0.04, 0.003, 0.002, 0.005]  # mismo skew que sibacom

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
                cod_ocu, nom_ocu = rng.choice(ocupaciones)
                # Una sola elección: código y descripción siempre coherentes
                cod_reg, des_reg = rng.choices(regimenes, weights=regimenes_pesos, k=1)[0]
                es_cabeza = m == 0
                regs.append(RegistroCaracterizacion(
                    departamento="13", municipio=f"{rng_fam.randint(1, 99):03d}",
                    area=rng_fam.choice(["1", "2"]), corregimiento="00",
                    barrio_vereda=f"{rng_fam.randint(1, 50):03d}", manzana=f"{rng_fam.randint(1, 20):02d}",
                    vivienda=f"{n_familia % 999 + 1:04d}", familia=f"{n_familia % 9 + 1}",
                    ciuf=str(100000 + n_familia),
                    tipo_documento=rng.choice(["CC", "TI", "RC"]) if not es_cabeza else "CC",
                    num_documento=str(1_000_000_000 + seq),
                    nombres_apellidos=f"{rng.choice(nombres)} {rng.choice(apellidos)} {rng.choice(apellidos)}",
                    sexo=rng.choice(["M", "F"]),
                    fecha_nacimiento=f"19{rng.randint(40, 99):02d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                    edad=str(rng.randint(1, 90)), unidades="1",
                    parentesco="CABEZA DE FAMILIA" if es_cabeza else rng.choice(parentescos[1:]),
                    estudia=rng.choice(["SI", "NO"]), anos_aprobados=str(rng.randint(0, 11)),
                    cod_ocupacion=cod_ocu, nombre_ocupacion=nom_ocu,
                    tipo_seguridad_social=rng.choice(["S", "C"]),
                    eps="EPS025", nombre_institucion="MUTUAL SER",
                    etnia=rng.choice(etnias), gae=rng.choice(["", "1"]),
                    programa=rng.choice(["", "GESTANTES", "HTA"]),
                    discapacidad=rng.choice(["", "NINGUNA", "FISICA"]),
                    fecha_registro=str(fecha_r),
                    latitud=f"{rng_fam.randint(8, 10)} {rng_fam.randint(0, 59)} N",
                    longitud=f"{rng_fam.randint(74, 76)} {rng_fam.randint(0, 59)} W",
                    cohorte=str(rng_fam.randint(1, 5)), visita=str(rng_fam.randint(1, 3)),
                    # Régimen por persona (rng, no rng_fam) → simula mezcla intrafamiliar
                    cod_regimen=cod_reg, descripcion_regimen=des_reg,
                    sisben_grupo=rng_fam.choice(["A", "B", "C"]), sisben_subgrupo=str(rng_fam.randint(1, 9)),
                    direccion=f"CALLE {rng_fam.randint(1, 99)} # {rng_fam.randint(1, 99)}-{rng_fam.randint(1, 99)}",
                    telefono_1=f"30{rng_fam.randint(0, 9)}{rng_fam.randint(1000000, 9999999)}",
                    telefono_2="", correo="",
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
