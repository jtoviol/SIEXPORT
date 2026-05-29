"""Generador determinista de datos falsos para desarrollo y testing.

Genera registros que respetan el contrato Atencion: mismos campos que el SELECT
final de la query SQL, varios afiliados con 1-5 atenciones cada uno.
"""
import random
from datetime import date, timedelta

from efdi.domain.models import (
    Atencion,
    ModoIngreso,
    Regimen,
    Sexo,
    TipoDocumento,
)

SEED = 42

# Catálogo reducido de programas usado por el mock (cód, descripción)
PROGRAMAS_MOCK = [
    ("41", "Tamizaje para identificación de riesgo de Diabetes"),
    ("46", "Tamizaje para cáncer de cuello uterino"),
    ("21", "Valoración para la primera infancia"),
    ("34", "Consulta Prenatal primera vez (SMH)"),
    ("11", "Profilaxis y remoción de placa Bacteriana"),
    ("28", "Valoración de la salud bucal por odontología"),
    ("51", "Tamizaje para VIH"),
    ("19", "Suministro de micronutrientes durante Gestación"),
    ("A1", "Vacunación Covid 19"),
    ("06", "Vacunación VPH"),
]

NOMBRES_M = ["Juan", "Carlos", "Luis", "Andrés", "Diego", "Pedro", "Jorge", "Miguel", "David", "Mario"]
NOMBRES_F = ["María", "Ana", "Vanessa", "Laura", "Carolina", "Patricia", "Lucía", "Sandra", "Diana", "Camila"]
APELLIDOS = ["Toviol", "Pérez", "García", "Rodríguez", "Martínez", "López", "Gómez", "Díaz", "Vargas", "Hernández", "Ruiz", "Ortiz"]
MUNICIPIOS = [
    ("11001", "BOGOTÁ D.C.", "11", "BOGOTÁ"),
    ("05001", "MEDELLÍN", "05", "ANTIOQUIA"),
    ("76001", "CALI", "76", "VALLE DEL CAUCA"),
    ("08001", "BARRANQUILLA", "08", "ATLÁNTICO"),
    ("13001", "CARTAGENA", "13", "BOLÍVAR"),
    ("66001", "PEREIRA", "66", "RISARALDA"),
]
IPS = [
    "IPS MUTUALSER BOGOTÁ NORTE",
    "IPS MUTUALSER MEDELLÍN CENTRO",
    "IPS MUTUALSER CALI SUR",
    "CENTRO DE SALUD COMUNITARIO",
    "HOSPITAL MUNICIPAL",
]
CARGOS = [
    "Agente Educativo",
    "Coord/Aux. atención al usuario",
    "Gestor del riesgo / Gemas",
    "Coordinador gestión del riesgo",
    "Aux. de atención telefónica",
]
REMITENTES = [
    ("01", "Gestor en Salud de Grupo Comunitario Afiliado"),
    ("02", "Miembro de alianza de usuarios"),
    ("03", "Gestor en Salud de Grupo Comunitario Asociado"),
    ("99", "Otros"),
]
CURSOS_VIDA = [
    "Primera infancia",
    "Infancia",
    "Adolescencia",
    "Juventud",
    "Adultez",
    "Vejez",
]
RIAS_GRUPOS = [
    "Cardiovascular y metabólico",
    "Materno perinatal",
    "Enfermedades infecciosas",
    "Cáncer",
    "Salud mental",
]


def _random_phone(rng: random.Random) -> str:
    return f"3{rng.randint(0, 99):02d}{rng.randint(1000000, 9999999)}"


def _random_email(rng: random.Random, nombre: str, apellido: str) -> str:
    dominios = ["gmail.com", "hotmail.com", "yahoo.com", "outlook.com"]
    return f"{nombre.lower()}.{apellido.lower()}{rng.randint(1, 99)}@{rng.choice(dominios)}"


