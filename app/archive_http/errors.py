from __future__ import annotations


class ArchiveHttpError(RuntimeError):
    """Base error for HLS TS archive HTTP access."""


class ArchiveHttpAuthError(ArchiveHttpError):
    """Raised when authentication data is missing or rejected."""


class ArchiveHttpDataError(ArchiveHttpError):
    """Raised when the archive HTTP API returns invalid data."""


class ArchiveHttpResponseError(ArchiveHttpDataError):
    """Compatibility alias for invalid HTTP response payloads."""
