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



# ─── Conteo previo en paralelo ───────────────────────────────────────────────
# Regresión: los 8 COUNT corrían en serie (~63 s en producción) y el proxy de
# IIS cortaba el preview con 502. Ahora corren en paralelo.


class _RepoLento:
    def __init__(self, total: int, demora: float = 0.4, falla: bool = False) -> None:
        self.total, self.demora, self.falla = total, demora, falla

    def get_total(self, desde, hasta, **_kw) -> int:
        import time
        time.sleep(self.demora)
        if self.falla:
            raise RuntimeError("timeout simulado")
        return self.total


def _parchear_modulos(monkeypatch, repos: dict[str, _RepoLento]) -> None:
    from efdi.services import extraction_soporte_unificado as su
    monkeypatch.setattr(su, "_FACTURABLES", [
        ("demanda-inducida", lambda: repos["demanda-inducida"], None, None),
        ("findrisc", lambda: repos["findrisc"], None, None),
    ])
    monkeypatch.setattr(su, "_REGIMEN_SIMPLE", [
        ("vacunacion", lambda: repos["vacunacion"], None, None),
    ])
    monkeypatch.setattr(su, "get_caracterizacion_repository", lambda: repos["caracterizacion-familiar"])


def test_conteo_por_modulo_corre_en_paralelo(monkeypatch):
    import time
    from efdi.services.extraction_soporte_unificado import conteo_por_modulo
    _parchear_modulos(monkeypatch, {
        "demanda-inducida": _RepoLento(10), "findrisc": _RepoLento(20),
        "vacunacion": _RepoLento(30), "caracterizacion-familiar": _RepoLento(40),
    })
    t = time.monotonic()
    conteo = conteo_por_modulo(date(2026, 9, 1), date(2026, 9, 30), facturas=None, regimen="SUBSIDIADO")
    duracion = time.monotonic() - t
    assert conteo == {"demanda-inducida": 10, "findrisc": 20, "vacunacion": 30, "caracterizacion-familiar": 40}
    assert list(conteo) == ["demanda-inducida", "findrisc", "vacunacion", "caracterizacion-familiar"]
    assert duracion < 1.2, f"en serie serían ~1.6 s; tardó {duracion:.2f} s"


def test_conteo_por_modulo_un_modulo_que_falla_no_tumba_a_los_demas(monkeypatch):
    from efdi.services.extraction_soporte_unificado import conteo_por_modulo
    _parchear_modulos(monkeypatch, {
        "demanda-inducida": _RepoLento(10), "findrisc": _RepoLento(0, falla=True),
        "vacunacion": _RepoLento(30), "caracterizacion-familiar": _RepoLento(40),
    })
    conteo = conteo_por_modulo(date(2026, 9, 1), date(2026, 9, 30), facturas=None, regimen="SUBSIDIADO")
    assert conteo == {"demanda-inducida": 10, "findrisc": 0, "vacunacion": 30, "caracterizacion-familiar": 40}
