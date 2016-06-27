import pytest

from rcluster.pmkutils import _unix_path

val = "hello/this/is.text"


def test_valid():
    assert _unix_path(val) == val


def test_windows():
    assert _unix_path("hello\\this\\is.text") == val


def test_mix():
    assert _unix_path("hello\\this/is.text") == val


def test_none():
    with pytest.raises(TypeError) as exc:
        _unix_path(None)
    assert "join() argument must be str or bytes" in str(exc.value)
