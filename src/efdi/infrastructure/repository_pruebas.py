"""Repositorio Pruebas Rápidas — abstrae origen de datos para respuestas de
pruebas rápidas (VIH, Sífilis, Hepatitis, Embarazo, PSA, Hb glicosilada, etc.).

Query basada en el SP `prGeneraRips` cursor `cuPruebaRapida`:
    FROM srg_respuesta_prueba_rapida a (registros 1:1 con afiliado)
    JOIN  srg_prueba_rapida           b (catálogo finito de pruebas)
    JOIN  AVS_AFILIADO_MUTUALSER_HIS  c

Diferencia clave con DI/FINDRISC/PlanFami: el CIEX y CUPS NO son fijos por
módulo — vienen del catálogo `srg_prueba_rapida` (varían por prueba). Por eso
el `_FACTURA_EXISTS_PRUEBAS` filtra AP con un IN dinámico:
    cod_diag_principal IN (SELECT DISTINCT ciex_asociado FROM srg_prueba_rapida)
"""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import RespuestaPruebaRapida, TipoDocumento

log = logging.getLogger(__name__)


class PruebasRapidasRepository(Protocol):
    def obtener_respuestas(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RespuestaPruebaRapida]: ...

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int: ...


# === Query principal paginada ================================================
#
# COUNT(*) y FETCH miden la MISMA unidad (filas-respuesta): el INNER JOIN a
# SRG_RESPUESTA_PRUEBA_RAPIDA multiplica encuestas Seragil cuando una persona
# se hizo varias pruebas en una sesión (ej. en la misma visita le hacen VIH +
# Sífilis + Hepatitis). Sin COUNT(*) el _auto_tamano_lote subestimaría como
# pasó en DI/PlanFami (ver memoria project-count-vs-fetch-bug).

