"""Stable error codes exposed in the {"error": {"code": ...}} contract."""

from enum import StrEnum


class ErrorCode(StrEnum):
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN_HOST = "FORBIDDEN_HOST"
    HOST_NOT_FOUND = "HOST_NOT_FOUND"
    HOSTNAME_TAKEN = "HOSTNAME_TAKEN"
    ENROLLMENT_DISABLED = "ENROLLMENT_DISABLED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL = "INTERNAL"
