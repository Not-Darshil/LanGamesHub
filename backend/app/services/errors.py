"""Errors raised by the service layer and translated to HTTP responses by the API."""

from __future__ import annotations


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409


class Forbidden(ServiceError):
    status_code = 403
