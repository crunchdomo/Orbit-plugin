import pytest

from app.pagination import parse_page


def test_defaults_to_first_page():
    assert parse_page(None, size=20, total=45).number == 1


def test_clamps_past_the_last_page():
    page = parse_page("99", size=20, total=45)
    assert page.number == 3
    assert not page.has_next


def test_non_numeric_falls_back_to_first_page():
    assert parse_page("abc", size=20, total=45).number == 1


def test_offset_matches_page():
    assert parse_page("2", size=20, total=45).offset == 20


def test_empty_total_still_has_one_page():
    assert parse_page("1", size=20, total=0).pages == 1


def test_rejects_zero_size():
    with pytest.raises(ValueError):
        parse_page("1", size=0, total=10)
