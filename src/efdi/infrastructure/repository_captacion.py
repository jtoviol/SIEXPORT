"""Repositorio Gestión Captación — abstrae origen de datos para captación de afiliados."""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import RegistroCaptacion, TipoDocumento

log = logging.getLogger(__name__)


class CaptacionRepository(Protocol):
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroCaptacion]: ...

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int: ...


# === Query principal paginada =================================================
QUERY_CAPTACION = """
WITH X AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY a.fec_captacion_afiliado DESC, a.cod_funcionario
           ) AS NUM_REGISTRO,
           a.seq_captacion_afiliado,
           a.cod_tipo_identificacion_persona,
           b.des_tipo_identificacion,
           a.num_tipo_identificacion_persona,
           CONVERT(CHAR(10), a.fec_captacion_afiliado) AS fec_captacion_afiliado,
           e.AFL_PRIMER_NOMBRE + ' ' + ISNULL(e.AFL_SEGUNDO_NOMBRE,'') + ' '
               + e.AFL_PRIMER_APELLIDO + ' ' + ISNULL(e.AFL_SEGUNDO_APELLIDO,'') AS txt_nombres_afiliado,
           genero = CASE
                       WHEN e.COD_GENERO = 'M' THEN 'MASCULINO'
                       WHEN e.COD_GENERO = 'F' THEN 'FEMENINO'
                       ELSE ''
                   END,
           fec_nacimiento = CASE
                       WHEN e.FEC_NACIMIENTO = '1900-01-01' THEN ''
                       WHEN e.FEC_NACIMIENTO IS NULL THEN ''
                       ELSE CONVERT(CHAR(10), e.FEC_NACIMIENTO)
                   END,
           estado = CASE
                       WHEN (a.cod_estado_captacion) = 'VA' THEN 'EN VALIDACION'
                       WHEN (a.cod_estado_captacion) = 'RE' THEN 'RECHAZADO'
                       WHEN (a.cod_estado_captacion) = 'PA' THEN 'APROBADO PARCIALMENTE'
                       WHEN (a.cod_estado_captacion) = 'AP' THEN 'APROBADO'
                       WHEN (a.cod_estado_captacion) = 'NC' THEN 'NO FUE CONTACTADO'
                       ELSE ''
                   END,
           edad = CASE
                       WHEN (a.cod_tipo_edad) = 'D' THEN CAST(a.vlr_edad_enel_momento AS varchar) + ' DIAS'
                       WHEN (a.cod_tipo_edad) = 'M' THEN CAST(a.vlr_edad_enel_momento AS varchar) + ' MESES'
                       ELSE CAST(a.vlr_edad_enel_momento AS varchar) + ' AÑOS'
                   END,
           ISNULL(d.NOMBRE_FUNCIONARIO,'') AS funcionario,
           ISNULL(c.des_departamento,'')   AS des_departamento,
           ISNULL(f.des_municipio,'')      AS des_municipio,
           ISNULL(a.txt_direccion_actual,'')      AS txt_direccion_actual,
           ISNULL(a.txt_telefono_celular,'')      AS txt_telefono_celular,
           ISNULL(a.txt_telefono_fijo,'')         AS txt_telefono_fijo,
           ISNULL(a.txt_correo_electronico,'')    AS txt_correo_electronico,
           ISNULL(a.txt_telefono_familiar,'')     AS txt_telefono_familiar,
           ISNULL(g.des_prestador_servicios,'')   AS des_prestador_servicios,
           ISNULL(h.des_regional,'')              AS des_regional,
           ISNULL(i.DES_FUENTE_CAPTACION, '')     AS des_fuente_captacion,
           flg_gestantes    = CASE WHEN (a.flg_gestantes)    = 'SI' THEN a.flg_gestantes    ELSE '' END,
           flg_hta          = CASE WHEN (a.flg_hta)          = 'SI' THEN a.flg_hta          ELSE '' END,
           flg_mujer_sana   = CASE WHEN (a.flg_mujer_sana)   = 'SI' THEN a.flg_mujer_sana   ELSE '' END,
           flg_ser_joven    = CASE WHEN (a.flg_ser_joven)    = 'SI' THEN a.flg_ser_joven    ELSE '' END,
           flg_salud_mental = CASE WHEN (a.flg_salud_mental) = 'SI' THEN a.flg_salud_mental ELSE '' END,
           flg_victimas     = CASE WHEN (a.flg_victimas)     = 'SI' THEN a.flg_victimas     ELSE '' END,
           flg_epoc         = CASE WHEN (a.flg_epoc)         = 'SI' THEN a.flg_epoc         ELSE '' END,
           flg_amarte       = CASE WHEN (a.flg_amarte)       = 'SI' THEN a.flg_amarte       ELSE '' END,
           flg_renal        = CASE WHEN (a.flg_renal)        = 'SI' THEN a.flg_renal        ELSE '' END,
           flg_vih          = CASE WHEN (a.flg_vih)          = 'SI' THEN a.flg_vih          ELSE '' END,
           flg_hemofilia    = CASE WHEN (a.flg_hemofilia)    = 'SI' THEN a.flg_hemofilia    ELSE '' END,
           flg_salud_sexual = CASE WHEN (a.flg_salud_sexual) = 'SI' THEN a.flg_salud_sexual ELSE '' END,
           flg_cancer       = CASE WHEN (a.flg_cancer)       = 'SI' THEN a.flg_cancer       ELSE '' END,
           flg_tuberculosis = CASE WHEN (a.flg_tuberculosis) = 'SI' THEN a.flg_tuberculosis ELSE '' END,
           flg_lepra        = CASE WHEN (a.flg_lepra)        = 'SI' THEN a.flg_lepra        ELSE '' END,
           flg_epilepsia    = CASE WHEN (a.flg_epilepsia)    = 'SI' THEN a.flg_epilepsia    ELSE '' END,
           flg_huerfanas    = CASE WHEN (a.flg_huerfanas)    = 'SI' THEN a.flg_huerfanas    ELSE '' END,
           flg_desnutricion = CASE WHEN (a.flg_desnutricion) = 'SI' THEN a.flg_desnutricion ELSE '' END,
           flg_obesidad     = CASE WHEN (a.flg_obesidad)     = 'SI' THEN a.flg_obesidad     ELSE '' END
    FROM srg_captacion_afiliados a
    INNER JOIN AVS_AFILIADO_MUTUALSER AS e
        ON a.cod_tipo_identificacion_persona = e.COD_TIPO_IDENTIFICACION
       AND a.num_tipo_identificacion_persona = e.NRO_TIPO_IDENTIFICACION
    LEFT JOIN AVS_TIPO_IDENTIFICACION_USUARIO AS b ON a.cod_tipo_identificacion_persona = b.cod_tipo_identificacion
    LEFT JOIN AVS_DEPARTAMENTO AS c ON a.cod_departamento_vive = c.COD_DEPARTAMENTO
    LEFT JOIN SRG_FUNCIONARIOS_CAPTACION AS d ON a.cod_funcionario = d.SEQ_FUNCIONARIO
    LEFT JOIN AVS_MUNICIPIO AS f ON a.cod_municipio_vive = f.COD_MUNICIPIO
    LEFT JOIN AVS_PRESTADOR_SERVICIOS AS g ON a.cod_prestador_servicio = g.COD_PRESTADOR_SERVICIOS
    LEFT JOIN avs_regional AS h ON f.COD_REGIONAL = h.cod_regional
    LEFT JOIN SRG_FUENTE_CAPTACION AS i ON a.cod_fuente_captacion = i.COD_FUENTE_CAPTACION
    WHERE 1 = 1
      AND a.fec_captacion_afiliado >= ?
      AND a.fec_captacion_afiliado <= ?
      {factura_filter}
)
SELECT X.NUM_REGISTRO,
       X.seq_captacion_afiliado,
       X.cod_tipo_identificacion_persona,
       X.funcionario,
       X.fec_captacion_afiliado,
       X.estado,
       X.des_tipo_identificacion,
       X.num_tipo_identificacion_persona,
       X.des_fuente_captacion,
       X.txt_nombres_afiliado,
       X.fec_nacimiento,
       X.edad,
       X.genero,
       X.des_regional,
       X.des_departamento,
       X.des_municipio,
       X.txt_direccion_actual,
       X.txt_telefono_celular,
       X.txt_telefono_fijo,
       X.txt_correo_electronico,
       X.txt_telefono_familiar,
       X.des_prestador_servicios,
       X.flg_gestantes,    X.flg_hta,          X.flg_mujer_sana,   X.flg_ser_joven,
       X.flg_salud_mental, X.flg_victimas,     X.flg_epoc,         X.flg_amarte,
       X.flg_renal,        X.flg_vih,          X.flg_hemofilia,    X.flg_salud_sexual,
       X.flg_cancer,       X.flg_tuberculosis, X.flg_lepra,        X.flg_epilepsia,
       X.flg_huerfanas,    X.flg_desnutricion, X.flg_obesidad
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_CAPTACION_COUNT = """
SELECT COUNT(DISTINCT a.seq_captacion_afiliado) AS total
FROM srg_captacion_afiliados a
INNER JOIN AVS_AFILIADO_MUTUALSER AS e
    ON a.cod_tipo_identificacion_persona = e.COD_TIPO_IDENTIFICACION
   AND a.num_tipo_identificacion_persona = e.NRO_TIPO_IDENTIFICACION
