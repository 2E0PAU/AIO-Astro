"""Errors callers can present without knowing a transport's implementation."""


class AstroError(Exception):
    """Base application error."""


class DeviceError(AstroError):
    """An equipment operation failed or its outcome is unknown."""


class ProtocolError(DeviceError):
    """A peer sent an invalid or unsupported response."""


class SequenceBusy(AstroError):
    """A capture sequence already owns this runner."""
