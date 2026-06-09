"""Repositorio Seguimiento Planificación Familiar.

Origen: SRG_POBLACION_RIESGO_REPRODUCTIVO + SRG_DETALLE_RIESGO_REPRODUCTIVO.
Filtro único: rango de fec_gestion_seguimiento.
Política de fidelidad: campos literales de la BD.
"""
import logging
from datetime import date
from typing import Protocol

from efdi.config import settings
from efdi.domain.models import RegistroPlanFamiliar, TipoDocumento

log = logging.getLogger(__name__)


class PlanFamiRepository(Protocol):
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroPlanFamiliar]: ...

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int: ...


# === Query principal paginada =================================================
QUERY_PLANFAMI = """
WITH X AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY a.cod_periodo_ano, a.cod_periodo_trimestre, a.COD_REGIONAL DESC
           ) AS NUM_REGISTRO,
           a.seq_poblacion_riesgo,
           a.cod_tipo_identificacion,
           a.COD_REGIONAL,
           a.nro_tipo_identificacion,
           fec_gestion_seguimiento = CASE
                       WHEN (l.fec_gestion_seguimiento IS NULL
                             OR l.fec_gestion_seguimiento = '1900-01-01') THEN ''
                       ELSE CONVERT(CHAR(10), l.fec_gestion_seguimiento)
                   END,
           b.AFL_PRIMER_NOMBRE + ' ' + ISNULL(b.AFL_SEGUNDO_NOMBRE,'') + ' '
               + b.AFL_PRIMER_APELLIDO + ' ' + ISNULL(b.AFL_SEGUNDO_APELLIDO,'') AS nom_afiliado,
           genero = CASE
                       WHEN b.COD_GENERO = 'M' THEN 'MASCULINO'
                       WHEN b.COD_GENERO = 'F' THEN 'FEMENINO'
                       ELSE ''
                   END,
           fec_nacimiento = CASE
                       WHEN (b.FEC_NACIMIENTO IS NULL OR b.FEC_NACIMIENTO = '1900-01-01') THEN ''
                       ELSE CONVERT(CHAR(10), b.FEC_NACIMIENTO)
                   END,
           edad = DATEDIFF(year, b.FEC_NACIMIENTO, GETDATE()),
           ISNULL(d.des_departamento,'')          AS des_departamento,
           ISNULL(c.DES_REGIONAL,'')              AS des_regional,
           ISNULL(f.DES_MUNICIPIO,'')             AS des_municipio,
           ISNULL(e.des_tipo_identificacion,'')   AS des_tipo_identificacion,
           ISNULL(h.DES_MOTIVO_NO_PLANIFICA,'')   AS des_motivo_no_planifica,
           ISNULL(i.DES_METODO_ANTICONCEPTIVO,'') AS des_metodo_anticonceptivo,
           ISNULL(j.DES_METODO_ANTICONCEPTIVO,'') AS des_metodo_planificacion,
           ISNULL(k.des_motivo_nocontacto,'')     AS des_motivo_nocontacto,
           a.cod_periodo_ano,
           a.cod_periodo_trimestre,
           ISNULL(a.flg_inicio_preconcepcional,'') AS flg_inicio_preconcepcional,
           ISNULL(b.TXT_TELEFONO,'') + ' ' + ISNULL(b.TXT_CELULAR_UNO,'') + ' '
               + ISNULL(b.TXT_CELULAR_DOS,'') AS tel_afiliada,
           ISNULL(g.TXT_PRIMER_NOMBRE,'') + ' ' + ISNULL(g.TXT_SEGUNDO_NOMBRE,'') + ' '
               + ISNULL(g.TXT_PRIMER_APELLIDO,'') + ' '
               + ISNULL(g.TXT_SEGUNDO_APELLIDO,'') AS nom_encuestador,
           ISNULL(a.flg_planifica,'')              AS flg_planifica,
           ISNULL(a.flg_desea_utilizar_metodo,'')  AS flg_desea_utilizar_metodo,
           ISNULL(a.nro_eventos_obstetricos, 0)    AS nro_eventos_obstetricos,
           ISNULL(a.flg_fuente_evento_obstetrico,'') AS flg_fuente_evento_obstetrico,
           ISNULL(a.fec_evento_planificacion,'')     AS fec_evento_planificacion,
           ISNULL(a.cod_producto_ev_planificacion,'') AS cod_producto_ev_planificacion,
           ISNULL(a.nom_producto_ev_planificacion,'') AS nom_producto_ev_planificacion,
           ISNULL(a.fec_planificacion_202,'')        AS fec_planificacion_202,
           ISNULL(a.var_planificacion_202,'')        AS var_planificacion_202,
           ISNULL(a.fec_planificacion_Temporal,'')   AS fec_planificacion_Temporal,
           ISNULL(a.cod_fuente_Planificacion_Temporal,'') AS cod_fuente_Planificacion_Temporal,
           ISNULL(a.des_metodo_Planificacion_Temporal,'') AS des_metodo_Planificacion_Temporal,
           ISNULL(a.FIC_Dtc_Dm,'')        AS FIC_Dtc_Dm,
           ISNULL(a.FIC_Dtc_Hta,'')       AS FIC_Dtc_Hta,
           ISNULL(a.FIC_Artritis,'')      AS FIC_Artritis,
           ISNULL(a.FIC_Cancer,'')        AS FIC_Cancer,
           ISNULL(a.FIC_Epilepsia,'')     AS FIC_Epilepsia,
           ISNULL(a.FIC_Epoc,'')          AS FIC_Epoc,
           ISNULL(a.FIC_Hemofilia,'')     AS FIC_Hemofilia,
           ISNULL(a.FIC_Huerfanas,'')     AS FIC_Huerfanas,
           ISNULL(a.FIC_Renal,'')         AS FIC_Renal,
           ISNULL(a.FIC_Salud_Mental,'')  AS FIC_Salud_Mental,
           ISNULL(a.FIC_Trasplante,'')    AS FIC_Trasplante,
           ISNULL(a.FIC_Victimas,'')      AS FIC_Victimas,
           ISNULL(a.FIC_Vih,'')           AS FIC_Vih,
           tipo_poblacion = CASE
                               WHEN a.cod_tipo_poblacion = '01' THEN 'ADOLESCENTE'
                               WHEN a.cod_tipo_poblacion = '02' THEN 'MULTIPARA'
                               WHEN a.cod_tipo_poblacion = '03' THEN 'COHORTE DE RIESGO'
                               ELSE 'SIN DEFINIR'
                            END,
           estado = CASE
                       WHEN a.cod_estado = '01' THEN 'NO INTERVENIDA'
                       WHEN a.cod_estado = '02' THEN 'PENDIENTE'
                       WHEN a.cod_estado = '03' THEN 'CERRADA'
                       ELSE ''
                    END,
           tipo_seguimiento = CASE
                                 WHEN l.cod_tipo_seguimiento = '01' THEN 'TELEFONICO'
                                 WHEN l.cod_tipo_seguimiento = '02' THEN 'DOMICILIARIO'
                                 ELSE ''
                              END,
           regimen = CASE
                        WHEN b.AFIC_REGIMEN = 'C' THEN 'CONTRIBUTIVO'
                        WHEN b.AFIC_REGIMEN = 'S' THEN 'SUBSIDIADO'
                        WHEN b.AFIC_REGIMEN = 'V' THEN 'VINCULADO'
                        WHEN b.AFIC_REGIMEN = 'N' THEN 'POBRE NO ASEGURADO'
                        WHEN b.AFIC_REGIMEN = 'P' THEN 'PARTICULAR'
                        ELSE ''
                     END,
           fec_inicio_planfami = CASE
                       WHEN (a.fec_inicio_planfami IS NULL
                             OR a.fec_inicio_planfami = '1900-01-01') THEN ''
                       ELSE CONVERT(CHAR(10), a.fec_inicio_planfami)
                   END,
           ISNULL(l.flg_contactada,'')          AS flg_contactada,
           ISNULL(l.flg_visita_domiciliaria,'') AS flg_visita_domiciliaria,
           ISNULL(l.flg_cierra_seguimiento,'')  AS flg_cierra_seguimiento,
           ISNULL(l.observaciones,'')           AS observaciones
    FROM SRG_POBLACION_RIESGO_REPRODUCTIVO a
    LEFT JOIN AVS_AFILIADO_MUTUALSER_HIS AS b
        ON a.cod_tipo_identificacion = b.COD_TIPO_IDENTIFICACION
       AND a.nro_tipo_identificacion = b.NRO_TIPO_IDENTIFICACION
    LEFT JOIN AVS_REGIONAL AS c ON a.COD_REGIONAL = c.COD_REGIONAL
    LEFT JOIN AVS_DEPARTAMENTO AS d ON b.COD_DEPARTAMENTO = d.COD_DEPARTAMENTO
    LEFT JOIN SRG_DETALLE_RIESGO_REPRODUCTIVO AS l
        ON a.seq_poblacion_riesgo = l.seq_poblacion_riesgo
    LEFT JOIN AVS_TIPO_IDENTIFICACION_USUARIO AS e
        ON a.cod_tipo_identificacion = e.COD_TIPO_IDENTIFICACION
    LEFT JOIN AVS_MUNICIPIO AS f ON b.COD_MUNICIPIO = f.COD_MUNICIPIO
    LEFT JOIN AVS_USUARIO_SISTEMA AS g ON l.SEQ_USUARIO_SISTEMA = g.SEQ_USUARIO_SISTEMA
    LEFT JOIN SRG_MOTIVO_NO_PLANIFICA AS h
        ON a.cod_motivo_noutiliza_metodo = h.COD_MOTIVO_NO_PLANIFICA
    LEFT JOIN SRG_METODO_ANTICONCEPTIVO AS i
        ON a.cod_que_metodo_quiere_usar = i.COD_METODO_ANTICONCEPTIVO
    LEFT JOIN SRG_METODO_ANTICONCEPTIVO AS j
        ON a.cod_metodo_planificacion = j.COD_METODO_ANTICONCEPTIVO
    LEFT JOIN srg_motivo_nocontacto AS k
        ON l.cod_motivo_no_contacto = k.cod_motivo_nocontacto
    WHERE 1 = 1
      AND a.fec_gestion_seguimiento >= ?
      AND a.fec_gestion_seguimiento <= ?
      {factura_filter}
)
SELECT X.NUM_REGISTRO,
       X.seq_poblacion_riesgo,
       X.cod_tipo_identificacion,
       X.des_regional,
       X.des_municipio,
       X.des_departamento,
       X.cod_periodo_ano       AS anio,
       X.cod_periodo_trimestre AS trimestre,
       X.tipo_poblacion,
       X.nom_encuestador,
       X.fec_gestion_seguimiento,
       X.nro_tipo_identificacion,
       X.des_tipo_identificacion,
       X.nom_afiliado,
       X.fec_nacimiento,
       X.edad,
       X.tel_afiliada,
       X.regimen,
       X.flg_planifica,
       X.des_motivo_no_planifica,
       X.flg_desea_utilizar_metodo,
       X.des_metodo_anticonceptivo,
       X.fec_inicio_planfami,
       X.flg_inicio_preconcepcional,
       X.nro_eventos_obstetricos,
       X.flg_fuente_evento_obstetrico,
       X.fec_evento_planificacion,
       X.cod_producto_ev_planificacion,
       X.nom_producto_ev_planificacion,
       X.fec_planificacion_202,
       X.var_planificacion_202,
       X.fec_planificacion_Temporal,
       X.cod_fuente_Planificacion_Temporal,
       X.des_metodo_Planificacion_Temporal,
       X.FIC_Dtc_Dm,    X.FIC_Dtc_Hta,    X.FIC_Artritis,
       X.FIC_Cancer,    X.FIC_Epilepsia,  X.FIC_Epoc,
       X.FIC_Hemofilia, X.FIC_Huerfanas,  X.FIC_Renal,
       X.FIC_Salud_Mental, X.FIC_Trasplante, X.FIC_Victimas, X.FIC_Vih,
       X.estado,
       X.tipo_seguimiento,
       X.flg_contactada,
       X.flg_visita_domiciliaria,
       X.flg_cierra_seguimiento,
       X.des_motivo_nocontacto,
       X.des_metodo_planificacion,
       X.observaciones
FROM X
ORDER BY X.NUM_REGISTRO
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
"""

