"""Repositorio Educación Grupal — SRG_EDUCACION_GRUPAL + asistentes."""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import RegistroEducacionGrupal

log = logging.getLogger(__name__)


class EducacionGrupalRepository(Protocol):
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroEducacionGrupal]: ...

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int: ...


# Single source of truth para el WHERE — evita que COUNT y FETCH diverjan
# (bug histórico project-count-vs-fetch-bug). El `IS NOT NULL` descarta
# asistentes sin afiliado clasificable: decisión consciente del módulo
# (Educación Grupal es reporte interno P&P, no se reporta a RIPS).
def _build_wheres(regimen: str | None) -> tuple[list[str], list]:
    wheres = [
        "a.fec_educacion_grupal >= ?",
        "a.fec_educacion_grupal <= ?",
        "h.AFIC_REGIMEN IS NOT NULL",
    ]
    params: list = []
    if regimen:
        wheres.append("h.AFIC_REGIMEN = ?")
        params.append("S" if regimen.upper() == "SUBSIDIADO" else "C")
    return wheres, params


# FROM + JOINs compartido entre COUNT y FETCH (parte estructural; el SELECT
# del CTE agrega columnas adicionales pero el FROM/JOIN/WHERE es el mismo).
_FROM_JOINS = """
FROM SRG_EDUCACION_GRUPAL a
    LEFT JOIN AVS_USUARIO_SISTEMA AS b ON a.seq_usuario_facilitador = b.SEQ_USUARIO_SISTEMA
    LEFT JOIN SRG_TEMAS_EDUCACION_GRUPAL AS c ON (a.cod_cursovida_asistente = c.cod_cursovida_asistente
                                       AND a.cod_eje_tematico = c.cod_eje_tematico)
    LEFT JOIN avs_curso_vida AS d ON a.cod_cursovida_asistente = d.cod_curso_vida_asociado
    LEFT JOIN AVS_DEPARTAMENTO AS e ON a.cod_departamento = e.COD_DEPARTAMENTO
    LEFT JOIN AVS_MUNICIPIO f ON a.cod_municipio = f.cod_municipio
    LEFT JOIN SRG_ASISTENTE_EDUCACION_GRUPAL AS g ON a.seq_educacion_grupal = g.seq_educacion_grupal
    LEFT JOIN AVS_AFILIADO_MUTUALSER_HIS AS h ON (g.cod_tipo_identificacion = h.COD_TIPO_IDENTIFICACION
                                       AND g.nro_tipo_identificacion = h.NRO_TIPO_IDENTIFICACION)
"""


def _build_count_sql(regimen: str | None = None) -> tuple[str, list]:
    wheres, params = _build_wheres(regimen)
    where_clause = " AND ".join(wheres)
    sql = f"SELECT COUNT(*) AS total {_FROM_JOINS} WHERE {where_clause}"
    return sql, params


