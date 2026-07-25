from types import SimpleNamespace

from app.services.label_aliases import normalize_alias_label
from app.services.markers import MARKER_SEED, extract_lis_code_hint, match_marker, resolve_marker


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


def test_resolve_code_hint_case_insensitive():
    m = resolve_marker("x", _catalog(), code_hint="HGB")
    assert m is not None
    assert m.code == "hgb"


def test_resolve_smart_skips_fuzzy_without_code():
    # Without Smart code, fuzzy would match; allow_fuzzy=False must not invent bind.
    m = resolve_marker("Hemoglobin", _catalog(), allow_fuzzy=False)
    assert m is None


def test_lis_bracket_hgb():
    assert extract_lis_code_hint("Hemoglobin [HGB]") == "hgb"
    m = resolve_marker("Hemoglobin [HGB]", _catalog(), allow_fuzzy=False)
    assert m is not None
    assert m.code == "hgb"


def test_fuzzy_hemoglobin():
    m = resolve_marker("Hemoglobin", _catalog(), allow_fuzzy=True)
    assert m is not None
    assert m.code == "hgb"


def test_resolve_smart_keeps_user_alias_without_fuzzy():
    aliases = {normalize_alias_label("Weird lab label"): "ast"}
    m = resolve_marker(
        "Weird lab label",
        _catalog(),
        user_aliases=aliases,
        allow_fuzzy=False,
    )
    assert m is not None
    assert m.code == "ast"


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


def test_match_transferrin_sat():
    m = match_marker("Saturace transferinu", _catalog())
    assert m is not None
    assert m.code == "transferrin_sat"


def test_match_hs_crp():
    m = match_marker("hs-CRP", _catalog())
    assert m is not None
    assert m.code == "hs_crp"


def test_match_nt_pro_bnp():
    m = match_marker("NT-proBNP", _catalog())
    assert m is not None
    assert m.code == "nt_pro_bnp"


def test_match_amylase():
    m = match_marker("S_Amyláza", _catalog())
    assert m is not None
    assert m.code == "amylase"


def test_match_ca19_9():
    m = match_marker("CA 19-9", _catalog())
    assert m is not None
    assert m.code == "ca19_9"


def test_match_ca72_4_not_calcium():
    m = match_marker("Ca 72-4", _catalog())
    assert m is not None
    assert m.code == "ca72_4"


def test_match_thyroglobulin_not_triglycerides():
    m = match_marker("Tg (tyreoglobulin)", _catalog())
    assert m is not None
    assert m.code == "thyroglobulin"


def test_match_bare_tg_still_triglycerides():
    m = match_marker("TG", _catalog())
    assert m is not None
    assert m.code == "triglycerides"


def test_match_scc():
    m = match_marker("SCC", _catalog())
    assert m is not None
    assert m.code == "scc"


def test_match_urine_ph_not_eosinophils():
    m = match_marker("pH", _catalog())
    assert m is not None
    assert m.code == "urine_ph"


def test_enrich_overrides_stale_ph_code_hint():
    from app.services.import_process import enrich_proposals

    catalog = _catalog()
    out = enrich_proposals(
        [{"label": "pH", "marker_code": "eosinophils_abs", "value": 5.0, "unit": "ph"}],
        catalog,
    )
    assert out[0]["marker_code"] == "urine_ph"


def test_enrich_drops_stale_code_on_junk_note():
    from app.services.import_process import enrich_proposals

    catalog = _catalog()
    out = enrich_proposals(
        [{"label": "Poznámka k sed.1", "marker_code": "potassium", "value": 0.0, "unit": "pseudov"}],
        catalog,
    )
    assert out[0]["marker_code"] == ""


def test_match_note_not_potassium():
    assert match_marker("Poznámka k sed.1", _catalog()) is None


def test_match_tromb_hematokrit_pct():
    m = match_marker("Tromb. hematokrit", _catalog())
    assert m is not None
    assert m.code == "pct"


def test_match_vma_and_hiiaa():
    assert match_marker("Kys.vanilmadlová", _catalog()).code == "vma"
    assert match_marker("5-HIO", _catalog()).code == "hiiaa"


def test_match_egfr_mdrd_alias():
    m = match_marker("Vypočet GF MDRD kre.", _catalog())
    assert m is not None
    assert m.code == "egfr"


def test_seed_codes_unique():
    codes = [m["code"] for m in MARKER_SEED]
    assert len(codes) == len(set(codes))