QUERY_PRUEBAS = """
WITH X AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY B.FEC_REGISTRO_INFORMACION DESC,
                        O.SEQ_RESPUESTA_PRUEBA_RAPIDA ASC
           ) AS NUM_REGISTRO,
           A.COD_TIPO_IDENTIFICACION, A.NRO_TIPO_IDENTIFICACION, B.SEQ_SERAGIL,
           O.SEQ_RESPUESTA_PRUEBA_RAPIDA, O.SEQ_PRUEBA_RAPIDA,
           A.AFL_PRIMER_NOMBRE, ISNULL(A.AFL_SEGUNDO_NOMBRE,'') AS AFL_SEGUNDO_NOMBRE,
           ISNULL(A.AFL_PRIMER_APELLIDO,'') AS AFL_PRIMER_APELLIDO,
           ISNULL(A.AFL_SEGUNDO_APELLIDO,'') AS AFL_SEGUNDO_APELLIDO,
           CONVERT(CHAR(10), B.FEC_REGISTRO_INFORMACION, 23) AS FEC_REGISTRO_INFORMACION,
           CONVERT(CHAR(10), O.FEC_REALIZACION, 23) AS FEC_REALIZACION,
           A.COD_GENERO, A.COD_DEPARTAMENTO, A.COD_MUNICIPIO,
           CONVERT(CHAR(10),B.FEC_NACIMIENTO_PERSONA, 23) AS FEC_NACIMIENTO_PERSONA,
           B.DES_DIRECCION_ACTUAL, B.DES_TELEFONO_UNO, B.DES_TELEFONO_DOS,
           B.DES_CORREO_ELECTRONICO, B.SEQ_ENCUESTADOR_CARACTERIZACION,
           ISNULL(E.DES_TIPO_IDENTIFICACION,'') AS DES_TIPO_IDENTIFICACION,
           ISNULL(D.DES_DEPARTAMENTO,'') AS DES_DEPARTAMENTO,
           ISNULL(G.DES_MUNICIPIO,'') AS DES_MUNICIPIO,
           B.FLG_GESTANTE,
           ISNULL(F.DES_GENERO,'') AS DES_GENERO,
           M.DES_CARGO_USUARIO,
           ISNULL(I.TXT_PRIMER_NOMBRE,'')+' '+ ISNULL(I.TXT_SEGUNDO_NOMBRE,'')+' '
               +ISNULL(I.TXT_PRIMER_APELLIDO,'')+' '+ ISNULL(I.TXT_SEGUNDO_APELLIDO,'') AS ENCUESTADOR,
           DATEDIFF(YEAR, B.FEC_NACIMIENTO_PERSONA, B.FEC_REGISTRO_INFORMACION) AS VLR_EDAD_ACTUAL,
           P.DES_PRUEBA_RAPIDA,
           RESULTADO_PRUEBA = CASE
                                  WHEN O.RESULTADO_PRUEBA = 'NE' THEN 'NEGATIVA'
                                  WHEN O.RESULTADO_PRUEBA = 'PO' THEN 'POSITIVA'
                                  ELSE O.RESULTADO_PRUEBA
                              END,
           ISNULL(O.NRO_LOTE,'') AS NRO_LOTE,
           ISNULL(O.OBSERVACION,'') AS OBSERVACION,
           ISNULL(B.PRESION_ARTERIAL,'') AS PRESION_ARTERIAL
    FROM  AVS_REGISTRO_SERAGIL AS B
    INNER JOIN SRG_RESPUESTA_PRUEBA_RAPIDA AS O
        ON O.SEQ_SERAGIL = B.SEQ_SERAGIL
    INNER JOIN SRG_PRUEBA_RAPIDA AS P
        ON P.SEQ_PRUEBA_RAPIDA = O.SEQ_PRUEBA_RAPIDA
    LEFT JOIN AVS_AFILIADO_MUTUALSER_HIS AS A
        ON A.COD_TIPO_IDENTIFICACION = B.COD_TIPO_IDENTIFICACION_PERSONA
       AND A.NRO_TIPO_IDENTIFICACION = B.NUM_TIPO_IDENTIFICACION_PERSONA
    LEFT JOIN AVS_DEPARTAMENTO AS D ON D.COD_DEPARTAMENTO = A.COD_DEPARTAMENTO
    LEFT JOIN AVS_TIPO_IDENTIFICACION_USUARIO AS E ON E.COD_TIPO_IDENTIFICACION = A.COD_TIPO_IDENTIFICACION
    LEFT JOIN AVS_GENERO AS F ON F.COD_GENERO = A.COD_GENERO
    LEFT JOIN AVS_MUNICIPIO AS G ON G.COD_MUNICIPIO = A.COD_MUNICIPIO
    LEFT JOIN AVS_USUARIO_SISTEMA AS I ON I.SEQ_USUARIO_SISTEMA = B.SEQ_ENCUESTADOR_CARACTERIZACION
    LEFT JOIN AVS_CARGO_USUARIO AS M ON M.COD_CARGO_USUARIO = B.COD_CARGO_ENCUESTADOR
    WHERE B.FLG_PRUEBA_RAPIDA = 'SI'
      AND B.FEC_REGISTRO_INFORMACION >= ?
      AND B.FEC_REGISTRO_INFORMACION <= ?
      {factura_filter}
)
SELECT
    X.SEQ_SERAGIL,
    X.SEQ_RESPUESTA_PRUEBA_RAPIDA,
    X.SEQ_PRUEBA_RAPIDA,
    X.COD_TIPO_IDENTIFICACION,
    X.NRO_TIPO_IDENTIFICACION                                                AS [Numero de identificacion],
    X.AFL_PRIMER_NOMBRE,
    X.AFL_SEGUNDO_NOMBRE,
    X.AFL_PRIMER_APELLIDO,
    X.AFL_SEGUNDO_APELLIDO,
    CONCAT(X.AFL_PRIMER_NOMBRE, ' ', X.AFL_SEGUNDO_NOMBRE, ' ',
           X.AFL_PRIMER_APELLIDO, ' ', X.AFL_SEGUNDO_APELLIDO)              AS [Nombre del Afiliado],
    X.DES_GENERO                                                            AS Sexo,
    X.VLR_EDAD_ACTUAL                                                        AS [Edad Actual],
    X.FEC_NACIMIENTO_PERSONA,
    X.FEC_REGISTRO_INFORMACION,
    X.FEC_REALIZACION,
    X.DES_DEPARTAMENTO                                                       AS Departamento,
    X.DES_MUNICIPIO                                                          AS Municipio,
    X.DES_DIRECCION_ACTUAL                                                   AS Direccion,
    X.DES_TIPO_IDENTIFICACION                                                AS [Tipo de identificacion],
    X.DES_TELEFONO_UNO                                                       AS [Telefono 1],
    X.DES_TELEFONO_DOS                                                       AS [Telefono 2],
    X.DES_CORREO_ELECTRONICO                                                 AS [Correo electronico],
    X.FLG_GESTANTE,
    X.ENCUESTADOR,
    X.DES_CARGO_USUARIO                                                      AS [Cargo encuestador],
    X.PRESION_ARTERIAL,
    X.DES_PRUEBA_RAPIDA                                                      AS [Prueba],
    X.RESULTADO_PRUEBA                                                       AS [Resultado],
    X.NRO_LOTE                                                               AS [Lote],
    X.OBSERVACION                                                            AS [Observacion]
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""


QUERY_PRUEBAS_COUNT = """
SELECT COUNT(*) AS total
FROM AVS_REGISTRO_SERAGIL AS B
INNER JOIN SRG_RESPUESTA_PRUEBA_RAPIDA AS O ON O.SEQ_SERAGIL = B.SEQ_SERAGIL
INNER JOIN SRG_PRUEBA_RAPIDA AS P ON P.SEQ_PRUEBA_RAPIDA = O.SEQ_PRUEBA_RAPIDA
LEFT JOIN AVS_AFILIADO_MUTUALSER_HIS AS A
    ON A.COD_TIPO_IDENTIFICACION = B.COD_TIPO_IDENTIFICACION_PERSONA
   AND A.NRO_TIPO_IDENTIFICACION = B.NUM_TIPO_IDENTIFICACION_PERSONA
