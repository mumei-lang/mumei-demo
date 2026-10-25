import pytest

from late_fee import late_fee


def test_late_fee_example():
    assert late_fee(3, 50) == 150


def test_late_fee_relation():
    assert late_fee(10, 20) >= 0


def test_late_fee_rejects_negative():
    with pytest.raises(ValueError):
        late_fee(-1, 20)
