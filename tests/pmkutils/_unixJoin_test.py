import pytest

from rcluster.pmkutils import _unixJoin

left = "hello/this"
right = "is.text"
val = "hello/this/is.text"


def test_valid():
    assert _unixJoin(left, right) == val


def test_bad_left():
    with pytest.raises(TypeError) as exc:
        _unixJoin(None, right)
    assert "unsupported operand type" in str(exc.value)


def test_bad_right():
    with pytest.raises(TypeError) as exc:
        _unixJoin(left, None)
    assert "Can't convert 'NoneType'" in str(exc.value)