WHERE B.FLG_PRUEBA_RAPIDA = 'SI'
  AND B.FEC_REGISTRO_INFORMACION >= ?
  AND B.FEC_REGISTRO_INFORMACION <= ?
  {factura_filter}
"""


# Fragmento EXISTS contra AVS_REGISTROS_AP — mismo patrón que DI/FINDRISC/PlanFami
# pero con subquery dinámica al catálogo srg_prueba_rapida en vez de un CIEX fijo.
# El catálogo trae 5 CIEX (Z320, Z114, Z113, Z125, E119) y ninguno choca con
# Z048 (DI) / Z131 (FINDRISC) / Z309 (PlanFami) — si mañana agregan otra prueba
# al catálogo, el filtro la absorbe sin tocar código.
_FACTURA_EXISTS_PRUEBAS = """AND EXISTS (
    SELECT 1 FROM AVS_REGISTROS_AP r_ap
    WHERE r_ap.NUM_TIPO_IDENTIFICACION = A.NRO_TIPO_IDENTIFICACION
      AND r_ap.COD_TIPO_IDENTIFICACION = A.COD_TIPO_IDENTIFICACION
      AND r_ap.NRO_FACTURA IN ({placeholders})
      AND r_ap.cod_diag_principal IN (
          SELECT DISTINCT ciex_asociado
          FROM SRG_PRUEBA_RAPIDA
          WHERE ciex_asociado IS NOT NULL AND ciex_asociado <> ''
      )
)"""


def _factura_filter_pruebas(facturas: list[str] | None) -> str:
    """Devuelve el fragmento EXISTS con N placeholders, o cadena vacía."""
    if not facturas:
        return ""
    placeholders = ",".join("?" * len(facturas))
    return _FACTURA_EXISTS_PRUEBAS.format(placeholders=placeholders)


# ─── helpers de parseo ────────────────────────────────────────────────────────

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


def _str(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ═══════════════════════════════════════════════════════════════════════════
# Mock — genera respuestas sintéticas usando el catálogo real de pruebas
# ═══════════════════════════════════════════════════════════════════════════

_CATALOGO_MOCK = [
    (1, "PRUEBA DE EMBARAZO",        "F"),
    (2, "PRUEBA DE VIH1",            "A"),
    (3, "PRUEBA DE HEPATITIS B",     "A"),
    (4, "PRUEBA DE SIFILIS",         "A"),
    (5, "PRUEBA DE VIH2",            "A"),
    (6, "PRUEBA PSA",                "M"),
    (7, "HEMOGLOBINA GLICOSILADA",   "A"),
]


class MockPruebasRapidasRepository:
    def obtener_respuestas(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RespuestaPruebaRapida]:
        import random
        from datetime import timedelta
        out: list[RespuestaPruebaRapida] = []
        nombres = ["CARLOS", "MARIA", "JOSE", "ANA", "LUIS", "CARMEN", "PEDRO", "ROSA"]
        segundos = ["", "ANDRES", "ELENA", "JOSE", "MIGUEL", "ISABEL"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
        municipios = ["CARTAGENA", "BARRANQUILLA", "MONTERIA", "SINCELEJO", "VALLEDUPAR", "SANTA MARTA"]
        for i in range(limite):
            seq = offset + i + 1
            rng = random.Random(seq * 31)
            edad = rng.randint(18, 75)
            sexo_letra = rng.choice(["M", "F"])
            sexo_desc = "Masculino" if sexo_letra == "M" else "Femenino"

            # Selección de prueba respetando género del catálogo
            pruebas_disponibles = [
                p for p in _CATALOGO_MOCK
                if p[2] == "A" or p[2] == sexo_letra
            ]
            seq_prueba, des_prueba, _ = rng.choice(pruebas_disponibles)
            resultado = rng.choice(["NEGATIVA", "POSITIVA"])

            fecha_real = desde + timedelta(days=rng.randint(0, max((hasta - desde).days, 0)))
            n1, n2 = rng.choice(nombres), rng.choice(segundos)
            a1, a2 = rng.choice(apellidos), rng.choice(apellidos)
            nombre_full = " ".join(p for p in [n1, n2, a1, a2] if p).strip()
            num_doc = str(1000000 + seq)

            # Simular afiliado más jóven (gestante posible si F)
            es_gestante = sexo_letra == "F" and rng.random() > 0.85

            out.append(RespuestaPruebaRapida(
                seq_seragil=seq,
                seq_respuesta=seq * 10,
                seq_prueba_rapida=seq_prueba,
                tipo_documento=TipoDocumento.CC,
                fecha_realizacion=fecha_real,
                fecha_registro=fecha_real,
                nombre_completo=nombre_full,
                primer_nombre=n1,
                segundo_nombre=n2 or None,
                primer_apellido=a1,
                segundo_apellido=a2,
                sexo=sexo_desc,
                edad=edad,
                fec_nacimiento=None,
                tipo_identificacion_desc="CEDULA DE CIUDADANIA",
                num_documento=num_doc,
                departamento="BOLIVAR",
                municipio=rng.choice(municipios),
                direccion=f"CALLE {rng.randint(1, 99)} # {rng.randint(1, 50)}-{rng.randint(1, 99)}",
                telefono_1=f"30{rng.randint(0, 9)}{rng.randint(1000000, 9999999)}",
                telefono_2=f"60{rng.randint(1, 8)}{rng.randint(1000000, 9999999)}" if rng.random() > 0.5 else None,
                correo=f"{n1.lower()}.{a1.lower()}@example.com",
                flg_gestante=es_gestante,
                encuestador=f"USUARIO_{rng.randint(1, 20)}",
                cargo_encuestador="GESTOR DE SALUD",
                presion_arterial=f"{rng.randint(100, 140)}/{rng.randint(60, 90)}",
                des_prueba_rapida=des_prueba,
                resultado_prueba=resultado,
                nro_lote=f"LOTE-{rng.randint(1000, 9999)}",
                observacion="Sin observaciones." if rng.random() > 0.3 else "",
            ))

        if facturas:
            # Mock del cruce: ~50% determinista por seq_seragil
            out = [r for r in out if r.seq_seragil % 2 == 0]
        return out

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        return 180 if facturas else 360


# ═══════════════════════════════════════════════════════════════════════════
# SqlServer — implementación real contra Seragil
# ═══════════════════════════════════════════════════════════════════════════

class SqlServerPruebasRapidasRepository:
    def obtener_respuestas(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RespuestaPruebaRapida]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_PRUEBAS.format(factura_filter=_factura_filter_pruebas(facturas))
        params: list = [fecha_inicio, fecha_final]
        if facturas:
            params.extend(facturas)
        params.extend([offset, limite])
        log.info("pruebas.query", extra={"desde": str(desde), "hasta": str(hasta),
                                         "limite": limite, "offset": offset,
                                         "facturas": len(facturas or [])})

        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(sql, *params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        out: list[RespuestaPruebaRapida] = []
        for r in rows:
            fec_real = _parse_date(r.get("FEC_REALIZACION"))
            if not fec_real:
                log.warning("pruebas: respuesta descartada por fecha realización inválida: seq=%s",
                            r.get("SEQ_RESPUESTA_PRUEBA_RAPIDA"))
                continue
            num_doc = str(r.get("Numero de identificacion") or "").strip()
            out.append(RespuestaPruebaRapida(
                seq_seragil=_to_int(r.get("SEQ_SERAGIL")),
                seq_respuesta=_to_int(r.get("SEQ_RESPUESTA_PRUEBA_RAPIDA")),
                seq_prueba_rapida=_to_int(r.get("SEQ_PRUEBA_RAPIDA")),
                tipo_documento=_normalizar_tipo_doc(r.get("COD_TIPO_IDENTIFICACION")),
                fecha_realizacion=fec_real,
                fecha_registro=_parse_date(r.get("FEC_REGISTRO_INFORMACION")),
                nombre_completo=(r.get("Nombre del Afiliado") or "").strip(),
                primer_nombre=_str(r.get("AFL_PRIMER_NOMBRE")),
                segundo_nombre=_str(r.get("AFL_SEGUNDO_NOMBRE")),
                primer_apellido=_str(r.get("AFL_PRIMER_APELLIDO")),
                segundo_apellido=_str(r.get("AFL_SEGUNDO_APELLIDO")),
                sexo=_str(r.get("Sexo")),
                edad=_to_int(r.get("Edad Actual")),
                fec_nacimiento=_parse_date(r.get("FEC_NACIMIENTO_PERSONA")),
                tipo_identificacion_desc=_str(r.get("Tipo de identificacion")),
                num_documento=num_doc,
                departamento=_str(r.get("Departamento")),
                municipio=_str(r.get("Municipio")),
                direccion=_str(r.get("Direccion")),
                telefono_1=_str(r.get("Telefono 1")),
                telefono_2=_str(r.get("Telefono 2")),
                correo=_str(r.get("Correo electronico")),
                flg_gestante=_to_bool(r.get("FLG_GESTANTE")),
                encuestador=_str(r.get("ENCUESTADOR")),
                cargo_encuestador=_str(r.get("Cargo encuestador")),
                presion_arterial=_str(r.get("PRESION_ARTERIAL")),
                des_prueba_rapida=(r.get("Prueba") or "").strip() or "PRUEBA RAPIDA",
                resultado_prueba=_str(r.get("Resultado")),
                nro_lote=_str(r.get("Lote")),
                observacion=_str(r.get("Observacion")),
            ))

        log.info("pruebas.fetched", extra={"rows": len(out)})
        return out

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_PRUEBAS_COUNT.format(factura_filter=_factura_filter_pruebas(facturas))
        params: list = [fecha_inicio, fecha_final]
        if facturas:
            params.extend(facturas)
        try:
            with pyodbc.connect(settings.db_dsn, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(sql, *params)
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            log.exception("pruebas.get_total failed")
            return 0


def get_pruebas_repository() -> PruebasRapidasRepository:
    if settings.use_mock:
        return MockPruebasRapidasRepository()
    return SqlServerPruebasRapidasRepository()
