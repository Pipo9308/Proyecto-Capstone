import pytest

from app.core.rut import compute_dv, is_valid_rut, normalize_rut


@pytest.mark.parametrize(
    "raw",
    ["12.345.678-5", "12345678-5", "123456785", " 12 345 678 - 5 ", "11.111.111-1", "11111111-1"],
)
def test_valid_ruts_are_normalized(raw):
    assert normalize_rut(raw) in {"12345678-5", "11111111-1"}


def test_canonical_format_has_no_dots_and_uppercase_k():
    k_body = next(str(n) for n in range(1_000_000, 2_000_000) if compute_dv(str(n)) == "K")

    assert normalize_rut(f"{k_body}-k") == f"{k_body}-K"


def test_check_digit_zero_and_ten():
    assert compute_dv("11111111") == "1"
    zero_body = next(str(n) for n in range(1_000_000, 2_000_000) if compute_dv(str(n)) == "0")
    assert normalize_rut(f"{zero_body}-0") == f"{zero_body}-0"


def test_seven_digit_ruts_are_accepted():
    body = "5000000"

    assert normalize_rut(f"{body}-{compute_dv(body)}") == f"{body}-{compute_dv(body)}"


@pytest.mark.parametrize("raw", ["12.345.678-4", "12345678-K", "11111111-2"])
def test_wrong_check_digit_is_rejected(raw):
    with pytest.raises(ValueError, match="verificador"):
        normalize_rut(raw)


@pytest.mark.parametrize("raw", ["", "abc", "123", "1234567890-1", "12.345.67x-5", None, "12-3"])
def test_bad_shapes_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_rut(raw)


def test_is_valid_rut():
    assert is_valid_rut("12.345.678-5") is True
    assert is_valid_rut("12.345.678-0") is False