QUERY_PLANFAMI_COUNT = """
SELECT COUNT(DISTINCT a.seq_poblacion_riesgo) AS total
FROM SRG_POBLACION_RIESGO_REPRODUCTIVO a
LEFT JOIN SRG_DETALLE_RIESGO_REPRODUCTIVO l
    ON a.seq_poblacion_riesgo = l.seq_poblacion_riesgo
LEFT JOIN AVS_AFILIADO_MUTUALSER_HIS AS b
    ON a.cod_tipo_identificacion = b.COD_TIPO_IDENTIFICACION
   AND a.nro_tipo_identificacion = b.NRO_TIPO_IDENTIFICACION
WHERE a.fec_gestion_seguimiento >= ?
  AND a.fec_gestion_seguimiento <= ?
  {factura_filter}
"""


# Fragmento EXISTS contra AVS_REGISTROS_AP — mismo patrón que DI/FINDRISC/Captación.
# Planificación Familiar usa alias 'b' para el afiliado (AVS_AFILIADO_MUTUALSER_HIS).
# El código completo CAB+N / FAB+N identifica el régimen de facturación.
_FACTURA_EXISTS_PLANFAMI = """AND EXISTS (
    SELECT 1 FROM AVS_REGISTROS_AP r_ap
    WHERE r_ap.NUM_TIPO_IDENTIFICACION = b.NRO_TIPO_IDENTIFICACION
      AND r_ap.COD_TIPO_IDENTIFICACION = b.COD_TIPO_IDENTIFICACION
      AND r_ap.NRO_FACTURA IN ({placeholders})
)"""


