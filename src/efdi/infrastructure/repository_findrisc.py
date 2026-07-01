"""Repositorio FINDRISC — abstrae origen de datos para evaluaciones de riesgo de diabetes."""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import RegistroFindrisc, TipoDocumento

log = logging.getLogger(__name__)


class FindriscRepository(Protocol):
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroFindrisc]: ...

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int: ...


# === Query principal paginada ================================================

QUERY_FINDRISC = """
WITH X AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY B.SEQ_ENCUESTADOR_CARACTERIZACION ASC,
                        J.FEC_REALIZACION DESC
           ) AS NUM_REGISTRO,
           A.COD_TIPO_IDENTIFICACION, A.NRO_TIPO_IDENTIFICACION, B.SEQ_SERAGIL,
           A.AFL_PRIMER_NOMBRE, ISNULL(A.AFL_SEGUNDO_NOMBRE,'') AS AFL_SEGUNDO_NOMBRE,
           ISNULL(A.AFL_PRIMER_APELLIDO,'') AS AFL_PRIMER_APELLIDO,
           CONVERT(CHAR(10),J.FEC_REALIZACION) AS FEC_REALIZACION,
           CONVERT(CHAR(10), J.FEC_REGISTRO_INFORMACION) AS FEC_REGISTRO_INFORMACION,
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
      {factura_filter}
)
SELECT
    -- Metadata interna (no se muestra en el reporte; necesaria para agrupar y nombrar archivos)
    X.SEQ_SERAGIL,
    X.COD_TIPO_IDENTIFICACION,
    X.FEC_REGISTRO_INFORMACION,
    X.NUM_REGISTRO,

    -- Columnas del reporte (20)
    CONCAT(X.AFL_PRIMER_NOMBRE, ' ', X.AFL_SEGUNDO_NOMBRE, ' ',
           X.AFL_PRIMER_APELLIDO, ' ', X.AFL_SEGUNDO_APELLIDO)              AS [Nombre del Afiliado],
    X.DES_GENERO                                                            AS Sexo,
    DATEDIFF(yy, X.FEC_NACIMIENTO_PERSONA, GETDATE())
      - CASE
          WHEN MONTH(X.FEC_NACIMIENTO_PERSONA) > MONTH(GETDATE())
            OR (MONTH(X.FEC_NACIMIENTO_PERSONA) = MONTH(GETDATE())
                AND DAY(X.FEC_NACIMIENTO_PERSONA) > DAY(GETDATE()))
          THEN 1 ELSE 0
        END                                                                  AS [Edad Actual],
    X.DES_MUNICIPIO                                                          AS Municipio,
    X.DES_PRESTADOR_SERVICIOS                                                AS [IPS de Atencion Integral al que se remite],
    X.DES_TIPO_IDENTIFICACION                                                AS [Tipo de identificacion],
    X.NRO_TIPO_IDENTIFICACION                                                AS [Numero de identificacion],
    X.DES_TELEFONO_UNO                                                       AS [Telefono 1],
    X.DES_TELEFONO_DOS                                                       AS [Telefono 2],
    X.DES_CORREO_ELECTRONICO                                                 AS [Correo electronico],
    X.VLR_PESO                                                               AS Peso,
    X.VLR_TALLA                                                              AS Talla,
    X.VLR_IMC                                                                AS IMC,
    X.VLR_PERIMETRO_CINTURA                                                  AS [Perimetro de cintura CM],
    X.FLG_ACTIVIDA_FISICA                                                    AS [Activida fisica],
    X.VLR_FRECUENCIA_VERDURAS                                                AS [Frecuencia de verdura o frutas?],
    X.FLG_MEDICAMENTOS_HIPERTENSION                                          AS [Medicamento de la hipertension],
    X.FLG_GLUCOSA_ALTA                                                       AS [Glucosa alta],
    X.FLG_DIABETIS                                                           AS [Se le ha diagnosticado diabetes (tipo 1 o 2) a alguno de sus familiares],
    X.VLR_PUNTAJE_OBTENIDO                                                   AS [Puntaje total]
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_FINDRISC_COUNT = """
SELECT COUNT(*) AS total
FROM AVS_REGISTRO_SERAGIL AS B
JOIN SRG_FORMATO_FINDRISC AS J ON J.SEQ_SERAGIL = B.SEQ_SERAGIL
LEFT JOIN AVS_AFILIADO_MUTUALSER_HIS AS A
    ON A.COD_TIPO_IDENTIFICACION = B.COD_TIPO_IDENTIFICACION_PERSONA
   AND A.NRO_TIPO_IDENTIFICACION = B.NUM_TIPO_IDENTIFICACION_PERSONA
WHERE B.FLG_FORMATO_COLDRISC = 'SI'
  AND B.FEC_REGISTRO_INFORMACION >= ?
  AND B.FEC_REGISTRO_INFORMACION <= ?
  {factura_filter}
