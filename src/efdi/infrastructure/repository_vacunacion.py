"""Repository de Vacunación — consulta SQL Server (AVS_REGISTRO_SERAGIL +
AVS_PROGRAMA_ASOCIADO_DEMIND filtrado por códigos de programa de vacunación).

Antes este módulo leía un .xlsx subido a mano porque no había query conectada;
ahora usa la misma consulta base de Demanda Inducida, acotada a los códigos de
programa de vacunación (`COD_PROGRAMA_DEMIND IN (...)`, esquema regular +
COVID-19) y filtrada por régimen igual que Captación/Educación Grupal — sin
factura, porque Vacunación no se factura por CAB/FAB.

El régimen sale de `AVS_AFILIADO_MUTUALSER_HIS.AFIC_REGIMEN` (S/C/V), igual que
los demás módulos de régimen simple.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import (
    Regimen,
    RegistroVacuna,
    Sexo,
    TipoDocumento,
)
from efdi.infrastructure.errors import RepositorioNoDisponibleError

log = logging.getLogger(__name__)


class VacunacionRepository(Protocol):
    """Contrato del repository."""

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int: ...

    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroVacuna]: ...


# ─── Helpers de normalización (sin cambios respecto a la versión Excel —  ────
# ─── el shape de columnas es el mismo, solo cambia la fuente de las filas) ───


def _normalizar_sexo(des: str | None) -> Sexo:
    """DES_GENERO viene como 'MASCULINO'/'FEMENINO'."""
    if des:
        u = des.upper().strip()
        if u.startswith("F") or "FEM" in u:
            return Sexo.F
        if u.startswith("M") or "MASC" in u:
            return Sexo.M
    return Sexo.M


def _normalizar_tipo_doc(des: str | None) -> TipoDocumento:
    """DES_TIPO_IDENTIFICACION viene como 'CEDULA DE CIUDADANIA', 'TARJETA DE IDENTIDAD', etc."""
    if not des:
        return TipoDocumento.CC
    u = des.upper().strip()
    if "CIUDAD" in u or u == "CC":
        return TipoDocumento.CC
    if "TARJETA" in u or u == "TI":
        return TipoDocumento.TI
    if "REGISTRO" in u or u == "RC":
        return TipoDocumento.RC
    if "EXTRANJ" in u or u == "CE":
        return TipoDocumento.CE
    if "PASAPORTE" in u or u == "PA":
        return TipoDocumento.PA
    if "MENOR SIN ID" in u or "MSI" in u or u == "MS":
        return TipoDocumento.MS
    return TipoDocumento.CC


def _normalizar_regimen(s: str | None) -> Regimen | None:
    if not s:
        return None
    u = s.upper().strip()
    if u == "CONTRIBUTIVO":
        return Regimen.CONTRIBUTIVO
    if u == "SUBSIDIADO":
        return Regimen.SUBSIDIADO
    if u == "VINCULADO":
        return Regimen.VINCULADO
    return None


def _parse_date(v: object) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _str_or_none(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.upper() == "NULL" or s.upper() == "NOTIENE":
        return None
    return s


def _int_or_none(v: object) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return None


def _row_a_registro(row, idx: dict[str, int]) -> RegistroVacuna | None:
    """Convierte una fila (tupla indexable por posición, ej. de pyodbc) a
    RegistroVacuna usando `idx` (nombre de columna -> posición). Devuelve None
    si la fila es inválida (faltan campos críticos) — se descarta y se cuenta,
    nunca se revienta el lote completo por una fila mala."""

    def g(col: str) -> object:
        i = idx.get(col)
        return row[i] if i is not None and i < len(row) else None

    fec_aplicacion = _parse_date(g("FEC_REGISTRO_INFORMACION"))
    fec_nac = _parse_date(g("FEC_NACIMIENTO_PERSONA"))
    seq = _int_or_none(g("SEQ_SERAGIL"))
    num_doc = _str_or_none(g("NRO_TIPO_IDENTIFICACION"))
    primer_nombre = _str_or_none(g("AFL_PRIMER_NOMBRE"))
    primer_apellido = _str_or_none(g("AFL_PRIMER_APELLIDO"))
    programa = _str_or_none(g("DES_PROGRAMA_DEMIND"))

    if not all([fec_aplicacion, fec_nac, seq, num_doc, primer_nombre, primer_apellido, programa]):
        return None

    try:
        return RegistroVacuna(
            seq_seragil=int(seq),  # type: ignore[arg-type]
            tipo_documento=_normalizar_tipo_doc(_str_or_none(g("DES_TIPO_IDENTIFICACION"))),
            num_documento=str(num_doc),
            tipo_identificacion_desc=_str_or_none(g("DES_TIPO_IDENTIFICACION")),
            primer_nombre=str(primer_nombre),
            segundo_nombre=_str_or_none(g("AFL_SEGUNDO_NOMBRE")),
            primer_apellido=str(primer_apellido),
            segundo_apellido=_str_or_none(g("AFL_SEGUNDO_APELLIDO")),
            sexo=_normalizar_sexo(_str_or_none(g("DES_GENERO"))),
            edad=_int_or_none(g("VLR_EDAD_ACTUAL")) or 0,
            fecha_nacimiento=fec_nac,  # type: ignore[arg-type]
            direccion=_str_or_none(g("DES_DIRECCION_ACTUAL")),
            telefono_1=_str_or_none(g("DES_TELEFONO_UNO")),
            telefono_2=_str_or_none(g("DES_TELEFONO_DOS")),
            correo=_str_or_none(g("DES_CORREO_ELECTRONICO")),
            departamento=_str_or_none(g("DES_DEPARTAMENTO")),
            municipio=_str_or_none(g("DES_MUNICIPIO")),
            zona_afiliado=_int_or_none(g("ZONA_AFILIADO")),
            curso_vida=_str_or_none(g("DES_CURSO_VIDA_ASOCIADO")),
            regimen=_normalizar_regimen(_str_or_none(g("REGIMEN"))),
            fecha_aplicacion=fec_aplicacion,  # type: ignore[arg-type]
            programa=str(programa),
            modo_ingreso=_str_or_none(g("DES_MODO_INGRESO")),
            encuestador=_str_or_none(g("ENCUESTADOR")),
            cargo_encuestador=_str_or_none(g("DES_CARGO_USUARIO")),
        )
    except Exception:
        log.exception("vacunacion.row_invalida seq=%s", seq)
        return None


# ─── SQL ──────────────────────────────────────────────────────────────────────

# Códigos de programa de vacunación (esquema regular + COVID-19) — dados por
# el área de Planeación/TIC, confirmados contra la consulta real en producción.
_COD_PROGRAMAS_VACUNACION = (
    "'01','02','03','04','05','06','07','08','09','10','89','90','91','92','93','94',"
    "'95','96','97','98','99','A2','A3','A4','A5','A6',"
    "'00','A1','B7'"
)

_FROM_JOINS = """
FROM AVS_REGISTRO_SERAGIL AS B
    INNER JOIN AVS_AFILIADO_MUTUALSER_HIS AS A ON (A.COD_TIPO_IDENTIFICACION = B.COD_TIPO_IDENTIFICACION_PERSONA
        AND A.NRO_TIPO_IDENTIFICACION = B.NUM_TIPO_IDENTIFICACION_PERSONA)
    LEFT JOIN AVS_CURSO_VIDA AS C ON B.COD_CURSO_VIDA_ASOCIADO = C.COD_CURSO_VIDA_ASOCIADO
    LEFT JOIN AVS_DEPARTAMENTO AS D ON A.COD_DEPARTAMENTO = D.COD_DEPARTAMENTO
    LEFT JOIN AVS_TIPO_IDENTIFICACION_USUARIO AS E ON A.COD_TIPO_IDENTIFICACION = E.COD_TIPO_IDENTIFICACION
    LEFT JOIN AVS_GENERO AS F ON A.COD_GENERO = F.COD_GENERO
    LEFT JOIN AVS_MUNICIPIO AS G ON A.COD_MUNICIPIO = G.COD_MUNICIPIO
    LEFT JOIN AVS_PRESTADOR_SERVICIOS AS H ON B.COD_IPS_AQUESE_REMITE = H.COD_PRESTADOR_SERVICIOS
    LEFT JOIN AVS_USUARIO_SISTEMA AS I ON B.SEQ_ENCUESTADOR_CARACTERIZACION = I.SEQ_USUARIO_SISTEMA
    LEFT JOIN AVS_EVENTO_NOTIFICACION AS J ON B.COD_EVENTO_NOTIFICACION_REMITE = J.COD_EVENTO_NOTIFICACION
    LEFT JOIN AVS_RIAS_GRUPO_RIESGO AS K ON B.COD_RIAS_GRUPO_RIESGO = K.COD_RIAS_GRUPO_RIESGO
    LEFT JOIN AVS_REMITENTE_INICIAL AS L ON B.COD_TIPO_REMITENTE_INICIAL = L.COD_REMITENTE_INICIAL
    LEFT JOIN AVS_CARGO_USUARIO AS M ON B.COD_CARGO_ENCUESTADOR = M.COD_CARGO_USUARIO
    INNER JOIN AVS_PROGRAMA_ASOCIADO_DEMIND AS O ON O.SEQ_SERAGIL = B.SEQ_SERAGIL
    INNER JOIN AVS_PROGRAMAS_DEMIND AS P ON O.COD_PROGRAMA_DEMIND = P.COD_PROGRAMA_DEMIND
