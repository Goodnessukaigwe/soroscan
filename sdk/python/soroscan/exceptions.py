"""Exception classes for SoroScan SDK."""


class SoroScanError(Exception):
    """Base exception for all SoroScan SDK errors."""

    pass


class SoroScanAPIError(SoroScanError):
    """Raised when the API returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response_data: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class SoroScanAuthError(SoroScanAPIError):
    """Raised when authentication fails (401/403)."""

    pass


class SoroScanNotFoundError(SoroScanAPIError):
    """Raised when a resource is not found (404)."""

    pass


class SoroScanRateLimitError(SoroScanAPIError):
    """Raised when rate limit is exceeded (429)."""

    pass


class SoroScanValidationError(SoroScanAPIError):
    """Raised when request validation fails (400)."""

    pass
