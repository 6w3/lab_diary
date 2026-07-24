from app.services.multi_date import unique_drawn_dates


def test_unique_drawn_dates():
    props = [
        {"proposed_drawn_on": "2020-10-14"},
        {"proposed_drawn_on": "2020-10-14"},
        {"proposed_drawn_on": "2021-06-03"},
        {"proposed_drawn_on": ""},
        {},
    ]
    assert unique_drawn_dates(props) == ["2020-10-14", "2021-06-03"]