def _factura_filter_planfami(facturas: list[str] | None) -> str:
    """Devuelve fragmento EXISTS con N placeholders o cadena vacía."""
    if not facturas:
        return ""
    placeholders = ",".join("?" * len(facturas))
    return _FACTURA_EXISTS_PLANFAMI.format(placeholders=placeholders)


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

class MockPlanFamiRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroPlanFamiliar]:
        import random
        from datetime import timedelta

        regs: list[RegistroPlanFamiliar] = []
        nombres = ["MARIA", "ANA", "CARMEN", "ROSA", "LUZ", "PATRICIA", "DIANA"]
        segundos = ["", "PAOLA", "ISABEL", "LUCIA", "ELENA", "DEL CARMEN"]
        apellidos = ["GARCIA", "LOPEZ", "MARTINEZ", "RODRIGUEZ", "GONZALEZ", "PEREZ"]
        encuestadores = ["EDILSA SALGADO OROZCO", "NELSYS MARTINEZ ARRIETA",
                         "LUZ DARY GOYENECHE PINEDA", "GLORIA PATRICIA SAEZ REGINO"]
        regiones = ["BOLIVAR NORTE", "MAGDALENA", "ATLANTICO", "CORDOBA"]
        municipios = ["CARTAGENA", "SANTA MARTA", "BARRANQUILLA", "MONTERIA", "CIENAGA"]
        deptos = ["BOLIVAR", "MAGDALENA", "ATLANTICO", "CORDOBA"]
        tipos_poblacion = ["ADOLESCENTE", "MULTIPARA", "COHORTE DE RIESGO"]
        estados = ["NO INTERVENIDA", "PENDIENTE", "CERRADA"]
        tipos_seg = ["TELEFONICO", "DOMICILIARIO"]
        regimenes = ["SUBSIDIADO", "CONTRIBUTIVO"]
        motivos_no = ["HISTERECTOMIA", "MENOPAUSIA", "INFERTILIDAD",
                      "NO TIENE PAREJA ACTUALMENTE", "NO DESEA PLANIFICAR",
                      "NO HA INICIADO RELACIONES SEXUALES"]
        motivos_contacto = ["NO RESPONDEN", "FUERA DE SERVICIO", "TELEFONO APAGADO",
                            "USUARIA OTRA EPS", "NUMERO EQUIVOCADO"]
        all_fic = [
            "fic_dtc_dm", "fic_dtc_hta", "fic_artritis", "fic_cancer",
            "fic_epilepsia", "fic_epoc", "fic_hemofilia", "fic_huerfanas",
            "fic_renal", "fic_salud_mental", "fic_trasplante", "fic_victimas", "fic_vih",
        ]

        for i in range(limite):
            seq = offset + i + 1
            rng = random.Random(seq * 23)
            fecha_g = desde + timedelta(days=rng.randint(0, max((hasta - desde).days, 0)))
            n1 = rng.choice(nombres)
            n2 = rng.choice(segundos)
            a1 = rng.choice(apellidos)
            a2 = rng.choice(apellidos)
            nombre = " ".join(p for p in [n1, n2, a1, a2] if p).strip()
            num_doc = str(1_000_000_000 + seq)
            edad_n = rng.randint(16, 52)
            estado = rng.choice(estados)
            cerrada = estado == "CERRADA"
            n_fic = rng.randint(0, 3)
            fic_activos = set(rng.sample(all_fic, n_fic))
            fic_dict = {f: ("SI" if f in fic_activos else "") for f in all_fic}

            regs.append(RegistroPlanFamiliar(
                seq_poblacion_riesgo=seq,
                tipo_documento=TipoDocumento.CC,
                fecha_gestion=fecha_g,
                regional=rng.choice(regiones),
                municipio=rng.choice(municipios),
                departamento=rng.choice(deptos),
                anio=str(rng.randint(2022, 2026)),
                trimestre=f"0{rng.randint(1, 4)}",
                tipo_poblacion=rng.choice(tipos_poblacion),
                encuestador=rng.choice(encuestadores),
                fecha_gestion_str=str(fecha_g),
                tipo_identificacion_desc="CEDULA DE CIUDADANIA",
                num_documento=num_doc,
                nombre_completo=nombre,
                fecha_nacimiento=f"19{rng.randint(70, 99):02d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                edad=str(edad_n),
                telefono=f"30{rng.randint(0, 9)}{rng.randint(1000000, 9999999)}",
                regimen=rng.choice(regimenes),
                flg_planifica=rng.choice(["SI", "NO", ""]),
                motivo_no_planifica=rng.choice(motivos_no) if rng.random() > 0.5 else "",
                flg_desea_utilizar_metodo=rng.choice(["SI", "NO", ""]),
                metodo_anticonceptivo="",
                fec_inicio_planfami="",
                flg_inicio_preconcepcional="",
                metodo_planificacion="",
                nro_eventos_obstetricos=str(rng.randint(0, 6)),
                flg_fuente_evento_obstetrico="",
                fec_evento_planificacion="",
                cod_producto_ev_planificacion="",
                nom_producto_ev_planificacion="",
                fec_planificacion_202="",
                var_planificacion_202="",
                fec_planificacion_temporal="",
                cod_fuente_planificacion_temporal="",
                des_metodo_planificacion_temporal="",
                estado=estado,
                tipo_seguimiento=rng.choice(tipos_seg) if cerrada or rng.random() > 0.3 else "",
                flg_contactada=rng.choice(["SI", "NO"]) if cerrada else "",
                flg_visita_domiciliaria=rng.choice(["SI", "NO"]) if cerrada else "",
                flg_cierra_seguimiento="SI" if cerrada else ("NO" if rng.random() > 0.5 else ""),
                motivo_nocontacto=rng.choice(motivos_contacto) if not cerrada else "",
                observaciones="Educación realizada con respecto a los servicios de PYM" if cerrada else "",
                **fic_dict,
            ))
        if facturas:
            # Mock del cruce: ~50% de afiliados en el set de códigos (determinista).
            regs = [r for r in regs if r.seq_poblacion_riesgo % 2 == 0]
        return regs

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        return 400 if facturas else 800