"""


def _build_wheres(regimen: str | None) -> tuple[list[str], list]:
    """Single source of truth del WHERE — compartido entre COUNT y FETCH
    (evita que diverjan, mismo criterio que Educación Grupal/Captación)."""
    wheres = [
        "B.FLG_REGIND_DEMIND = 'SI'",
        "B.FEC_REGISTRO_INFORMACION >= ?",
        "B.FEC_REGISTRO_INFORMACION <= ?",
    ]
    params: list = []
    if regimen:
        wheres.append("A.AFIC_REGIMEN = ?")
        params.append("S" if regimen.upper() == "SUBSIDIADO" else "C")
    wheres.append(f"O.COD_PROGRAMA_DEMIND IN ({_COD_PROGRAMAS_VACUNACION})")
    return wheres, params


def _build_count_sql(regimen: str | None) -> str:
    wheres, _ = _build_wheres(regimen)
    where_clause = "\n      AND ".join(wheres)
    return f"SELECT COUNT(*) AS total {_FROM_JOINS} WHERE {where_clause}"


def _build_query_sql(regimen: str | None) -> str:
    wheres, _ = _build_wheres(regimen)
    where_str = "\n      AND ".join(wheres)
    return f"""
WITH X AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY B.SEQ_ENCUESTADOR_CARACTERIZACION ASC, B.FEC_REGISTRO_INFORMACION DESC
           ) AS NUM_REGISTRO,
           A.COD_TIPO_IDENTIFICACION, A.NRO_TIPO_IDENTIFICACION, B.SEQ_SERAGIL,
           A.AFL_PRIMER_NOMBRE, ISNULL(A.AFL_SEGUNDO_NOMBRE,'') AS AFL_SEGUNDO_NOMBRE,
           ISNULL(A.AFL_PRIMER_APELLIDO,'') AS AFL_PRIMER_APELLIDO,
           CONVERT(CHAR, B.FEC_REGISTRO_INFORMACION,23) AS FEC_REGISTRO_INFORMACION,
           ISNULL(A.AFL_SEGUNDO_APELLIDO,'') AS AFL_SEGUNDO_APELLIDO,
           A.COD_GENERO, A.COD_DEPARTAMENTO, A.COD_MUNICIPIO,
           CONVERT(CHAR(10),B.FEC_NACIMIENTO_PERSONA) AS FEC_NACIMIENTO_PERSONA,
           B.DES_DIRECCION_ACTUAL, A.ZONA_AFILIADO, B.DES_TELEFONO_UNO, B.DES_TELEFONO_DOS,
           B.DES_CORREO_ELECTRONICO, B.COD_IPS_AQUESE_REMITE, B.SEQ_ENCUESTADOR_CARACTERIZACION,
           ISNULL(E.DES_TIPO_IDENTIFICACION,'') AS DES_TIPO_IDENTIFICACION,
           ISNULL(D.DES_DEPARTAMENTO,'') AS DES_DEPARTAMENTO,
           ISNULL(G.DES_MUNICIPIO,'') AS DES_MUNICIPIO,
           ISNULL(F.DES_GENERO,'') AS DES_GENERO, M.DES_CARGO_USUARIO,
           ISNULL(C.DES_CURSO_VIDA_ASOCIADO,'') AS DES_CURSO_VIDA_ASOCIADO,
           ISNULL(J.DES_EVENTO_NOTIFICACION,'') AS DES_EVENTO_NOTIFICACION,
           B.FLG_NOTIFICACION_OBLIGATORIA, B.FLG_RECUPERACION_URGENCIAS,
           B.FLG_RECUPERACION_CONSULTA_EXTERNA, B.DES_OTRO_REMITENTE_INICIAL,
           ISNULL(K.DES_RIAS_GRUPO_RIESGO,'') AS DES_RIAS_GRUPO_RIESGO,
           ISNULL(H.DES_PRESTADOR_SERVICIOS,'') AS DES_PRESTADOR_SERVICIOS,
           ISNULL(B.DES_OTRA_RIAS_GRUPO_RIESGO,'') AS DES_OTRA_RIAS_GRUPO_RIESGO,
           ISNULL(L.DES_REMITENTE_INICIAL,'') AS DES_REMITENTE_INICIAL,
           REGIMEN = CASE
                        WHEN A.AFIC_REGIMEN = 'C' THEN 'CONTRIBUTIVO'
                        WHEN A.AFIC_REGIMEN = 'S' THEN 'SUBSIDIADO'
                        WHEN A.AFIC_REGIMEN = 'V' THEN 'VINCULADO'
                        ELSE '' END,
           I.TXT_PRIMER_NOMBRE+' '+ISNULL(I.TXT_SEGUNDO_NOMBRE,'')+' '+ISNULL(I.TXT_PRIMER_APELLIDO,'')+' '+ISNULL(I.TXT_SEGUNDO_APELLIDO,'') AS ENCUESTADOR,
           DATEDIFF(YEAR, B.FEC_NACIMIENTO_PERSONA, B.FEC_REGISTRO_INFORMACION) AS VLR_EDAD_ACTUAL,
           DES_MODO_INGRESO = CASE
                        WHEN B.FLG_MODO_INGRESO = 'CO' THEN 'COMUNIDAD'
                        WHEN B.FLG_MODO_INGRESO = 'TE' THEN 'TELEFONICO'
                        WHEN B.FLG_MODO_INGRESO = 'VI' THEN 'VIRTUAL'
                        ELSE '' END,
           O.COD_PROGRAMA_DEMIND, P.DES_PROGRAMA_DEMIND
    {_FROM_JOINS}
    WHERE {where_str}
)
SELECT X.SEQ_SERAGIL, X.DES_MODO_INGRESO, X.ENCUESTADOR, X.DES_CARGO_USUARIO, X.FEC_REGISTRO_INFORMACION,
       X.DES_DEPARTAMENTO, X.DES_MUNICIPIO, X.REGIMEN, X.AFL_PRIMER_NOMBRE, X.AFL_SEGUNDO_NOMBRE,
       X.AFL_PRIMER_APELLIDO, X.AFL_SEGUNDO_APELLIDO, X.DES_GENERO, X.FEC_NACIMIENTO_PERSONA, X.VLR_EDAD_ACTUAL,
       X.DES_TIPO_IDENTIFICACION, X.NRO_TIPO_IDENTIFICACION, X.DES_DIRECCION_ACTUAL, X.ZONA_AFILIADO,
       X.DES_TELEFONO_UNO, X.DES_TELEFONO_DOS, X.DES_CORREO_ELECTRONICO, X.DES_CURSO_VIDA_ASOCIADO,
       X.DES_EVENTO_NOTIFICACION, X.FLG_NOTIFICACION_OBLIGATORIA, X.FLG_RECUPERACION_URGENCIAS,
       X.FLG_RECUPERACION_CONSULTA_EXTERNA, X.DES_RIAS_GRUPO_RIESGO, X.DES_OTRA_RIAS_GRUPO_RIESGO,
       X.DES_REMITENTE_INICIAL, X.DES_OTRO_REMITENTE_INICIAL, X.DES_PROGRAMA_DEMIND
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""