def generar_atenciones(
    limite: int,
    desde: date,
    hasta: date,
    seed: int = SEED,
    offset: int = 0,
) -> list[Atencion]:
    """Genera `limite` atenciones deterministas en el rango [desde, hasta].

    `offset`: saltea los primeros N registros (para soportar lotes).
    Distribución: ~8-10 afiliados por cada 25-50 registros, c/u con 1-5 atenciones.
    """
    # Para que cada lote sea determinista pero distinto, mezclamos el offset al seed
    rng = random.Random(seed + offset * 7919)
    rango_dias = max((hasta - desde).days, 1)
    atenciones: list[Atencion] = []
    consecutivo = offset + 1

    # Generar afiliados hasta cubrir el límite exacto
    afiliado_idx = 0
    while len(atenciones) < limite:
        afiliado_idx += 1
        if afiliado_idx > 50_000:  # guarda dura por si algo se descontrola
            break

        sexo = rng.choice([Sexo.M, Sexo.F])
        nombres_pool = NOMBRES_M if sexo == Sexo.M else NOMBRES_F
        primer_nombre = rng.choice(nombres_pool)
        segundo_nombre = rng.choice(nombres_pool) if rng.random() < 0.5 else None
        primer_apellido = rng.choice(APELLIDOS)
        segundo_apellido = rng.choice(APELLIDOS) if rng.random() < 0.8 else None

        edad = rng.randint(1, 85)
        fecha_nac = date.today() - timedelta(days=edad * 365 + rng.randint(0, 364))
        tipo_doc = rng.choice([TipoDocumento.CC, TipoDocumento.TI, TipoDocumento.RC])
        num_doc = str(rng.randint(10000000, 99999999999))

        cod_mun, des_mun, cod_dep, des_dep = rng.choice(MUNICIPIOS)
        regimen = rng.choice(list(Regimen))
        curso_vida = rng.choice(CURSOS_VIDA)

        telefono_1 = _random_phone(rng)
        telefono_2 = _random_phone(rng) if rng.random() < 0.4 else None
        correo = _random_email(rng, primer_nombre, primer_apellido) if rng.random() < 0.7 else None
        direccion = f"Calle {rng.randint(1, 200)} # {rng.randint(1, 100)}-{rng.randint(1, 99)}"

        encuestador_nombre = f"{rng.choice(NOMBRES_M + NOMBRES_F)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        cargo = rng.choice(CARGOS)

        num_atenciones = rng.randint(1, min(5, limite - len(atenciones)))
        for _ in range(num_atenciones):
            if len(atenciones) >= limite:
                break

            cod_prog, des_prog = rng.choice(PROGRAMAS_MOCK)
            dias_offset = rng.randint(0, rango_dias)
            fecha_reg = desde + timedelta(days=dias_offset)
            fecha_at = fecha_reg + timedelta(days=rng.randint(0, 15)) if rng.random() < 0.6 else None
            cod_rem, des_rem = rng.choice(REMITENTES)

            atenciones.append(Atencion(
                seq_seragil=100000 + consecutivo,
                consecutivo=consecutivo,
                tipo_documento=tipo_doc,
                num_documento=num_doc,
                primer_nombre=primer_nombre,
                segundo_nombre=segundo_nombre,
                primer_apellido=primer_apellido,
                segundo_apellido=segundo_apellido,
                sexo=sexo,
                edad=edad,
                fecha_nacimiento=fecha_nac,
                direccion=direccion,
                telefono_1=telefono_1,
                telefono_2=telefono_2,
                correo=correo,
                departamento=des_dep,
                municipio=des_mun,
                curso_vida=curso_vida,
                regimen=regimen,
                fecha_registro=fecha_reg,
                fecha_atencion=fecha_at,
                cod_programa=cod_prog,
                des_programa=des_prog,
                ips_remite=rng.choice(IPS),
                ips_atiende=rng.choice(IPS),
                modo_ingreso=rng.choice(list(ModoIngreso)),
                cod_remitente=cod_rem,
                des_remitente=des_rem,
                des_otro_remitente="Voluntario barrio" if cod_rem == "99" else None,
                encuestador_nombre=encuestador_nombre,
                cargo_encuestador=cargo,
                rias_grupo_riesgo=rng.choice(RIAS_GRUPOS) if rng.random() < 0.5 else None,
                otra_rias=None,
                notificacion_obligatoria=rng.random() < 0.1,
                recuperacion_urgencias=rng.random() < 0.15,
                recuperacion_consulta_externa=rng.random() < 0.2,
            ))
            consecutivo += 1

    return atenciones