"""


# Fragmento EXISTS contra AVS_REGISTROS_AP — mismo patrón que DI Fase 2.
# El código completo (CAB+N o FAB+N) identifica un régimen específico de
# facturación. Cuando vienen facturas, el filtro garantiza que el afiliado
# esté en al menos uno de esos códigos. EXISTS evita multiplicar filas.
# `cod_diag_principal = 'Z131'` es la firma que deja el SP prGeneraRips en las
# filas AP de FINDRISC (cursor cuFormatoFindrisc) — sin él se cuelan afiliados
# facturados en el mismo código de régimen bajo otro módulo (Z048 DI, Z309 PF…).
_FACTURA_EXISTS_FINDRISC = """AND EXISTS (
    SELECT 1 FROM AVS_REGISTROS_AP r_ap
    WHERE r_ap.NUM_TIPO_IDENTIFICACION = A.NRO_TIPO_IDENTIFICACION
      AND r_ap.COD_TIPO_IDENTIFICACION = A.COD_TIPO_IDENTIFICACION
      AND r_ap.NRO_FACTURA IN ({placeholders})
      AND r_ap.cod_diag_principal = 'Z131'
)"""


def _factura_filter_findrisc(facturas: list[str] | None) -> str:
    """Devuelve el fragmento EXISTS con N placeholders, o cadena vacía."""
    if not facturas:
        return ""
    placeholders = ",".join("?" * len(facturas))
    return _FACTURA_EXISTS_FINDRISC.format(placeholders=placeholders)


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
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroFindrisc]:
        import random
        from datetime import timedelta
        registros = []
        nombres = ["CARLOS", "MARIA", "JOSE", "ANA", "LUIS", "CARMEN", "PEDRO", "ROSA"]
        segundos = ["", "ANDRES", "ELENA", "JOSE", "MIGUEL", "ISABEL"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
        municipios = ["CARTAGENA", "BARRANQUILLA", "MONTERIA", "SINCELEJO", "VALLEDUPAR", "SANTA MARTA"]
        ips_list = ["IPS NORTE", "IPS CENTRO", "IPS SUR", "CLINICA SAN JOSE", "CENTRO MEDICO LOS ANGELES"]
        for i in range(limite):
            seq = offset + i + 1
            rng2 = random.Random(seq * 13)
            edad = rng2.randint(18, 75)
            peso = round(rng2.uniform(50, 110), 1)
            talla = round(rng2.uniform(1.50, 1.85), 2)
            imc = round(peso / (talla ** 2), 1)
            cintura = round(rng2.uniform(70, 110), 1)
            actividad = rng2.random() > 0.5
            verduras_ok = rng2.random() > 0.4
            medicamentos = rng2.random() > 0.6
            glucosa = rng2.random() > 0.7
            diab_opts = ["OTROS PARIENTES O NINGUNO", "SI PADRES O HERMANOS", "SI ABUELOS O TIOS O PRIMOS HERMANOS"]
            antecedente = rng2.choice(diab_opts)
            sexo_str = "Femenino" if rng2.random() > 0.5 else "Masculino"

            # Puntajes calculados (mismas reglas que la versión anterior)
            p_edad = 0 if edad < 45 else (2 if edad < 55 else (3 if edad < 65 else 4))
            p_imc = 0 if imc < 25 else (1 if imc < 30 else 3)
            # Perímetro depende del sexo
            if sexo_str == "Masculino":
                p_cintura = 0 if cintura < 94 else (3 if cintura < 102 else 4)
            else:
                p_cintura = 0 if cintura < 80 else (3 if cintura < 88 else 4)
            p_actividad = 0 if actividad else 2
            p_verduras = 0 if verduras_ok else 1
            p_med = 0 if not medicamentos else 2
            p_glucosa = 0 if not glucosa else 5
            p_diab = {
                "OTROS PARIENTES O NINGUNO": 0,
                "SI ABUELOS O TIOS O PRIMOS HERMANOS": 3,
                "SI PADRES O HERMANOS": 5,
            }[antecedente]
            total = p_edad + p_imc + p_cintura + p_actividad + p_verduras + p_med + p_glucosa + p_diab

            fecha_reg = desde + timedelta(days=rng2.randint(0, max((hasta - desde).days, 0)))
            n1 = rng2.choice(nombres)
            n2 = rng2.choice(segundos)
            a1 = rng2.choice(apellidos)
            a2 = rng2.choice(apellidos)
            nombre_full = " ".join(p for p in [n1, n2, a1, a2] if p).strip()
            num_doc = str(1000000 + seq)

            registros.append(RegistroFindrisc(
                seq_seragil=seq,
                tipo_documento=TipoDocumento.CC,
                fecha_registro=fecha_reg,
                nombre_completo=nombre_full,
                sexo=sexo_str,
                edad=edad,
                municipio=rng2.choice(municipios),
                ips=rng2.choice(ips_list),
                tipo_identificacion_desc="CEDULA DE CIUDADANIA",
                num_documento=num_doc,
                telefono_1=f"30{rng2.randint(0, 9)}{rng2.randint(1000000, 9999999)}",
                telefono_2=f"60{rng2.randint(1, 8)}{rng2.randint(1000000, 9999999)}" if rng2.random() > 0.4 else None,
                correo=f"{n1.lower()}.{a1.lower()}@example.com",
                # En Mock simulamos strings tal como vendrían de la BD (algunos con coma)
                peso=f"{peso:.0f}",
                talla=f"{talla:.2f}".replace(".", ","),
                imc=f"{imc:.2f}".replace(".", ","),
                perimetro_cintura=f"{cintura:.0f}",
                actividad_fisica=actividad,
                frecuencia_verduras="TODOS LOS DIAS" if verduras_ok else "NO TODOS LOS DIAS",
                medicamentos_hipertension=medicamentos,
                glucosa_alta=glucosa,
                antecedente_diabetes=antecedente,
                puntaje_total=total,
            ))
        if facturas:
            # Mock del cruce: simula que ~50% de afiliados aparece en el set
            # de facturas. Determinista vía seq_seragil para ser estable.
            registros = [r for r in registros if r.seq_seragil % 2 == 0]
        return registros

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        return 250 if facturas else 500


class SqlServerFindriscRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroFindrisc]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_FINDRISC.format(factura_filter=_factura_filter_findrisc(facturas))
        # Orden de placeholders: fecha_inicio, fecha_final, [facturas...], offset, limite
        params: list = [fecha_inicio, fecha_final]
        if facturas:
            params.extend(facturas)
        params.extend([offset, limite])
        log.info("findrisc.query", extra={"desde": str(desde), "hasta": str(hasta),
                                          "limite": limite, "offset": offset,
                                          "facturas": len(facturas or [])})

        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(sql, *params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        registros: list[RegistroFindrisc] = []
        for r in rows:
            fec_reg = _parse_date(r.get("FEC_REGISTRO_INFORMACION"))
            if not fec_reg:
                log.warning("findrisc: fila descartada por fecha inválida: %s", r.get("SEQ_SERAGIL"))
                continue
            num_doc = str(r.get("Numero de identificacion") or "").strip()
            registros.append(RegistroFindrisc(
                # metadata interna
                seq_seragil=int(r["SEQ_SERAGIL"]),
                tipo_documento=_normalizar_tipo_doc(r.get("COD_TIPO_IDENTIFICACION")),
                fecha_registro=fec_reg,
                # reporte
                nombre_completo=(r.get("Nombre del Afiliado") or "").strip(),
                sexo=(r.get("Sexo") or "").strip() or None,
                edad=_to_int(r.get("Edad Actual")),
                municipio=(r.get("Municipio") or "").strip() or None,
                ips=(r.get("IPS de Atencion Integral al que se remite") or "").strip() or None,
                tipo_identificacion_desc=(r.get("Tipo de identificacion") or "").strip() or None,
                num_documento=num_doc,
                telefono_1=(r.get("Telefono 1") or "").strip() or None,
                telefono_2=(r.get("Telefono 2") or "").strip() or None,
                correo=(r.get("Correo electronico") or "").strip() or None,
                # Valores antropométricos: string literal de la BD (sin parseo)
                peso=(str(r.get("Peso")).strip() if r.get("Peso") is not None else None) or None,
                talla=(str(r.get("Talla")).strip() if r.get("Talla") is not None else None) or None,
                imc=(str(r.get("IMC")).strip() if r.get("IMC") is not None else None) or None,
                perimetro_cintura=(str(r.get("Perimetro de cintura CM")).strip() if r.get("Perimetro de cintura CM") is not None else None) or None,
                actividad_fisica=_to_bool(r.get("Activida fisica")),
                frecuencia_verduras=(r.get("Frecuencia de verdura o frutas?") or "").strip() or None,
                medicamentos_hipertension=_to_bool(r.get("Medicamento de la hipertension")),
                glucosa_alta=_to_bool(r.get("Glucosa alta")),
                antecedente_diabetes=(r.get(
                    "Se le ha diagnosticado diabetes (tipo 1 o 2) a alguno de sus familiares"
                ) or "").strip() or None,
                puntaje_total=_to_int(r.get("Puntaje total")),
            ))

        log.info("findrisc.fetched", extra={"rows": len(registros)})
        return registros

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_FINDRISC_COUNT.format(factura_filter=_factura_filter_findrisc(facturas))
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
            log.exception("findrisc.get_total failed")
            return 0


def get_findrisc_repository() -> FindriscRepository:
    if settings.use_mock:
        return MockFindriscRepository()
    return SqlServerFindriscRepository()
