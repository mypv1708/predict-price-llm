from __future__ import annotations


class AppError(Exception):
    status_code = 500

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class BadRequestError(AppError):
    status_code = 400


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class PayloadTooLargeError(AppError):
    status_code = 413


class UpstreamError(AppError):
    status_code = 502


class UpstreamUnavailableError(AppError):
    status_code = 503


class UpstreamTimeoutError(AppError):
    status_code = 504
