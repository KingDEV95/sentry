import pytest

from sentry.utils.iterators import advance, chunked, shingle


def test_chunked() -> None:
    assert list(chunked(range(5), 5)) == [[0, 1, 2, 3, 4]]

    assert list(chunked(range(10), 4)) == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]


def test_advance() -> None:
    i = iter(range(10))

    advance(5, i)  # [0, 1, 2, 3, 4]
    assert next(i) == 5

    advance(10, i)  # don't raise if slicing past end of iterator
    with pytest.raises(StopIteration):
        next(i)


def test_shingle() -> None:
    assert list(shingle(5, "x")) == []
    assert list(shingle(2, ("foo", "bar", "baz"))) == [("foo", "bar"), ("bar", "baz")]
