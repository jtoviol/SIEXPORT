"""Repository — abstrae el origen de datos (mock o SQL Server)."""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import Atencion, ModoIngreso, Regimen, Sexo, TipoDocumento
from efdi.infrastructure.mock_data import generar_atenciones

log = logging.getLogger(__name__)


class AtencionRepository(Protocol):
    """Contrato del repositorio."""

    def obtener_atenciones(
        self, desde: date, hasta: date, limite: int, offset: int = 0
    ) -> list[Atencion]: ...


class MockRepository:
    """Datos falsos deterministas."""

    def obtener_atenciones(
        self, desde: date, hasta: date, limite: int, offset: int = 0
    ) -> list[Atencion]:
        return generar_atenciones(limite=limite, desde=desde, hasta=hasta, offset=offset)

    def get_total(self, desde: date, hasta: date) -> int:
        return 25_000


# === SQL Server real ============================================================

# Query fiel a la consulta oficial de SERAGIL.
# Parámetros: fecha_inicio (datetime 00:00:00), fecha_final (datetime 23:59:59), offset, limit
QUERY_BASE = """
WITH X AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY B.SEQ_ENCUESTADOR_CARACTERIZACION ASC,
                        B.FEC_REGISTRO_INFORMACION DESC
           ) AS NUM_REGISTRO,
           A.COD_TIPO_IDENTIFICACION, A.NRO_TIPO_IDENTIFICACION, B.SEQ_SERAGIL,
           A.AFL_PRIMER_NOMBRE, ISNULL(A.AFL_SEGUNDO_NOMBRE,'') AS AFL_SEGUNDO_NOMBRE,
           ISNULL(A.AFL_PRIMER_APELLIDO,'') AS AFL_PRIMER_APELLIDO,
           CONVERT(CHAR, B.FEC_REGISTRO_INFORMACION,23) AS FEC_REGISTRO_INFORMACION,
           ISNULL(A.AFL_SEGUNDO_APELLIDO,'') AS AFL_SEGUNDO_APELLIDO,
           A.COD_GENERO, A.COD_DEPARTAMENTO, A.COD_MUNICIPIO,
           CONVERT(CHAR(10),B.FEC_NACIMIENTO_PERSONA) AS FEC_NACIMIENTO_PERSONA,
           B.DES_DIRECCION_ACTUAL, B.DES_TELEFONO_UNO, B.DES_TELEFONO_DOS,
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
           B.DES_OTRA_RIAS_GRUPO_RIESGO, L.DES_REMITENTE_INICIAL,
           REGIMEN = CASE
               WHEN A.AFIC_REGIMEN = 'C' THEN 'CONTRIBUTIVO'
               WHEN A.AFIC_REGIMEN = 'S' THEN 'SUBSIDIADO'
               WHEN A.AFIC_REGIMEN = 'V' THEN 'VINCULADO'
               ELSE ''
           END,
           I.TXT_PRIMER_NOMBRE+' '+ISNULL(I.TXT_SEGUNDO_NOMBRE,'')+' '
               +ISNULL(I.TXT_PRIMER_APELLIDO,'')+' '+ISNULL(I.TXT_SEGUNDO_APELLIDO,'') AS ENCUESTADOR,
           DATEDIFF(YEAR, B.FEC_NACIMIENTO_PERSONA, B.FEC_REGISTRO_INFORMACION) AS VLR_EDAD_ACTUAL,
           DES_MODO_INGRESO = CASE
               WHEN B.FLG_MODO_INGRESO = 'CO' THEN 'COMUNIDAD'
               WHEN B.FLG_MODO_INGRESO = 'TE' THEN 'TELEFONICO'
               WHEN B.FLG_MODO_INGRESO = 'VI' THEN 'VIRTUAL'
               ELSE ''
           END,
           O.COD_PROGRAMA_DEMIND, P.DES_PROGRAMA_DEMIND
    FROM AVS_REGISTRO_SERAGIL AS B
    INNER JOIN AVS_AFILIADO_MUTUALSER_HIS AS A
        ON A.COD_TIPO_IDENTIFICACION = B.COD_TIPO_IDENTIFICACION_PERSONA
       AND A.NRO_TIPO_IDENTIFICACION = B.NUM_TIPO_IDENTIFICACION_PERSONA
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
    LEFT JOIN AVS_PROGRAMAS_DEMIND AS P ON O.COD_PROGRAMA_DEMIND = P.COD_PROGRAMA_DEMIND
    WHERE B.FLG_REGIND_DEMIND = 'SI'
      AND B.FEC_REGISTRO_INFORMACION >= ?
      AND B.FEC_REGISTRO_INFORMACION <= ?
)
SELECT X.*
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

# COUNT rápido — mismos filtros, solo INNER JOINs que afectan el conteo.
QUERY_COUNT = """
SELECT COUNT(DISTINCT B.SEQ_SERAGIL) AS total
FROM AVS_REGISTRO_SERAGIL AS B
INNER JOIN AVS_AFILIADO_MUTUALSER_HIS AS A
    ON A.COD_TIPO_IDENTIFICACION = B.COD_TIPO_IDENTIFICACION_PERSONA
   AND A.NRO_TIPO_IDENTIFICACION = B.NUM_TIPO_IDENTIFICACION_PERSONA
