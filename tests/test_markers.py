from types import SimpleNamespace

from app.services.markers import MARKER_SEED, match_marker, resolve_marker


def _catalog():
    return [SimpleNamespace(**{k: v for k, v in item.items() if k in {"code", "name_cs", "name_en", "default_unit"}}) for item in MARKER_SEED]


def test_match_barvivo_erytr_mch():
    m = match_marker("Barvivo erytr. MCH", _catalog())
    assert m is not None
    assert m.code == "mch"


def test_match_distr_kriv_ery_rdw():
    m = match_marker("Distr.křiv.ery RDW", _catalog())
    assert m is not None
    assert m.code == "rdw"


def test_match_erytrocyty():
    m = match_marker("Erytrocyty RBC", _catalog())
    assert m is not None
    assert m.code == "rbc"


def test_resolve_prefers_code_hint():
    m = resolve_marker("Something weird", _catalog(), code_hint="mpv")
    assert m is not None
    assert m.code == "mpv"


def test_unknown_stays_unmatched():
    assert match_marker("Super special home assay XYZ99", _catalog()) is None
