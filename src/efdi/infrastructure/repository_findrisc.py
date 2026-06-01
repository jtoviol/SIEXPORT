"""Repositorio FINDRISC — abstrae origen de datos para evaluaciones de riesgo de diabetes."""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import RegistroFindrisc, TipoDocumento

log = logging.getLogger(__name__)


class FindriscRepository(Protocol):
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0
    ) -> list[RegistroFindrisc]: ...

    def get_total(self, desde: date, hasta: date) -> int: ...


# === Query principal paginada ================================================

QUERY_FINDRISC = """
WITH X AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY B.SEQ_ENCUESTADOR_CARACTERIZACION ASC,
                        J.FEC_REALIZACION DESC
           ) AS NUM_REGISTRO,
           A.COD_TIPO_IDENTIFICACION,
           A.NRO_TIPO_IDENTIFICACION, B.SEQ_SERAGIL,
           A.AFL_PRIMER_NOMBRE, ISNULL(A.AFL_SEGUNDO_NOMBRE,'') AS AFL_SEGUNDO_NOMBRE,
           ISNULL(A.AFL_PRIMER_APELLIDO,'') AS AFL_PRIMER_APELLIDO,
           CONVERT(CHAR(10),J.FEC_REALIZACION) AS FEC_REALIZACION,
           CONVERT(CHAR(10), J.FEC_REGISTRO_INFORMACION) AS FEC_REGISTRO_INFORMACION,
           ISNULL(A.AFL_SEGUNDO_APELLIDO,'') AS AFL_SEGUNDO_APELLIDO,
           A.COD_GENERO, A.COD_DEPARTAMENTO, A.COD_MUNICIPIO,
           CONVERT(CHAR(10),B.FEC_NACIMIENTO_PERSONA) AS FEC_NACIMIENTO_PERSONA,
           B.DES_DIRECCION_ACTUAL, B.DES_TELEFONO_UNO,
           B.DES_CORREO_ELECTRONICO, B.COD_IPS_AQUESE_REMITE, B.SEQ_ENCUESTADOR_CARACTERIZACION,
           ISNULL(E.DES_TIPO_IDENTIFICACION,'') AS DES_TIPO_IDENTIFICACION,
           ISNULL(D.DES_DEPARTAMENTO,'') AS DES_DEPARTAMENTO,
           ISNULL(G.DES_MUNICIPIO,'') AS DES_MUNICIPIO,
           ISNULL(F.DES_GENERO,'') AS DES_GENERO, M.DES_CARGO_USUARIO,
           ISNULL(C.DES_CURSO_VIDA_ASOCIADO,'') AS DES_CURSO_VIDA_ASOCIADO,
           I.TXT_PRIMER_NOMBRE+' '+ ISNULL(I.TXT_SEGUNDO_NOMBRE, '')+' '
               +ISNULL(I.TXT_PRIMER_APELLIDO,'')+' '+ ISNULL(I.TXT_SEGUNDO_APELLIDO,'') AS ENCUESTADOR,
           J.VLR_EDAD_ACTUAL, J.VLR_PESO, J.VLR_TALLA, J.VLR_IMC, J.VLR_PERIMETRO_CINTURA,
           J.FLG_ACTIVIDA_FISICA,
           VLR_FRECUENCIA_VERDURAS = CASE
               WHEN (J.VLR_FRECUENCIA_VERDURAS) = 1 THEN 'TODOS LOS DIAS'
               ELSE 'NO TODOS LOS DIAS'
           END,
           J.FLG_MEDICAMENTOS_HIPERTENSION,
           J.FLG_GLUCOSA_ALTA,
           FLG_DIABETIS = CASE
               WHEN (J.FLG_DIABETIS) = '01' THEN 'SI PADRES O HERMANOS'
               WHEN (J.FLG_DIABETIS) = '02' THEN 'SI ABUELOS O TIOS O PRIMOS HERMANOS'
               ELSE 'OTROS PARIENTES O NINGUNO'
           END,
           J.VLR_PUNTAJE_EDAD, J.VLR_PUNTAJE_IMC,
           J.VLR_PUNTAJE_PERIMETRO_ABDOMINAL, J.VLR_PUNTAJE_ACTIVIDAD_FISICA,
           J.VLR_PUNTAJE_FRECUENCIA_VERDURAS, J.VLR_PUNTAJE_MEDICAMENTOS,
           J.VLR_PUNTAJE_GLUCOSA, J.VLR_PUNTAJE_DIABETIS, J.VLR_PUNTAJE_OBTENIDO,
           J.FLG_APLICA_XA_PRUEBA,
           ISNULL(N.cod_regional,'') AS COD_REGIONAL,
           ISNULL(O.des_regional,'') AS DES_REGIONAL,
           ISNULL(P.DES_PRESTADOR_SERVICIOS,'') AS DES_PRESTADOR_SERVICIOS,
           ISNULL(Q.DES_TIPO_REGIMEN,'') AS DES_TIPO_REGIMEN
    FROM  AVS_REGISTRO_SERAGIL AS B
    LEFT JOIN AVS_AFILIADO_MUTUALSER_HIS AS A
        ON A.COD_TIPO_IDENTIFICACION = B.COD_TIPO_IDENTIFICACION_PERSONA
       AND A.NRO_TIPO_IDENTIFICACION = B.NUM_TIPO_IDENTIFICACION_PERSONA
    LEFT JOIN AVS_CURSO_VIDA AS C ON C.COD_CURSO_VIDA_ASOCIADO = B.COD_CURSO_VIDA_ASOCIADO
    LEFT JOIN AVS_DEPARTAMENTO AS D ON D.COD_DEPARTAMENTO = A.COD_DEPARTAMENTO
    LEFT JOIN AVS_TIPO_IDENTIFICACION_USUARIO AS E ON E.COD_TIPO_IDENTIFICACION = A.COD_TIPO_IDENTIFICACION
    LEFT JOIN AVS_GENERO AS F ON F.COD_GENERO = A.COD_GENERO
    LEFT JOIN AVS_MUNICIPIO AS G ON G.COD_MUNICIPIO = A.COD_MUNICIPIO
    LEFT JOIN AVS_USUARIO_SISTEMA AS I ON I.SEQ_USUARIO_SISTEMA = B.SEQ_ENCUESTADOR_CARACTERIZACION
    JOIN  SRG_FORMATO_FINDRISC AS J ON J.SEQ_SERAGIL = B.SEQ_SERAGIL
    LEFT JOIN AVS_CARGO_USUARIO AS M ON M.COD_CARGO_USUARIO = B.COD_CARGO_ENCUESTADOR
    LEFT JOIN avs_regional_usuario AS N ON N.seq_usuario_sistema = B.SEQ_ENCUESTADOR_CARACTERIZACION
    LEFT JOIN avs_regional AS O ON O.cod_regional = N.cod_regional
    LEFT JOIN AVS_PRESTADOR_SERVICIOS P ON P.COD_PRESTADOR_SERVICIOS = B.COD_IPS_AQUESE_REMITE
    LEFT JOIN AVS_TIPO_REGIMEN_SGSSS Q ON Q.COD_TIPO_REGIMEN = A.AFIC_REGIMEN
    WHERE B.FLG_FORMATO_COLDRISC = 'SI'
      AND B.FEC_REGISTRO_INFORMACION >= ?
      AND B.FEC_REGISTRO_INFORMACION <= ?
)
SELECT X.COD_TIPO_IDENTIFICACION, X.NRO_TIPO_IDENTIFICACION, X.SEQ_SERAGIL, X.NUM_REGISTRO,
       X.DES_REGIONAL, X.ENCUESTADOR, X.DES_CARGO_USUARIO,
       X.FEC_REALIZACION, X.FEC_REGISTRO_INFORMACION,
       X.DES_DEPARTAMENTO, X.DES_MUNICIPIO, X.DES_PRESTADOR_SERVICIOS,
       X.AFL_PRIMER_NOMBRE, X.AFL_SEGUNDO_NOMBRE, X.AFL_PRIMER_APELLIDO, X.AFL_SEGUNDO_APELLIDO,
       X.FEC_NACIMIENTO_PERSONA, X.DES_TIPO_IDENTIFICACION,
       X.DES_DIRECCION_ACTUAL, X.DES_TELEFONO_UNO, X.DES_CORREO_ELECTRONICO,
       X.DES_CURSO_VIDA_ASOCIADO, X.VLR_EDAD_ACTUAL, X.DES_GENERO,
       X.VLR_PESO, X.VLR_TALLA, X.VLR_IMC, X.VLR_PERIMETRO_CINTURA,
       X.FLG_ACTIVIDA_FISICA, X.VLR_FRECUENCIA_VERDURAS,
       X.FLG_MEDICAMENTOS_HIPERTENSION, X.FLG_GLUCOSA_ALTA, X.FLG_DIABETIS,
       X.FLG_APLICA_XA_PRUEBA,
       X.VLR_PUNTAJE_EDAD, X.VLR_PUNTAJE_IMC, X.VLR_PUNTAJE_PERIMETRO_ABDOMINAL,
       X.VLR_PUNTAJE_ACTIVIDAD_FISICA, X.VLR_PUNTAJE_FRECUENCIA_VERDURAS,
       X.VLR_PUNTAJE_MEDICAMENTOS, X.VLR_PUNTAJE_GLUCOSA,
       X.VLR_PUNTAJE_DIABETIS, X.VLR_PUNTAJE_OBTENIDO,
       X.DES_TIPO_REGIMEN
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_FINDRISC_COUNT = """
SELECT COUNT(DISTINCT B.SEQ_SERAGIL) AS total
FROM AVS_REGISTRO_SERAGIL AS B
JOIN SRG_FORMATO_FINDRISC AS J ON J.SEQ_SERAGIL = B.SEQ_SERAGIL
WHERE B.FLG_FORMATO_COLDRISC = 'SI'
  AND B.FEC_REGISTRO_INFORMACION >= ?
  AND B.FEC_REGISTRO_INFORMACION <= ?
