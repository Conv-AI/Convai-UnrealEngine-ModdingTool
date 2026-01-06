"""Custom exceptions for the Convai Modding Tool."""


class ConvaiToolError(Exception):
    """Base exception for Convai Modding Tool."""
    pass


class ConfigurationError(ConvaiToolError):
    """Configuration or prerequisite errors."""
    pass


class DownloadError(ConvaiToolError):
    """Download failures."""
    pass


class ProjectError(ConvaiToolError):
    """Project creation or modification errors."""
    pass


class BuildError(ConvaiToolError):
    """Build/compilation errors."""
    pass

