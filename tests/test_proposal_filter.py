from app.services.proposal_filter import filter_proposals, is_junk_label


def test_junk_cislo_sestaveni():
    assert is_junk_label("číslosestavení")
    assert is_junk_label("číslo sestavení")
    assert is_junk_label("Cislo sestaveni 3")


def test_junk_cp_platce():
    assert is_junk_label("ČP")
    assert is_junk_label("ČP: 8606254679")
    assert is_junk_label("Plátce")
    assert is_junk_label("Plátce: 094")


def test_keeps_real_analytes():
    assert not is_junk_label("ALP")
    assert not is_junk_label("S_Triacylglyceroly")
    assert not is_junk_label("Neutrofily abs. počet")
    assert not is_junk_label("S_P")  # phosphorus
    assert not is_junk_label("anti-TG")


def test_filter_drops_junk_and_dedupes():
    rows = [
        {"label": "ČP", "value": 8606254679.0, "proposed_drawn_on": "2026-04-22"},
        {"label": "ALP", "value": 1.26, "unit": "ukat/l", "proposed_drawn_on": "2026-04-22"},
        {"label": "ALP", "value": 1.26, "unit": "ukat/l", "proposed_drawn_on": "2026-04-22"},
        {"label": "Plátce", "value": 94.0, "proposed_drawn_on": "2026-04-22"},
        {
            "label": "S_ALP",
            "value": 1.26,
            "unit": "ukat/l",
            "marker_code": "alp",
            "proposed_drawn_on": "2026-04-22",
            "lab_ref_low": 0.58,
        },
    ]
    out = filter_proposals(rows)
    assert len(out) == 1
    assert out[0]["marker_code"] == "alp"
    assert out[0].get("lab_ref_low") == 0.58


def test_dedupe_same_code_different_labels():
    rows = [
        {"label": "Leukocyty", "marker_code": "wbc", "value": 4.2, "proposed_drawn_on": "2026-04-22"},
        {"label": "B_Leukocyty", "marker_code": "wbc", "value": 4.2, "proposed_drawn_on": "2026-04-22"},
    ]
    out = filter_proposals(rows)
    assert len(out) == 1