WHERE a.fec_captacion_afiliado >= ?
  AND a.fec_captacion_afiliado <= ?
  {factura_filter}
"""


# Fragmento EXISTS contra AVS_REGISTROS_AP — mismo patrón que DI/FINDRISC.
# Captación usa alias 'e' para el afiliado (AVS_AFILIADO_MUTUALSER).
# El código completo CAB+N / FAB+N identifica el régimen de facturación.
_FACTURA_EXISTS_CAPTACION = """AND EXISTS (
    SELECT 1 FROM AVS_REGISTROS_AP r_ap
    WHERE r_ap.NUM_TIPO_IDENTIFICACION = e.NRO_TIPO_IDENTIFICACION
      AND r_ap.COD_TIPO_IDENTIFICACION = e.COD_TIPO_IDENTIFICACION
      AND r_ap.NRO_FACTURA IN ({placeholders})
)"""


def _factura_filter_captacion(facturas: list[str] | None) -> str:
    """Devuelve fragmento EXISTS con N placeholders o cadena vacía."""
    if not facturas:
        return ""
    placeholders = ",".join("?" * len(facturas))
    return _FACTURA_EXISTS_CAPTACION.format(placeholders=placeholders)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _str(v: object) -> str | None:
    """Convierte cualquier valor a string limpio (None / '' → None)."""
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


# ─── Mock para desarrollo ─────────────────────────────────────────────────────

class MockCaptacionRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroCaptacion]:
        import random
        from datetime import timedelta
        registros: list[RegistroCaptacion] = []
        nombres = ["CARLOS", "MARIA", "JOSE", "ANA", "LUIS", "CARMEN", "PEDRO", "ROSA"]
        segundos = ["", "ANDRES", "ELENA", "JOSE", "MIGUEL", "ISABEL"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
        municipios = ["CARTAGENA", "BARRANQUILLA", "MONTERIA", "SINCELEJO", "VALLEDUPAR"]
        ips_list = ["IPS NORTE", "IPS CENTRO", "CLINICA SAN JOSE"]
        funcionarios = ["JUAN PEREZ", "CARLOS ANDRES JARAVA TAPIA", "LAURA GOMEZ", "ANA MARIA RUIZ"]
        estados = ["EN VALIDACION", "RECHAZADO", "APROBADO", "APROBADO PARCIALMENTE", "NO FUE CONTACTADO"]
        fuentes = ["TELEFONICO", "PRESENCIAL", "VISITA DOMICILIARIA", "WEB"]
        regionales = ["CARIBE", "ANDINA", "PACIFICO"]
        deptos = ["BOLIVAR", "ATLANTICO", "CORDOBA", "SUCRE", "CESAR"]
        all_flags = [
            "flg_gestantes", "flg_hta", "flg_mujer_sana", "flg_ser_joven", "flg_salud_mental",
            "flg_victimas", "flg_epoc", "flg_amarte", "flg_renal", "flg_vih", "flg_hemofilia",
            "flg_salud_sexual", "flg_cancer", "flg_tuberculosis", "flg_lepra",
            "flg_epilepsia", "flg_huerfanas", "flg_desnutricion", "flg_obesidad",
        ]
        for i in range(limite):
            seq = offset + i + 1
            rng = random.Random(seq * 17)
            fecha_cap = desde + timedelta(days=rng.randint(0, max((hasta - desde).days, 0)))
            n1, n2 = rng.choice(nombres), rng.choice(segundos)
            a1, a2 = rng.choice(apellidos), rng.choice(apellidos)
            nombre = " ".join(p for p in [n1, n2, a1, a2] if p).strip()
            # cuántos flags activos: 0-4
            n_flags = rng.randint(0, 4)
            flags_activos = set(rng.sample(all_flags, n_flags))
            flags_dict = {fl: ("SI" if fl in flags_activos else "") for fl in all_flags}
            edad_n = rng.randint(1, 80)
            tipo_edad = rng.choice(["AÑOS", "AÑOS", "AÑOS", "MESES", "DIAS"])

            registros.append(RegistroCaptacion(
                seq_captacion_afiliado=seq,
                tipo_documento=TipoDocumento.CC,
                fecha_captacion=fecha_cap,
                tipo_identificacion_desc="CEDULA DE CIUDADANIA",
                num_documento=str(1000000 + seq),
                nombre_completo=nombre,
                genero="MASCULINO" if rng.random() > 0.5 else "FEMENINO",
                fec_nacimiento=f"19{rng.randint(50, 99):02d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                edad=f"{edad_n} {tipo_edad}",
                funcionario=rng.choice(funcionarios),
                fecha_captacion_str=str(fecha_cap),
                estado=rng.choice(estados),
                fuente_captacion=rng.choice(fuentes),
                regional=rng.choice(regionales),
                departamento=rng.choice(deptos),
                municipio=rng.choice(municipios),
                direccion=f"CALLE {rng.randint(1, 99)} # {rng.randint(1, 99)}-{rng.randint(1, 99)}",
                telefono_celular=f"30{rng.randint(0, 9)}{rng.randint(1000000, 9999999)}",
                telefono_fijo=f"60{rng.randint(1, 8)}{rng.randint(1000000, 9999999)}" if rng.random() > 0.5 else None,
                telefono_familiar=f"30{rng.randint(0, 9)}{rng.randint(1000000, 9999999)}" if rng.random() > 0.6 else None,
                correo=f"{n1.lower()}.{a1.lower()}@example.com",
                prestador_servicios=rng.choice(ips_list),
                **flags_dict,
            ))
        if facturas:
            # Mock del cruce: simula ~50% de afiliados en el set de códigos.
            registros = [r for r in registros if r.seq_captacion_afiliado % 2 == 0]
        return registros

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        return 250 if facturas else 500


# ─── SQL Server real ─────────────────────────────────────────────────────────

class SqlServerCaptacionRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroCaptacion]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_CAPTACION.format(factura_filter=_factura_filter_captacion(facturas))
        params: list = [fecha_inicio, fecha_final]
        if facturas:
            params.extend(facturas)
        params.extend([offset, limite])
        log.info("captacion.query", extra={"desde": str(desde), "hasta": str(hasta),
                                            "limite": limite, "offset": offset,
                                            "facturas": len(facturas or [])})

        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(sql, *params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        registros: list[RegistroCaptacion] = []
        for r in rows:
            fec_cap = _parse_date(r.get("fec_captacion_afiliado"))
            if not fec_cap:
                log.warning("captacion: fila descartada por fecha inválida: %s", r.get("seq_captacion_afiliado"))
                continue
            registros.append(RegistroCaptacion(
                # metadata interna
                seq_captacion_afiliado=int(r["seq_captacion_afiliado"]),
                tipo_documento=_normalizar_tipo_doc(r.get("cod_tipo_identificacion_persona")),
                fecha_captacion=fec_cap,
                # identificación
                tipo_identificacion_desc=_str(r.get("des_tipo_identificacion")),
                num_documento=str(r.get("num_tipo_identificacion_persona") or "").strip(),
                nombre_completo=_str(r.get("txt_nombres_afiliado")) or "",
                genero=_str(r.get("genero")),
                fec_nacimiento=_str(r.get("fec_nacimiento")),
                edad=_str(r.get("edad")),
                # captación
                funcionario=_str(r.get("funcionario")),
                fecha_captacion_str=_str(r.get("fec_captacion_afiliado")),
                estado=_str(r.get("estado")),
                fuente_captacion=_str(r.get("des_fuente_captacion")),
                # ubicación / contacto
                regional=_str(r.get("des_regional")),
                departamento=_str(r.get("des_departamento")),
                municipio=_str(r.get("des_municipio")),
                direccion=_str(r.get("txt_direccion_actual")),
                telefono_celular=_str(r.get("txt_telefono_celular")),
                telefono_fijo=_str(r.get("txt_telefono_fijo")),
                telefono_familiar=_str(r.get("txt_telefono_familiar")),
                correo=_str(r.get("txt_correo_electronico")),
                prestador_servicios=_str(r.get("des_prestador_servicios")),
                # 19 banderas (vienen "SI" o cadena vacía)
                flg_gestantes=_str(r.get("flg_gestantes")),
                flg_hta=_str(r.get("flg_hta")),
                flg_mujer_sana=_str(r.get("flg_mujer_sana")),
                flg_ser_joven=_str(r.get("flg_ser_joven")),
                flg_salud_mental=_str(r.get("flg_salud_mental")),
                flg_victimas=_str(r.get("flg_victimas")),
                flg_epoc=_str(r.get("flg_epoc")),
                flg_amarte=_str(r.get("flg_amarte")),
                flg_renal=_str(r.get("flg_renal")),
                flg_vih=_str(r.get("flg_vih")),
                flg_hemofilia=_str(r.get("flg_hemofilia")),
                flg_salud_sexual=_str(r.get("flg_salud_sexual")),
                flg_cancer=_str(r.get("flg_cancer")),
                flg_tuberculosis=_str(r.get("flg_tuberculosis")),
                flg_lepra=_str(r.get("flg_lepra")),
                flg_epilepsia=_str(r.get("flg_epilepsia")),
                flg_huerfanas=_str(r.get("flg_huerfanas")),
                flg_desnutricion=_str(r.get("flg_desnutricion")),
                flg_obesidad=_str(r.get("flg_obesidad")),
            ))
        log.info("captacion.fetched", extra={"rows": len(registros)})
        return registros

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_CAPTACION_COUNT.format(factura_filter=_factura_filter_captacion(facturas))
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
            log.exception("captacion.get_total failed")
            return 0


def get_captacion_repository() -> CaptacionRepository:
    if settings.use_mock:
        log.info("captacion repo: MOCK")
        return MockCaptacionRepository()
    log.info("captacion repo: SQL Server")
    return SqlServerCaptacionRepository()
