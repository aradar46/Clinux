"""
Clinux core exception hierarchy.
"""


class ClinuxError(Exception):
    """Base exception for all Clinux errors."""
    pass


class ClinuxPermissionError(ClinuxError):
    """Raised when elevated privileges (root/sudo) are required or permission is denied."""
    pass


class CommandNotFoundError(ClinuxError):
    """Raised when a required system command or binary is not found on PATH."""
    pass


class UnsupportedSystemError(ClinuxError):
    """Raised when an operation is attempted on an unsupported system architecture or OS."""
    pass


class ConfigurationError(ClinuxError):
    """Raised when configuration parsing or validation fails."""
    pass


class ExecutionError(ClinuxError):
    """Raised when a subprocess or command fails."""
    def __init__(self, message: str, returncode: int = -1, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
