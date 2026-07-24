from types import SimpleNamespace

from app.services.label_aliases import normalize_alias_label
from app.services.markers import MARKER_SEED, match_marker, resolve_marker


def _catalog():
    return [
        SimpleNamespace(
            **{k: v for k, v in item.items() if k in {"code", "name_cs", "name_en", "default_unit"}}
        )
        for item in MARKER_SEED
    ]


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


def test_resolve_user_alias():
    aliases = {normalize_alias_label("HAD AM S WeirdAST"): "ast"}
    m = resolve_marker("HAD AM S WeirdAST", _catalog(), user_aliases=aliases)
    assert m is not None
    assert m.code == "ast"


def test_normalize_alias_strips_lab_prefix():
    assert normalize_alias_label("HAD AM S WeirdAST") == "weirdast"
    assert normalize_alias_label("  Hemoglobin  ") == "hemoglobin"


def test_match_alp():
    m = match_marker("S_ALP", _catalog())
    assert m is not None
    assert m.code == "alp"


def test_match_neutrophils_abs_spaced():
    m = match_marker("Neutrofily abs. počet", _catalog())
    assert m is not None
    assert m.code == "neutrophils_abs"


def test_match_neutrophils_abs_glued():
    m = match_marker("Neutrofilyabs.počet", _catalog())
    assert m is not None
    assert m.code == "neutrophils_abs"


def test_match_triacylglyceroly():
    m = match_marker("S_Triacylglyceroly", _catalog())
    assert m is not None
    assert m.code == "triglycerides"


def test_match_anti_tg():
    m = match_marker("S_anti-TG", _catalog())
    assert m is not None
    assert m.code == "anti_tg"


def test_match_immature_granulocytes_abs():
    m = match_marker("Nezralégranulocytyabs.počet", _catalog())
    assert m is not None
    assert m.code == "ig_abs"


def test_match_relative_neutrophils():
    m = match_marker("B_Neutrofily", _catalog())
    assert m is not None
    assert m.code == "neutrophils"