def _build_query_sql(regimen: str | None = None) -> tuple[str, list]:
    wheres, _ = _build_wheres(regimen)
    where_str = "\n      AND ".join(wheres)

    sql = f"""
WITH X AS (
    SELECT ROW_NUMBER() OVER (ORDER BY a.fec_educacion_grupal) AS NUM_REGISTRO,
           a.seq_educacion_grupal,
           b.TXT_PRIMER_NOMBRE+' '+ ISNULL(b.TXT_SEGUNDO_NOMBRE, '')+' '
               +ISNULL(b.TXT_PRIMER_APELLIDO,'')+' '+ ISNULL(b.TXT_SEGUNDO_APELLIDO,'') AS facilitador,
           d.des_curso_vida_asociado, c.des_eje_tematico,
           des_modalidad = CASE
               WHEN a.cod_modalidad = 'PR' THEN 'PRESENCIAL'
               WHEN a.cod_modalidad = 'VI' THEN 'VIRTUAL'
               ELSE 'OTROS'
           END,
           CONVERT(CHAR(10), a.fec_educacion_grupal) AS fec_educacion_grupal,
           CONVERT(CHAR(10), a.fec_registro_educacion) AS fec_registro_educacion,
           e.DES_DEPARTAMENTO, f.DES_MUNICIPIO,
           ISNULL(a.txt_ubicacion_fisica,'') AS txt_ubicacion_fisica,
           g.cod_tipo_identificacion, g.nro_tipo_identificacion,
           ISNULL(h.AFL_PRIMER_NOMBRE+' '+ ISNULL(h.AFL_SEGUNDO_NOMBRE, '')+' '
               +h.AFL_PRIMER_APELLIDO +' '+ISNULL(h.AFL_SEGUNDO_APELLIDO, ''),'') AS nombre_afiliado,
           REGIMEN = CASE
               WHEN h.AFIC_REGIMEN = 'S' THEN 'SUBSIDIADO'
               WHEN h.AFIC_REGIMEN = 'C' THEN 'CONTRIBUTIVO'
           END
    {_FROM_JOINS}
    WHERE {where_str}
)
SELECT X.NUM_REGISTRO, X.seq_educacion_grupal, X.facilitador, X.des_curso_vida_asociado,
       X.des_eje_tematico, X.des_modalidad, X.fec_educacion_grupal, X.fec_registro_educacion,
       X.DES_DEPARTAMENTO, X.DES_MUNICIPIO, X.txt_ubicacion_fisica,
       X.cod_tipo_identificacion, X.nro_tipo_identificacion, X.nombre_afiliado, X.REGIMEN,
       (SELECT COUNT(1) FROM X) AS CAN_REGISTROS
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""
    return sql, []


def _fechas_dt(desde: date, hasta: date):
    from datetime import datetime as _dt
    return (
        _dt(desde.year, desde.month, desde.day, 0, 0, 0),
        _dt(hasta.year, hasta.month, hasta.day, 23, 59, 59),
    )


def _parse_date(v: object):
    if v is None or v == "":
        return None
    from datetime import date as _d, datetime as _dt
    if isinstance(v, _d):
        return v
    s = str(v).strip()[:10]
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return _dt.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class MockEducacionGrupalRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroEducacionGrupal]:
        import random
        from datetime import timedelta
        registros = []
        cursos = ["PRIMERA INFANCIA", "INFANCIA", "ADOLESCENCIA", "JUVENTUD", "ADULTEZ", "VEJEZ"]
        ejes = ["SALUD SEXUAL", "SALUD MENTAL", "ACTIVIDAD FISICA", "NUTRICION", "PREVENCION"]
        modalidades = ["PRESENCIAL", "VIRTUAL", "PRESENCIAL", "PRESENCIAL"]
        deptos = ["BOLIVAR", "ATLANTICO", "CORDOBA", "SUCRE", "MAGDALENA", "CESAR"]
        municipios = ["CARTAGENA", "BARRANQUILLA", "MONTERIA", "SINCELEJO", "VALLEDUPAR"]
        facilitadores = ["MARIA PEREZ", "CARLOS GOMEZ", "ANA MARTINEZ", "JOSE RODRIGUEZ"]
        nombres = ["LUIS", "MARIA", "PEDRO", "ANA", "CARLOS", "SOFIA", "JUAN", "ELENA"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ"]
        regimenes = ["SUBSIDIADO", "CONTRIBUTIVO", "SUBSIDIADO", "SUBSIDIADO"]

        for i in range(limite):
            seq = offset + i + 1
            rng = random.Random(seq * 17)
            dias = max((hasta - desde).days, 0)
            fec_sesion = desde + timedelta(days=rng.randint(0, dias))
            n1 = rng.choice(nombres)
            a1 = rng.choice(apellidos)
            a2 = rng.choice(apellidos)
            nombre_full = f"{n1} {a1} {a2}"
            num_doc = str(1000000 + seq)
            reg = rng.choice(regimenes)

            if regimen and reg != regimen.upper():
                continue

            registros.append(RegistroEducacionGrupal(
                seq_educacion_grupal=seq % 100 + 1,
                consecutivo=seq,
                facilitador=rng.choice(facilitadores),
                des_curso_vida_asociado=rng.choice(cursos),
                des_eje_tematico=rng.choice(ejes),
                des_modalidad=rng.choice(modalidades),
                fec_educacion_grupal=str(fec_sesion),
                fec_registro_educacion=str(fec_sesion),
                departamento=rng.choice(deptos),
                municipio=rng.choice(municipios),
                txt_ubicacion_fisica=f"SALON {rng.randint(1, 20)}",
                cod_tipo_identificacion="CC",
                nro_tipo_identificacion=num_doc,
                nombre_afiliado=nombre_full,
                regimen=reg,
            ))
        return registros

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int:
        base = 500
        if regimen:
            base = base // 2
        return base


class SqlServerEducacionGrupalRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroEducacionGrupal]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql, _ = _build_query_sql(regimen)
        params: list = [fecha_inicio, fecha_final]
        if regimen:
            params.append("S" if regimen.upper() == "SUBSIDIADO" else "C")
        params += [offset, limite]
        log.info("educacion_grupal.query", extra={"desde": str(desde), "hasta": str(hasta),
                                                   "limite": limite, "offset": offset,
                                                   "regimen": regimen})

        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(sql, *params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        registros: list[RegistroEducacionGrupal] = []
        for r in rows:
            registros.append(RegistroEducacionGrupal(
                seq_educacion_grupal=int(r["seq_educacion_grupal"]),
                consecutivo=int(r["NUM_REGISTRO"]),
                facilitador=(r.get("facilitador") or "").strip() or None,
                des_curso_vida_asociado=(r.get("des_curso_vida_asociado") or "").strip() or None,
                des_eje_tematico=(r.get("des_eje_tematico") or "").strip() or None,
                des_modalidad=(r.get("des_modalidad") or "").strip() or None,
                fec_educacion_grupal=(r.get("fec_educacion_grupal") or "").strip() or None,
                fec_registro_educacion=(r.get("fec_registro_educacion") or "").strip() or None,
                departamento=(r.get("DES_DEPARTAMENTO") or "").strip() or None,
                municipio=(r.get("DES_MUNICIPIO") or "").strip() or None,
                txt_ubicacion_fisica=(r.get("txt_ubicacion_fisica") or "").strip() or None,
                cod_tipo_identificacion=(r.get("cod_tipo_identificacion") or "").strip() or None,
                nro_tipo_identificacion=(r.get("nro_tipo_identificacion") or "").strip() or None,
                nombre_afiliado=(r.get("nombre_afiliado") or "").strip() or None,
                regimen=(r.get("REGIMEN") or "").strip() or None,
            ))

        log.info("educacion_grupal.fetched", extra={"rows": len(registros)})
        return registros

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql, _ = _build_count_sql(regimen)
        params: list = [fecha_inicio, fecha_final]
        if regimen:
            params.append("S" if regimen.upper() == "SUBSIDIADO" else "C")
        try:
            with pyodbc.connect(settings.db_dsn, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(sql, *params)
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            log.exception("educacion_grupal.get_total failed")
            return 0


def get_educacion_grupal_repository() -> EducacionGrupalRepository:
    if settings.use_mock:
        return MockEducacionGrupalRepository()
    return SqlServerEducacionGrupalRepository()