def _fechas_dt(desde: date, hasta: date) -> tuple[datetime, datetime]:
    return (
        datetime(desde.year, desde.month, desde.day, 0, 0, 0),
        datetime(hasta.year, hasta.month, hasta.day, 23, 59, 59),
    )


# ─── Implementación SQL Server ────────────────────────────────────────────────


class SqlServerVacunacionRepository:
    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int:
        try:
            import pyodbc
        except ImportError as e:
            raise RepositorioNoDisponibleError("Driver pyodbc no instalado") from e
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = _build_count_sql(regimen)
        _, regimen_params = _build_wheres(regimen)
        full_params = [fecha_inicio, fecha_final, *regimen_params]
        try:
            with pyodbc.connect(settings.db_dsn, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(sql, *full_params)
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception as e:
            log.exception("vacunacion.get_total failed")
            raise RepositorioNoDisponibleError("No se pudo consultar SQL Server") from e

    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroVacuna]:
        try:
            import pyodbc
        except ImportError as e:
            raise RepositorioNoDisponibleError("Driver pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = _build_query_sql(regimen)
        _, regimen_params = _build_wheres(regimen)
        params: list = [fecha_inicio, fecha_final, *regimen_params, offset, limite]

        log.info("vacunacion.query", extra={"desde": str(desde), "hasta": str(hasta),
                                             "limite": limite, "offset": offset, "regimen": regimen})

        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(sql, *params)
            cols = [c[0] for c in cur.description]
            idx = {name: i for i, name in enumerate(cols)}
            rows = cur.fetchall()

        registros: list[RegistroVacuna] = []
        descartadas = 0
        for row in rows:
            r = _row_a_registro(row, idx)
            if r is None:
                descartadas += 1
                continue
            registros.append(r)

        log.info("vacunacion.fetched", extra={"rows": len(registros), "descartadas": descartadas})
        return registros


# ─── Mock ──────────────────────────────────────────────────────────────────────


class MockVacunacionRepository:
    """Datos ficticios para USE_MOCK=true — mismo patrón que los demás módulos
    de régimen simple (MockEducacionGrupalRepository)."""

    def get_total(self, desde: date, hasta: date, regimen: str | None = None) -> int:
        base = 300
        if regimen:
            base = base // 2
        return base

    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        regimen: str | None = None,
    ) -> list[RegistroVacuna]:
        import random
        from datetime import timedelta

        nombres = ["LUIS", "MARIA", "PEDRO", "ANA", "CARLOS", "SOFIA", "JUAN", "ELENA"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ"]
        regimenes = ["SUBSIDIADO", "CONTRIBUTIVO", "SUBSIDIADO", "SUBSIDIADO"]
        programas = ["VACUNACION VPH", "VACUNACION INFLUENZA", "VACUNACION COVID 19", "VACUNACION FIEBRE AMARILLA"]
        deptos = ["BOLIVAR", "ATLANTICO", "CORDOBA", "SUCRE"]
        municipios = ["CARTAGENA", "BARRANQUILLA", "MONTERIA", "SINCELEJO"]
        modos = ["COMUNIDAD", "TELEFONICO", "VIRTUAL"]

        registros: list[RegistroVacuna] = []
        dias = max((hasta - desde).days, 0)
        for i in range(limite):
            seq = offset + i + 1
            rng = random.Random(seq * 23)
            reg = rng.choice(regimenes)
            if regimen and reg != regimen.upper():
                continue
            fec_aplicacion = desde + timedelta(days=rng.randint(0, dias))
            fec_nac = date(rng.randint(1950, 2023), rng.randint(1, 12), rng.randint(1, 28))
            registros.append(RegistroVacuna(
                seq_seragil=seq,
                tipo_documento=TipoDocumento.CC,
                num_documento=str(1_000_000_000 + seq),
                tipo_identificacion_desc="CEDULA DE CIUDADANIA",
                primer_nombre=rng.choice(nombres),
                primer_apellido=rng.choice(apellidos),
                segundo_apellido=rng.choice(apellidos),
                sexo=rng.choice([Sexo.M, Sexo.F]),
                edad=max(0, min(120, fec_aplicacion.year - fec_nac.year)),
                fecha_nacimiento=fec_nac,
                departamento=rng.choice(deptos),
                municipio=rng.choice(municipios),
                zona_afiliado=rng.choice([1, 2]),
                regimen=_normalizar_regimen(reg),
                fecha_aplicacion=fec_aplicacion,
                programa=rng.choice(programas),
                modo_ingreso=rng.choice(modos),
                encuestador="ENCUESTADOR DE PRUEBA",
                cargo_encuestador="AUXILIAR DE ENFERMERIA",
            ))
        return registros


def get_vacunacion_repository() -> VacunacionRepository:
    if settings.use_mock:
        log.info("vacunacion repo: MOCK")
        return MockVacunacionRepository()
    log.info("vacunacion repo: SQL Server")
    return SqlServerVacunacionRepository()
