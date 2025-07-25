from __future__ import annotations

import errno
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from requests import Response
from requests.adapters import RetryError
from requests.exceptions import RequestException

from sentry.utils import json

__all__ = (
    "ApiConnectionResetError",
    "ApiError",
    "ApiConflictError",
    "ApiHostError",
    "ApiTimeoutError",
    "ApiUnauthorized",
    "ApiRateLimitedError",
    "ApiInvalidRequestError",
    "IntegrationError",
    "IntegrationFormError",
    "UnsupportedResponseType",
)


class ApiError(Exception):
    """
    Base class for errors which arise while making outgoing requests to third-party APIs.
    """

    code: int | None = None

    def __init__(
        self,
        text: str,
        code: int | None = None,
        url: str | None = None,
        host: str | None = None,
        path: str | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        self.text = text
        self.url = url
        # we allow `host` and `path` to be passed in separately from `url` in case
        # either one is all we have
        self.host = host
        self.path = path
        self.json: dict[str, Any] | None = None
        self.xml: BeautifulSoup | None = None

        # TODO(dcramer): pull in XML support from Jira
        if text:
            try:
                self.json = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                if self.text[:5] == "<?xml":
                    # perhaps it's XML?
                    self.xml = BeautifulSoup(self.text, "xml")

        if url and not self.host:
            try:
                self.host = urlparse(url).netloc
            except ValueError:
                self.host = "[invalid URL]"

        if url and not self.path:
            try:
                self.path = urlparse(url).path
            except ValueError:
                self.path = "[invalid URL]"

        super().__init__(text[:1024])

    def __str__(self) -> str:
        return self.text

    @classmethod
    def from_response(cls, response: Response, url: str | None = None) -> ApiError:
        if response.status_code == 401:
            return ApiUnauthorized(response.text, url=url)
        elif response.status_code == 429:
            return ApiRateLimitedError(response.text, url=url)
        elif response.status_code == 409:
            return ApiConflictError(response.text, url=url)
        elif response.status_code == 400:
            return ApiInvalidRequestError(response.text, url=url)

        return cls(response.text, response.status_code, url=url)


class _RequestHasUrl(Protocol):
    @property
    def url(self) -> str: ...


class ApiHostError(ApiError):
    code = 503

    @classmethod
    def from_exception(cls, exception: Exception) -> ApiHostError:
        maybe_request = getattr(exception, "request", None)
        if maybe_request is not None:
            return cls.from_request(maybe_request)
        return cls("Unable to reach host")

    @classmethod
    def from_request(cls, request: _RequestHasUrl) -> ApiHostError:
        host = urlparse(request.url).netloc
        return cls(f"Unable to reach host: {host}", url=request.url)


class ApiRetryError(ApiError):
    code = 503

    @classmethod
    def from_exception(cls, exception: RetryError) -> ApiRetryError:
        msg = str(exception)
        return cls(msg)


class ApiTimeoutError(ApiError):
    code = 504

    @classmethod
    def from_exception(cls, exception: RequestException) -> ApiTimeoutError:
        maybe_request = getattr(exception, "request", None)
        if maybe_request is not None:
            return cls.from_request(maybe_request)
        return cls("Timed out reaching host")

    @classmethod
    def from_request(cls, request: _RequestHasUrl) -> ApiTimeoutError:
        host = urlparse(request.url).netloc
        return cls(f"Timed out attempting to reach host: {host}", url=request.url)


class ApiUnauthorized(ApiError):
    code = 401


class ApiRateLimitedError(ApiError):
    code = 429


class ApiConflictError(ApiError):
    code = 409


class ApiConnectionResetError(ApiError):
    code = errno.ECONNRESET


class ApiInvalidRequestError(ApiError):
    code = 400


class UnsupportedResponseType(ApiError):
    @property
    def content_type(self) -> str:
        return self.text


class IntegrationError(Exception):
    pass


class IntegrationInstallationConfigurationError(IntegrationError):
    """
    Error when external API access is blocked due to configuration issues
    like permissions, visibility changes, or invalid project settings.
    This is not a product error, but rather an integration setup issue
    that requires user intervention.
    """

    pass


class IntegrationResourceNotFoundError(IntegrationError):
    """
    Error when an external API resource is not found.
    """


class IntegrationProviderError(Exception):
    """Nonfatal errors generated by an external provider"""


class DuplicateDisplayNameError(IntegrationError):
    pass


class IntegrationFormError(IntegrationError):
    def __init__(self, field_errors: Mapping[str, Any] | None = None) -> None:
        error = "Invalid integration action"
        if field_errors:
            error = str(field_errors)

        super().__init__(error)

        self.field_errors = field_errors


class ClientError(RequestException):
    """4xx Error Occurred"""

    def __init__(self, status_code: str, url: str, response: Response | None = None) -> None:
        http_error_msg = f"{status_code} Client Error: for url: {url}"
        super().__init__(http_error_msg, response=response)