# ─── SQL Server real ─────────────────────────────────────────────────────────

class SqlServerPlanFamiRepository:
    def obtener_registros(
        self, desde: date, hasta: date, limite: int, offset: int = 0,
        facturas: list[str] | None = None,
    ) -> list[RegistroPlanFamiliar]:
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc no instalado") from e

        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_PLANFAMI.format(factura_filter=_factura_filter_planfami(facturas))
        params: list = [fecha_inicio, fecha_final]
        if facturas:
            params.extend(facturas)
        params.extend([offset, limite])
        log.info("planfami.query", extra={"desde": str(desde), "hasta": str(hasta),
                                           "limite": limite, "offset": offset,
                                           "facturas": len(facturas or [])})

        with pyodbc.connect(settings.db_dsn, timeout=60) as conn:
            cur = conn.cursor()
            cur.execute(sql, *params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

        registros: list[RegistroPlanFamiliar] = []
        for r in rows:
            fec_g = _parse_date(r.get("fec_gestion_seguimiento"))
            if not fec_g:
                log.warning("planfami: fila descartada por fecha inválida: %s",
                            r.get("seq_poblacion_riesgo"))
                continue
            registros.append(RegistroPlanFamiliar(
                seq_poblacion_riesgo=int(r["seq_poblacion_riesgo"]),
                tipo_documento=_normalizar_tipo_doc(r.get("cod_tipo_identificacion")),
                fecha_gestion=fec_g,
                regional=_str(r.get("des_regional")),
                municipio=_str(r.get("des_municipio")),
                departamento=_str(r.get("des_departamento")),
                anio=_str(r.get("anio")),
                trimestre=_str(r.get("trimestre")),
                tipo_poblacion=_str(r.get("tipo_poblacion")),
                encuestador=_str(r.get("nom_encuestador")),
                fecha_gestion_str=_str(r.get("fec_gestion_seguimiento")),
                tipo_identificacion_desc=_str(r.get("des_tipo_identificacion")),
                num_documento=str(r.get("nro_tipo_identificacion") or "").strip(),
                nombre_completo=_str(r.get("nom_afiliado")) or "",
                fecha_nacimiento=_str(r.get("fec_nacimiento")),
                edad=_str(r.get("edad")),
                telefono=_str(r.get("tel_afiliada")),
                regimen=_str(r.get("regimen")),
                flg_planifica=_str(r.get("flg_planifica")),
                motivo_no_planifica=_str(r.get("des_motivo_no_planifica")),
                flg_desea_utilizar_metodo=_str(r.get("flg_desea_utilizar_metodo")),
                metodo_anticonceptivo=_str(r.get("des_metodo_anticonceptivo")),
                fec_inicio_planfami=_str(r.get("fec_inicio_planfami")),
                flg_inicio_preconcepcional=_str(r.get("flg_inicio_preconcepcional")),
                metodo_planificacion=_str(r.get("des_metodo_planificacion")),
                nro_eventos_obstetricos=_str(r.get("nro_eventos_obstetricos")),
                flg_fuente_evento_obstetrico=_str(r.get("flg_fuente_evento_obstetrico")),
                fec_evento_planificacion=_str(r.get("fec_evento_planificacion")),
                cod_producto_ev_planificacion=_str(r.get("cod_producto_ev_planificacion")),
                nom_producto_ev_planificacion=_str(r.get("nom_producto_ev_planificacion")),
                fec_planificacion_202=_str(r.get("fec_planificacion_202")),
                var_planificacion_202=_str(r.get("var_planificacion_202")),
                fec_planificacion_temporal=_str(r.get("fec_planificacion_Temporal")),
                cod_fuente_planificacion_temporal=_str(r.get("cod_fuente_Planificacion_Temporal")),
                des_metodo_planificacion_temporal=_str(r.get("des_metodo_Planificacion_Temporal")),
                fic_dtc_dm=_str(r.get("FIC_Dtc_Dm")),
                fic_dtc_hta=_str(r.get("FIC_Dtc_Hta")),
                fic_artritis=_str(r.get("FIC_Artritis")),
                fic_cancer=_str(r.get("FIC_Cancer")),
                fic_epilepsia=_str(r.get("FIC_Epilepsia")),
                fic_epoc=_str(r.get("FIC_Epoc")),
                fic_hemofilia=_str(r.get("FIC_Hemofilia")),
                fic_huerfanas=_str(r.get("FIC_Huerfanas")),
                fic_renal=_str(r.get("FIC_Renal")),
                fic_salud_mental=_str(r.get("FIC_Salud_Mental")),
                fic_trasplante=_str(r.get("FIC_Trasplante")),
                fic_victimas=_str(r.get("FIC_Victimas")),
                fic_vih=_str(r.get("FIC_Vih")),
                estado=_str(r.get("estado")),
                tipo_seguimiento=_str(r.get("tipo_seguimiento")),
                flg_contactada=_str(r.get("flg_contactada")),
                flg_visita_domiciliaria=_str(r.get("flg_visita_domiciliaria")),
                flg_cierra_seguimiento=_str(r.get("flg_cierra_seguimiento")),
                motivo_nocontacto=_str(r.get("des_motivo_nocontacto")),
                observaciones=_str(r.get("observaciones")),
            ))
        log.info("planfami.fetched", extra={"rows": len(registros)})
        return registros

    def get_total(self, desde: date, hasta: date, facturas: list[str] | None = None) -> int:
        try:
            import pyodbc
        except ImportError:
            return 0
        fecha_inicio, fecha_final = _fechas_dt(desde, hasta)
        sql = QUERY_PLANFAMI_COUNT.format(factura_filter=_factura_filter_planfami(facturas))
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
            log.exception("planfami.get_total failed")
            return 0


def get_planfami_repository() -> PlanFamiRepository:
    if settings.use_mock:
        log.info("planfami repo: MOCK")
        return MockPlanFamiRepository()
    log.info("planfami repo: SQL Server")
    return SqlServerPlanFamiRepository()
