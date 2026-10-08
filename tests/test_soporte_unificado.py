"""Tests de Soporte Unificado — foco en el bug de datos corregido:

Antes, una familia de Caracterización Familiar donde NINGÚN integrante tenía
número de documento se descartaba en silencio (`continue`) del índice
unificado, mientras que el módulo standalone sí la incluía (carpeta
`FAM_<clave>`). Esto hacía que el conteo de Caracterización Familiar en el
unificado pudiera ser menor que su `get_total()` individual — no por la
deduplicación esperada (una persona en N módulos cuenta 1 vez en vez de N),
sino por una pérdida real de familias.
"""
from datetime import date

from efdi.domain.models import FamiliaCaracterizada, RegistroCaracterizacion
from efdi.services.extraction_soporte_unificado import _jefe_doc_key


def _reg(**overrides) -> RegistroCaracterizacion:
    base = dict(
        departamento="13", municipio="001", area="1", corregimiento="00",
        barrio_vereda="002", manzana="03", vivienda="0001", familia="1",
        ciuf="100001", tipo_documento="CC", num_documento=None,
        nombres_apellidos="JUAN PEREZ", parentesco="JEFE DE FAMILIA",
    )
    base.update(overrides)
    return RegistroCaracterizacion(**base)


def _familia(registros: list[RegistroCaracterizacion], key: str = "fam-key-1") -> FamiliaCaracterizada:
    return FamiliaCaracterizada(familia_key=key, registros=registros)


def test_jefe_doc_key_familia_con_documento_ancla_por_cc():
    fam = _familia([
        _reg(num_documento="123", parentesco="JEFE DE FAMILIA", nombres_apellidos="ANA GOMEZ"),
        _reg(num_documento="456", parentesco="HIJO(A)"),
    ])
    doc_key, nombre = _jefe_doc_key(fam)
    assert doc_key == "CC_123"
    assert nombre == "ANA GOMEZ"


def test_jefe_doc_key_sin_jefe_explicito_cae_al_primero_con_documento():
    fam = _familia([
        _reg(num_documento=None, parentesco="HIJO(A)"),
        _reg(num_documento="789", parentesco="CONYUGE"),
    ])
    doc_key, _ = _jefe_doc_key(fam)
    assert doc_key == "CC_789"


def test_jefe_doc_key_familia_sin_ningun_documento_NO_se_pierde():
    """Regresión del bug: antes esta función devolvía `None` y la familia se
    descartaba del índice unificado (`continue` en `recolectar_universo`),
    perdiéndose en silencio. Ahora debe devolver el mismo fallback que usa el
    módulo standalone (`FamiliaCaracterizada.doc_key`): `FAM_<clave>`."""
    fam = _familia([
        _reg(num_documento=None, parentesco="JEFE DE FAMILIA"),
        _reg(num_documento=None, parentesco="HIJO(A)"),
    ], key="13|001|1|00|002|03|0001|1|100001")

    doc_key, nombre = _jefe_doc_key(fam)

    assert doc_key is not None
    assert doc_key.startswith("FAM_")
    # El jefe sigue identificado por parentesco aunque no tenga documento —
    # el nombre se puede mostrar igual, solo el doc_key cae al fallback.
    assert nombre == "JUAN PEREZ"
    # Debe coincidir EXACTAMENTE con el fallback del módulo standalone, para
    # que ambos caminos (unificado vs. individual) generen la misma carpeta.
    assert doc_key == fam.doc_key


def test_jefe_doc_key_sin_jefe_ni_documento_ni_nombre():
    """Caso extremo: nadie tiene parentesco 'JEFE DE FAMILIA' ni documento.
    `fam.jefe` es None → doc_key cae a FAM_<clave> y nombre queda None (no se
    inventa un nombre de otro integrante)."""
    fam = _familia([
        _reg(num_documento=None, parentesco="HIJO(A)"),
        _reg(num_documento=None, parentesco="CONYUGE"),
    ])
    doc_key, nombre = _jefe_doc_key(fam)
    assert doc_key.startswith("FAM_")
    assert nombre is None
    assert doc_key == fam.doc_key


def test_jefe_doc_key_siempre_consistente_con_doc_key_standalone():
    """Para cualquier familia, el doc_key que usa Soporte Unificado debe ser
    idéntico al que usaría el módulo Caracterización Familiar standalone —
    es la garantía de que ambos caminos no diverjan en el futuro."""
    casos = [
        _familia([_reg(num_documento="1", parentesco="JEFE DE FAMILIA")]),
        _familia([_reg(num_documento=None, parentesco="JEFE DE FAMILIA"),
                   _reg(num_documento="2", parentesco="HIJO(A)")]),
        _familia([_reg(num_documento=None, parentesco="HIJO(A)"),
                   _reg(num_documento=None, parentesco="CONYUGE")], key="otra-clave"),
    ]
    for fam in casos:
        doc_key, _ = _jefe_doc_key(fam)
        assert doc_key == fam.doc_key