INNER JOIN AVS_PROGRAMA_ASOCIADO_DEMIND AS O ON O.SEQ_SERAGIL = B.SEQ_SERAGIL
WHERE B.FLG_REGIND_DEMIND = 'SI'
  AND B.FEC_REGISTRO_INFORMACION >= ?
  AND B.FEC_REGISTRO_INFORMACION <= ?
"""


def _normalizar_sexo(cod: str | None, des: str | None) -> Sexo:
    if cod and cod.upper().startswith("M"):
        return Sexo.M
    if cod and cod.upper().startswith("F"):
        return Sexo.F
    if des and "FEM" in des.upper():
        return Sexo.F
    return Sexo.M


def _normalizar_tipo_doc(cod: str | None, des: str | None) -> TipoDocumento:
    if not cod:
        return TipoDocumento.CC
    c = cod.upper().strip()
    try:
        return TipoDocumento(c)
    except ValueError:
        return TipoDocumento.CC


def _normalizar_regimen(s: str | None) -> Regimen | None:
    if not s:
        return None
    s = s.upper().strip()
    if s == "CONTRIBUTIVO":
        return Regimen.CONTRIBUTIVO
    if s == "SUBSIDIADO":
        return Regimen.SUBSIDIADO
    if s == "VINCULADO":
        return Regimen.VINCULADO
    return None


def _normalizar_modo_ingreso(s: str | None) -> ModoIngreso | None:
    if not s:
        return None
    s = s.upper().strip()
    try:
        return ModoIngreso(s)
    except ValueError:
        return None


def _to_bool(v: object) -> bool:
    """Normaliza flags de SQL Server. Trata 'SI'/'S'/'1'/'TRUE' como True
    y 'NO'/'N'/'0'/'FALSE'/None/'' como False.

    bool() de Python da True para cualquier string no vacío — por eso 'NO'
    salía como True. Esta función lee el contenido real del campo."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    if isinstance(v, str):
        return v.strip().upper() in ("SI", "S", "1", "TRUE", "YES", "Y")
    return False


def _fechas_dt(desde: date, hasta: date):
    """Devuelve (inicio, fin) como datetime igual que SERAGIL: 00:00:00 y 23:59:59."""
    from datetime import datetime as _dt
    return (
        _dt(desde.year, desde.month, desde.day, 0, 0, 0),
        _dt(hasta.year, hasta.month, hasta.day, 23, 59, 59),
    )


def _parse_date(v: object) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    from datetime import datetime as _dt
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return _dt.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


