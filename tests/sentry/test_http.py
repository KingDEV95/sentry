import platform
from unittest.mock import MagicMock, patch

import brotli
import pytest
import responses
from django.core.exceptions import SuspiciousOperation
from urllib3.util.connection import HAS_IPV6

from sentry import http
from sentry.testutils.helpers import override_blocklist


@responses.activate
@patch("socket.getaddrinfo")
def test_simple(mock_getaddrinfo: MagicMock) -> None:
    mock_getaddrinfo.return_value = [(2, 1, 6, "", ("81.0.0.1", 0))]
    responses.add(responses.GET, "http://example.com", body="foo bar")

    resp = http.safe_urlopen("http://example.com")
    data = http.safe_urlread(resp)
    assert data.decode("utf-8") == "foo bar"

    request = responses.calls[0].request
    assert "User-Agent" in request.headers
    assert "gzip" in request.headers.get("Accept-Encoding", "")


@override_blocklist("127.0.0.1", "::1", "10.0.0.0/8")
# XXX(dcramer): we can't use responses here as it hooks Session.send
# @responses.activate
def test_ip_blacklist_ipv4() -> None:
    with pytest.raises(SuspiciousOperation):
        http.safe_urlopen("http://127.0.0.1")
    with pytest.raises(SuspiciousOperation):
        http.safe_urlopen("http://10.0.0.10")
    with pytest.raises(SuspiciousOperation):
        # '2130706433' is dword for '127.0.0.1'
        http.safe_urlopen("http://2130706433")


@pytest.mark.skipif(not HAS_IPV6, reason="needs ipv6")
@override_blocklist("::1")
def test_ip_blacklist_ipv6() -> None:
    with pytest.raises(SuspiciousOperation):
        http.safe_urlopen("http://[::1]")


@pytest.mark.skipif(HAS_IPV6, reason="stub for non-ipv6 systems")
@override_blocklist("::1")
@patch("socket.getaddrinfo")
def test_ip_blacklist_ipv6_fallback(mock_getaddrinfo: MagicMock) -> None:
    mock_getaddrinfo.return_value = [(10, 1, 6, "", ("::1", 0, 0, 0))]
    with pytest.raises(SuspiciousOperation):
        http.safe_urlopen("http://[::1]")


@pytest.mark.skipif(
    platform.system() == "Darwin", reason="macOS is always broken, see comment in sentry/http.py"
)
@override_blocklist("127.0.0.1")
def test_garbage_ip() -> None:
    with pytest.raises(SuspiciousOperation):
        # '0177.0000.0000.0001' is an octal for '127.0.0.1'
        http.safe_urlopen("http://0177.0000.0000.0001")


@responses.activate
def test_fetch_file() -> None:
    responses.add(
        responses.GET, "http://example.com", body="foo bar", content_type="application/json"
    )

    result = http.fetch_file(url="http://example.com", domain_lock_enabled=False)
    assert result.body == b"foo bar"


@responses.activate
def test_fetch_file_brotli() -> None:
    body = brotli.compress(b"foo bar")
    responses.add(
        responses.GET,
        "http://example.com",
        body=body,
        content_type="application/json",
        adding_headers={"Content-Encoding": "br"},
    )

    result = http.fetch_file(url="http://example.com", domain_lock_enabled=False)
    assert result.body == b"foo bar"
