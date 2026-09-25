class VeraError(Exception):
    """Base error for expected VERA failures."""


class ConfigurationError(VeraError):
    """Raised when a configured integration cannot be initialized."""


class ProviderError(VeraError):
    """Raised when a language-model provider fails or returns invalid data."""


class SourceError(VeraError):
    """Raised when an authoritative source cannot be queried."""


class StreamError(VeraError):
    """Raised when an event stream or PCAP cannot be processed safely."""