"""


def _to_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    if isinstance(v, str):
        return v.upper() in ("SI", "S", "1", "TRUE", "YES")
    return False


def _to_int(v: object, default: int = 0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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


def _normalizar_tipo_doc(cod: str | None) -> TipoDocumento:
    if not cod:
        return TipoDocumento.CC
    c = cod.upper().strip()
    try:
        return TipoDocumento(c)
    except ValueError:
        return TipoDocumento.CC


class MockFindriscRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0
    ) -> list[RegistroFindrisc]:
        import random
        from datetime import timedelta
        rng = random.Random(offset * 7 + limite)
        registros = []
        nombres = ["CARLOS", "MARIA", "JOSE", "ANA", "LUIS", "CARMEN", "PEDRO", "ROSA"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
        for i in range(limite):
            seq = offset + i + 1
            rng2 = random.Random(seq * 13)
            edad = rng2.randint(18, 75)
            peso = round(rng2.uniform(50, 110), 1)
            talla = round(rng2.uniform(1.50, 1.85), 2)
            imc = round(peso / (talla ** 2), 1)
            cintura = round(rng2.uniform(70, 110), 1)
            actividad = rng2.random() > 0.5
            verduras = rng2.random() > 0.4
            medicamentos = rng2.random() > 0.6
            glucosa = rng2.random() > 0.7
            diab_opts = ["OTROS PARIENTES O NINGUNO", "SI PADRES O HERMANOS", "SI ABUELOS O TIOS O PRIMOS HERMANOS"]
            antecedente = rng2.choice(diab_opts)

            p_edad = 0 if edad < 45 else (2 if edad < 55 else (3 if edad < 65 else 4))
            p_imc = 0 if imc < 25 else (1 if imc < 30 else 3)
            p_cintura = 0 if cintura < 80 else (3 if cintura < 90 else 4)
            p_actividad = 0 if actividad else 2
            p_verduras = 0 if verduras else 1
            p_med = 0 if not medicamentos else 2
            p_glucosa = 0 if not glucosa else 5
            p_diab = {"OTROS PARIENTES O NINGUNO": 0, "SI ABUELOS O TIOS O PRIMOS HERMANOS": 3, "SI PADRES O HERMANOS": 5}[antecedente]
            total = p_edad + p_imc + p_cintura + p_actividad + p_verduras + p_med + p_glucosa + p_diab

            fecha_reg = desde + timedelta(days=rng2.randint(0, (hasta - desde).days))
            registros.append(RegistroFindrisc(
                seq_seragil=seq,
                consecutivo=seq,
                tipo_documento=TipoDocumento.CC,
                num_documento=str(1000000 + seq),
                primer_nombre=rng2.choice(nombres),
                primer_apellido=rng2.choice(apellidos),
                edad=edad,
                genero="Femenino" if rng2.random() > 0.5 else "Masculino",
                fecha_registro=fecha_reg,
                fecha_realizacion=fecha_reg,
                peso=peso, talla=talla, imc=imc, perimetro_cintura=cintura,
                actividad_fisica=actividad,
                frecuencia_verduras="TODOS LOS DIAS" if verduras else "NO TODOS LOS DIAS",
                medicamentos_hipertension=medicamentos,
                glucosa_alta=glucosa,
                antecedente_diabetes=antecedente,
                aplica_prueba=total >= 12,
                puntaje_edad=p_edad, puntaje_imc=p_imc, puntaje_perimetro=p_cintura,
                puntaje_actividad_fisica=p_actividad, puntaje_verduras=p_verduras,
                puntaje_medicamentos=p_med, puntaje_glucosa=p_glucosa,
                puntaje_diabetes=p_diab, puntaje_total=total,
            ))
        return registros

    def get_total(self, desde: date, hasta: date) -> int:
        return 500


class SqlServerFindriscRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0
    ) -> list[RegistroFindrisc]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        log.info("findrisc.query", extra={"desde": str(desde), "hasta": str(hasta), "limite": limite, "offset": offset})

        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(QUERY_FINDRISC, fecha_inicio, fecha_final, offset, limite)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        registros: list[RegistroFindrisc] = []
        for r in rows:
            fec_reg = _parse_date(r.get("FEC_REGISTRO_INFORMACION"))
            if not fec_reg:
                log.warning("findrisc: fila descartada por fecha inválida: %s", r.get("SEQ_SERAGIL"))
                continue
            registros.append(RegistroFindrisc(
                seq_seragil=int(r["SEQ_SERAGIL"]),
                consecutivo=int(r.get("NUM_REGISTRO") or 0),
                tipo_documento=_normalizar_tipo_doc(r.get("COD_TIPO_IDENTIFICACION")),
                num_documento=str(r.get("NRO_TIPO_IDENTIFICACION") or "").strip(),
                primer_nombre=(r.get("AFL_PRIMER_NOMBRE") or "").strip(),
                segundo_nombre=(r.get("AFL_SEGUNDO_NOMBRE") or "").strip() or None,
                primer_apellido=(r.get("AFL_PRIMER_APELLIDO") or "").strip(),
                segundo_apellido=(r.get("AFL_SEGUNDO_APELLIDO") or "").strip() or None,
                fecha_nacimiento=_parse_date(r.get("FEC_NACIMIENTO_PERSONA")),
                edad=_to_int(r.get("VLR_EDAD_ACTUAL")),
                genero=(r.get("DES_GENERO") or "").strip() or None,
                fecha_realizacion=_parse_date(r.get("FEC_REALIZACION")),
                fecha_registro=fec_reg,
                direccion=(r.get("DES_DIRECCION_ACTUAL") or "").strip() or None,
                telefono_1=(r.get("DES_TELEFONO_UNO") or "").strip() or None,
                correo=(r.get("DES_CORREO_ELECTRONICO") or "").strip() or None,
                departamento=(r.get("DES_DEPARTAMENTO") or "").strip() or None,
                municipio=(r.get("DES_MUNICIPIO") or "").strip() or None,
                curso_vida=(r.get("DES_CURSO_VIDA_ASOCIADO") or "").strip() or None,
                regimen=(r.get("DES_TIPO_REGIMEN") or "").strip() or None,
                ips=(r.get("DES_PRESTADOR_SERVICIOS") or "").strip() or None,
                regional=(r.get("DES_REGIONAL") or "").strip() or None,
                encuestador_nombre=(r.get("ENCUESTADOR") or "").strip() or None,
                cargo_encuestador=(r.get("DES_CARGO_USUARIO") or "").strip() or None,
                peso=_to_float(r.get("VLR_PESO")),
                talla=_to_float(r.get("VLR_TALLA")),
                imc=_to_float(r.get("VLR_IMC")),
                perimetro_cintura=_to_float(r.get("VLR_PERIMETRO_CINTURA")),
                actividad_fisica=_to_bool(r.get("FLG_ACTIVIDA_FISICA")),
                frecuencia_verduras=(r.get("VLR_FRECUENCIA_VERDURAS") or "").strip() or None,
                medicamentos_hipertension=_to_bool(r.get("FLG_MEDICAMENTOS_HIPERTENSION")),
                glucosa_alta=_to_bool(r.get("FLG_GLUCOSA_ALTA")),
                antecedente_diabetes=(r.get("FLG_DIABETIS") or "").strip() or None,
                aplica_prueba=_to_bool(r.get("FLG_APLICA_XA_PRUEBA")),
                puntaje_edad=_to_int(r.get("VLR_PUNTAJE_EDAD")),
                puntaje_imc=_to_int(r.get("VLR_PUNTAJE_IMC")),
                puntaje_perimetro=_to_int(r.get("VLR_PUNTAJE_PERIMETRO_ABDOMINAL")),
                puntaje_actividad_fisica=_to_int(r.get("VLR_PUNTAJE_ACTIVIDAD_FISICA")),
                puntaje_verduras=_to_int(r.get("VLR_PUNTAJE_FRECUENCIA_VERDURAS")),
                puntaje_medicamentos=_to_int(r.get("VLR_PUNTAJE_MEDICAMENTOS")),
                puntaje_glucosa=_to_int(r.get("VLR_PUNTAJE_GLUCOSA")),
                puntaje_diabetes=_to_int(r.get("VLR_PUNTAJE_DIABETIS")),
                puntaje_total=_to_int(r.get("VLR_PUNTAJE_OBTENIDO")),
            ))

        log.info("findrisc.fetched", extra={"rows": len(registros)})
        return registros

    def get_total(self, desde: date, hasta: date) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        try:
            with pyodbc.connect(settings.db_dsn, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(QUERY_FINDRISC_COUNT, fecha_inicio, fecha_final)
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            log.exception("findrisc.get_total failed")
            return 0


def get_findrisc_repository() -> FindriscRepository:
    if settings.use_mock:
        return MockFindriscRepository()
    return SqlServerFindriscRepository()