class SqlServerRepository:
    """SQL Server real vía pyodbc."""

    def obtener_atenciones(
        self, desde: date, hasta: date, limite: int, offset: int = 0
    ) -> list[Atencion]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError(
                "pyodbc no instalado. Instalar con: pip install '.[sqlserver]' "
                "y tener el ODBC Driver 17 for SQL Server en el sistema."
            ) from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        log.info(
            "sqlserver.query",
            extra={"desde": str(desde), "hasta": str(hasta), "limite": limite, "offset": offset},
        )
        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(QUERY_BASE, fecha_inicio, fecha_final, offset, limite)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        atenciones: list[Atencion] = []
        for r in rows:
            fec_nac = _parse_date(r.get("FEC_NACIMIENTO_PERSONA"))
            fec_reg = _parse_date(r.get("FEC_REGISTRO_INFORMACION"))
            if not fec_nac or not fec_reg:
                log.warning("fila descartada por fechas inválidas: %s", r.get("SEQ_SERAGIL"))
                continue

            atenciones.append(Atencion(
                seq_seragil=int(r["SEQ_SERAGIL"]),
                consecutivo=int(r["NUM_REGISTRO"]),
                tipo_documento=_normalizar_tipo_doc(r.get("COD_TIPO_IDENTIFICACION"),
                                                    r.get("DES_TIPO_IDENTIFICACION")),
                num_documento=str(r["NRO_TIPO_IDENTIFICACION"]).strip(),
                primer_nombre=(r.get("AFL_PRIMER_NOMBRE") or "").strip(),
                segundo_nombre=(r.get("AFL_SEGUNDO_NOMBRE") or "").strip() or None,
                primer_apellido=(r.get("AFL_PRIMER_APELLIDO") or "").strip(),
                segundo_apellido=(r.get("AFL_SEGUNDO_APELLIDO") or "").strip() or None,
                sexo=_normalizar_sexo(r.get("COD_GENERO"), r.get("DES_GENERO")),
                edad=int(r.get("VLR_EDAD_ACTUAL") or 0),
                fecha_nacimiento=fec_nac,
                direccion=(r.get("DES_DIRECCION_ACTUAL") or "").strip() or None,
                telefono_1=(r.get("DES_TELEFONO_UNO") or "").strip() or None,
                telefono_2=(r.get("DES_TELEFONO_DOS") or "").strip() or None,
                correo=(r.get("DES_CORREO_ELECTRONICO") or "").strip() or None,
                departamento=(r.get("DES_DEPARTAMENTO") or "").strip() or None,
                municipio=(r.get("DES_MUNICIPIO") or "").strip() or None,
                curso_vida=(r.get("DES_CURSO_VIDA_ASOCIADO") or "").strip() or None,
                regimen=_normalizar_regimen(r.get("REGIMEN")),
                fecha_registro=fec_reg,
                fecha_atencion=_parse_date(r.get("FEC_REAL_EJECUCION")),
                cod_programa=str(r.get("COD_PROGRAMA_DEMIND") or "").strip(),
                des_programa=(r.get("DES_PROGRAMA_DEMIND") or "").strip(),
                ips_remite=(r.get("DES_PRESTADOR_SERVICIOS") or "").strip() or None,
                ips_atiende=(r.get("DES_PRESTADOR_EJECUCION") or "").strip() or None,
                modo_ingreso=_normalizar_modo_ingreso(r.get("DES_MODO_INGRESO")),
                cod_remitente=str(r.get("COD_TIPO_REMITENTE_INICIAL") or "").strip() or None,
                des_remitente=(r.get("DES_REMITENTE_INICIAL") or "").strip() or None,
                des_otro_remitente=(r.get("DES_OTRO_REMITENTE_INICIAL") or "").strip() or None,
                encuestador_nombre=(r.get("ENCUESTADOR") or "").strip() or None,
                cargo_encuestador=(r.get("DES_CARGO_USUARIO") or "").strip() or None,
                rias_grupo_riesgo=(r.get("DES_RIAS_GRUPO_RIESGO") or "").strip() or None,
                otra_rias=(r.get("DES_OTRA_RIAS_GRUPO_RIESGO") or "").strip() or None,
                notificacion_obligatoria=_to_bool(r.get("FLG_NOTIFICACION_OBLIGATORIA")),
                recuperacion_urgencias=_to_bool(r.get("FLG_RECUPERACION_URGENCIAS")),
                recuperacion_consulta_externa=_to_bool(r.get("FLG_RECUPERACION_CONSULTA_EXTERNA")),
            ))
        log.info("sqlserver.fetched", extra={"rows": len(atenciones)})
        return atenciones

    def get_total(self, desde: date, hasta: date) -> int:
        """Retorna el total de registros para el rango — misma lógica que SERAGIL CAN_REGISTROS."""
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        try:
            with pyodbc.connect(settings.db_dsn, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(QUERY_COUNT, fecha_inicio, fecha_final)
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except Exception:
            log.exception("sqlserver.get_total failed")
            return 0

    def ping(self) -> bool:
        """Verifica conexión sin tocar las tablas reales."""
        try:
            import pyodbc
        except ImportError:
            return False
        try:
            with pyodbc.connect(settings.db_dsn, timeout=5) as conn:
                conn.cursor().execute("SELECT 1").fetchone()
            return True
        except Exception:
            log.exception("sqlserver.ping failed")
            return False


def get_repository() -> AtencionRepository:
    if settings.use_mock:
        return MockRepository()
    return SqlServerRepository()
