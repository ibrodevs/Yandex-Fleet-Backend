from typing import Any


class AppException(Exception):
    """Base application exception with unified error format."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found", details: Any | None = None):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=404,
            details=details,
        )


class ValidationError(AppException):
    def __init__(self, message: str = "Validation error", details: Any | None = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details=details,
        )


class YandexApiError(AppException):
    def __init__(
        self,
        message: str = "Failed to request Yandex Fleet API",
        status_code: int = 502,
        details: Any | None = None,
    ):
        super().__init__(
            code="YANDEX_API_ERROR",
            message=message,
            status_code=status_code,
            details=details,
        )


class YandexRateLimitError(AppException):
    def __init__(
        self,
        message: str = "Yandex Fleet API rate limit exceeded",
        details: Any | None = None,
    ):
        super().__init__(
            code="YANDEX_RATE_LIMIT",
            message=message,
            status_code=429,
            details=details,
        )


class YandexAuthError(AppException):
    def __init__(
        self,
        message: str = "Yandex Fleet API authentication failed. Check credentials.",
        details: Any | None = None,
    ):
        super().__init__(
            code="YANDEX_AUTH_ERROR",
            message=message,
            status_code=401,
            details=details,
        )


class FilterError(AppException):
    def __init__(self, message: str = "Order filter evaluation failed", details: Any | None = None):
        super().__init__(
            code="FILTER_ERROR",
            message=message,
            status_code=500,
            details=details,
        )


class YandexOfferApiNotAvailableError(AppException):
    """
    Raised when operations on incoming order offers (accept/reject/skip) are attempted.
    Public Yandex Fleet API does NOT provide endpoints for incoming offers or neutral skip.
    """

    def __init__(
        self,
        message: str = "Public Yandex Fleet API does not expose this operation.",
        details: Any | None = None,
    ):
        super().__init__(
            code="YANDEX_OFFER_API_NOT_AVAILABLE",
            message=message,
            status_code=501,
            details=details,
        )


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Authentication required", details: Any | None = None):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=401,
            details=details,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Access forbidden for current user", details: Any | None = None):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403,
            details=details,
        )


class InternalError(AppException):
    def __init__(self, message: str = "Internal server error", details: Any | None = None):
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
            status_code=500,
            details=details,
        )
