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
    """`limite` y `offset` se expresan en FAMILIAS (no en filas-persona).

    `regimen` filtra por el régimen DEL JEFE DE FAMILIA (parentes='1'):
      - 'SUBSIDIADO'   → solo familias cuyo jefe es 'S'
      - 'CONTRIBUTIVO' → solo familias cuyo jefe es 'C'
      - None           → todas las familias, sin filtro
    Familias sin jefe explícito caen al primer integrante por orden natural BD.
    Familias con jefe en régimen distinto de S/C (N, O, P) quedan fuera de ambos lotes.
    """

    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroCaracterizacion]: ...

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int: ...


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
WITH regimen_familiar AS (
    -- Régimen "representativo" de cada familia: el del JEFE DE FAMILIA
    -- (parentes='1'). Si hay varios jefes, gana el de menor uid (orden BD).
    -- Si NO hay ningún jefe, cae al primer integrante por uid.
    SELECT ciuf, tipousua AS regimen_jefe
    FROM (
        SELECT
            PC.ciuf, PC.tipousua,
            ROW_NUMBER() OVER (
                PARTITION BY PC.ciuf
                ORDER BY
                    CASE WHEN PC.parentes = '1' THEN 0 ELSE 1 END,
                    PC.uid
            ) AS rn
        FROM SBW_PERSONA_CARACTERIZADA PC
    ) X
    WHERE rn = 1
),
X AS (
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
    INNER JOIN regimen_familiar       RF ON RF.ciuf              = PC.ciuf
    WHERE UF.fecha_reg >= ?
      AND UF.fecha_reg <= ?
      {regimen_filter}
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
WITH regimen_familiar AS (
    SELECT ciuf, tipousua AS regimen_jefe
    FROM (
        SELECT
            PC.ciuf, PC.tipousua,
            ROW_NUMBER() OVER (
                PARTITION BY PC.ciuf
                ORDER BY
                    CASE WHEN PC.parentes = '1' THEN 0 ELSE 1 END,
                    PC.uid
            ) AS rn
        FROM SBW_PERSONA_CARACTERIZADA PC
    ) X
    WHERE rn = 1
)
SELECT COUNT(DISTINCT CONCAT(
    PC.[codniv1], '|', PC.[codniv2], '|', PC.[codniv3], '|', PC.[codniv4], '|',
    PC.[codniv5], '|', PC.[codniv6], '|', PC.[codvivi], '|', PC.[codfami], '|',
    PC.ciuf
)) AS total
FROM SBW_PERSONA_CARACTERIZADA PC
LEFT JOIN SBW_UBICACION_FAMILIA UF ON UF.UID = PC.uid AND UF.ciuf = PC.ciuf
INNER JOIN regimen_familiar RF ON RF.ciuf = PC.ciuf
WHERE UF.fecha_reg >= ?
  AND UF.fecha_reg <= ?
  {regimen_filter}
"""

# Mapeo régimen humano → código de PC.tipousua (catálogo SBW_TIPO_REGIMEN_SGSSS)
_REGIMEN_TO_COD = {"SUBSIDIADO": "S", "CONTRIBUTIVO": "C"}


def _regimen_filter(regimen: str | None) -> tuple[str, list]:
    """Devuelve (sql_fragment, params_extra) para inyectar en la query."""
    if regimen is None:
        return "", []
    cod = _REGIMEN_TO_COD.get(regimen.upper().strip())
    if cod is None:
        return "", []
    return "AND RF.regimen_jefe = ?", [cod]


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

# Catálogos en descripción legible (igual que el repo real con los joins).
_MOCK_NOMBRES = ["JOSE", "MARIA", "LUIS", "ANA", "CARLOS", "ROSA", "PEDRO", "LUZ"]
_MOCK_APELLIDOS = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
_MOCK_PARENTESCOS_OTROS = ["CONYUGE", "HIJO", "OTROS PARIENTES (Padres, Suegros, etc)",
                           "OTROS MIEMBROS, NO PARIENTES"]
_MOCK_OCUPACIONES = ["TRABAJANDO", "ESTUDIANDO", "OFICIOS DEL HOGAR",
                     "JUBILADO,PENSIONADO", "NO APLICA, POR EDAD", "SIN OCUPACION/INGRESO"]
_MOCK_ETNIAS = ["NINGUNO", "INDIGENA", "AFRODESCENDIENTES-NEGROS-RAIZALES"]
_MOCK_PROGRAMAS = ["NO PERTENECE A NINGUN PROGRAMA", "MAS FAMILIAS EN ACCION",
                   "JOVENES EN ACCION", "HOGAR DE BIENESTAR FAMILIAR"]
_MOCK_DISCAPACIDADES = ["NINGUNA", "AUDITIVA:SORDA", "VISUAL:CIEGA TOTAL",
                        "FISICA:AMPUTACION", "DISCAPACIDAD MENTAL"]
_MOCK_TIPOS_FAMILIA = ["NUCLEAR", "EXTENSA - COMPUESTA", "MONOPARENTAL"]
_MOCK_REGIMENES = ["SUBSIDIADO", "CONTRIBUTIVO", "POBRE NO ASEGURADO",
                   "OTRO (Regimen especial)", "PARTICULAR"]
_MOCK_REGIMENES_PESOS = [0.95, 0.04, 0.003, 0.002, 0.005]
# Total simulado de familias en el mock — define el universo paginable.
_MOCK_TOTAL_FAMILIAS = 200


def _mock_regimen_jefe(n_familia: int) -> str:
    """Régimen DEL JEFE (m==0) de una familia mock. Determinístico por n_familia.

    Coincide con la regla de negocio del repo real: el jefe representa a toda
    la familia. Usado para filtrar por régimen en el mock.
    """
    import random
    seq_jefe = n_familia * 4 + 0
    rng = random.Random(seq_jefe * 17)
    return rng.choices(_MOCK_REGIMENES, weights=_MOCK_REGIMENES_PESOS, k=1)[0]


class MockCaracterizacionRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroCaracterizacion]:
        import random
        from datetime import timedelta

        target_reg = regimen.upper().strip() if regimen else None

        regs: list[RegistroCaracterizacion] = []
        familias_emitidas = 0           # familias agregadas a la salida
        familias_filtradas_vistas = 0   # familias que cumplen el filtro (para offset)
        n_familia = 0                   # índice global del universo mock

        # Iteramos el universo hasta llenar `limite` familias post-filtro
        # (o agotar el universo simulado).
        while familias_emitidas < limite and n_familia < _MOCK_TOTAL_FAMILIAS:
            # ¿La familia n_familia pasa el filtro por régimen del jefe?
            pasa = target_reg is None or _mock_regimen_jefe(n_familia) == target_reg

            if pasa:
                # Saltamos las primeras `offset` familias filtradas
                if familias_filtradas_vistas >= offset:
                    self._emit_familia(regs, n_familia, desde, hasta)
                    familias_emitidas += 1
                familias_filtradas_vistas += 1

            n_familia += 1

        return regs

    def _emit_familia(self, out: list, n_familia: int, desde: date, hasta: date) -> None:
        """Agrega los 4 integrantes de la familia n al output."""
        import random
        from datetime import timedelta

        rng_fam = random.Random(n_familia * 31)
        fecha_r = desde + timedelta(days=rng_fam.randint(0, max((hasta - desde).days, 0)))
        # Teléfonos: a veces vienen como N/A simulando datos sin teléfono.
        tel1 = ("N/A" if rng_fam.random() < 0.1
                else f"30{rng_fam.randint(0, 9)}{rng_fam.randint(1000000, 9999999)}")
        # Campos compartidos por la familia
        depto = "BOLIVAR"
        muni = f"MUNICIPIO {rng_fam.randint(1, 99):03d}"
        area = rng_fam.choice(["URBANA", "RURAL"])
        barrio = f"{rng_fam.randint(1, 50):03d}"
        manzana = f"{rng_fam.randint(1, 20):02d}"
        viv = f"{n_familia % 999 + 1:04d}"
        fam_num = f"{n_familia % 9 + 1}"
        tipo_fam = rng_fam.choice(_MOCK_TIPOS_FAMILIA)
        ciuf = str(100000 + n_familia)
        lat = f"{rng_fam.randint(8, 10)} {rng_fam.randint(0, 59)} N"
        lon = f"{rng_fam.randint(74, 76)} {rng_fam.randint(0, 59)} W"
        cohorte = str(rng_fam.randint(1, 5))
        visita = str(rng_fam.randint(1, 3))
        sis_g = rng_fam.choice(["A", "B", "C"])
        sis_sg = str(rng_fam.randint(1, 9))
        dir_ = f"CALLE {rng_fam.randint(1, 99)} # {rng_fam.randint(1, 99)}-{rng_fam.randint(1, 99)}"

        for m in range(4):
            seq = n_familia * 4 + m
            rng = random.Random(seq * 17)
            des_reg = rng.choices(_MOCK_REGIMENES, weights=_MOCK_REGIMENES_PESOS, k=1)[0]
            es_cabeza = m == 0
            out.append(RegistroCaracterizacion(
                departamento=depto, municipio=muni, area=area,
                corregimiento="00", barrio_vereda=barrio, manzana=manzana,
                vivienda=viv, familia=fam_num, tipo_familia=tipo_fam, ciuf=ciuf,
                tipo_documento=rng.choice(["CC", "TI", "RC"]) if not es_cabeza else "CC",
                num_documento=str(1_000_000_000 + seq),
                nombres_apellidos=f"{rng.choice(_MOCK_NOMBRES)} {rng.choice(_MOCK_APELLIDOS)} {rng.choice(_MOCK_APELLIDOS)}",
                sexo=rng.choice(["M", "F"]),
                fecha_nacimiento=f"19{rng.randint(40, 99):02d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                edad=str(rng.randint(1, 90)), unidades="A",
                parentesco="JEFE DE FAMILIA" if es_cabeza else rng.choice(_MOCK_PARENTESCOS_OTROS),
                estudia=rng.choice(["SI", "NO"]), anos_aprobados=str(rng.randint(0, 11)),
                nombre_ocupacion=rng.choice(_MOCK_OCUPACIONES),
                nombre_institucion="ASOCIACION MUTUAL SER - EMPRESA SOLIDARIA DE SALUD E.S.S.",
                descripcion_regimen=des_reg,
                etnia=rng.choice(_MOCK_ETNIAS), gae=rng.choice(["0", "1"]),
                programa=rng.choice(_MOCK_PROGRAMAS),
                discapacidad=rng.choice(_MOCK_DISCAPACIDADES),
                fecha_registro=str(fecha_r), latitud=lat, longitud=lon,
                cohorte=cohorte, visita=visita,
                sisben_grupo=sis_g, sisben_subgrupo=sis_sg,
                direccion=dir_, telefono_1=tel1,
                telefono_2="N/A", correo="N/A",
            ))

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int:
        """Total de familias en el mock filtradas por régimen del jefe."""
        target_reg = regimen.upper().strip() if regimen else None
        if target_reg is None:
            return _MOCK_TOTAL_FAMILIAS
        # Recorre el universo simulado y cuenta las que matchean
        return sum(
            1 for n in range(_MOCK_TOTAL_FAMILIAS)
            if _mock_regimen_jefe(n) == target_reg
        )


# ─── SQL Server real (sibacom) ────────────────────────────────────────────────

class SqlServerCaracterizacionRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroCaracterizacion]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        reg_sql, reg_params = _regimen_filter(regimen)
        sql = QUERY_CARACTERIZACION.format(regimen_filter=reg_sql)
        log.info("caracterizacion.query", extra={"desde": str(desde), "hasta": str(hasta),
                                                 "familias": limite, "offset": offset,
                                                 "regimen": regimen})

        with pyodbc.connect(settings.db_dsn_sibacom, timeout=60) as conn:
            cur = conn.cursor()
            # Params orden: fecha_ini, fecha_fin, [cod_regimen?], offset_lo, offset_hi
            params = [fecha_inicio, fecha_final, *reg_params, offset, offset + limite]
            cur.execute(sql, *params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        registros = [_fila_a_registro(r) for r in rows]
        log.info("caracterizacion.fetched", extra={"rows": len(registros)})
        return registros

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        reg_sql, reg_params = _regimen_filter(regimen)
        sql = QUERY_CARACTERIZACION_COUNT.format(regimen_filter=reg_sql)
        try:
            with pyodbc.connect(settings.db_dsn_sibacom, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(sql, fecha_inicio, fecha_final, *reg_params)
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
