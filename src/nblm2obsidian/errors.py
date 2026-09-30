"""Custom exceptions for nblm2obsidian."""

from __future__ import annotations


class Nblm2ObsidianError(Exception):
    """Base exception for nblm2obsidian."""
    pass


class InvalidURLError(Nblm2ObsidianError):
    """Raised when the provided URL is not a valid NotebookLM share URL."""
    pass


class NotebookNotAccessibleError(Nblm2ObsidianError):
    """Raised when a notebook cannot be accessed (private, deleted, etc.)."""
    def __init__(self, message: str, notebook_id: str | None = None, url: str | None = None):
        super().__init__(message)
        self.notebook_id = notebook_id
        self.url = url


class NotebookNotFoundError(Nblm2ObsidianError):
    """Raised when a notebook does not exist."""
    def __init__(self, notebook_id: str):
        super().__init__(f"Notebook not found: {notebook_id}")
        self.notebook_id = notebook_id


class ExtractionError(Nblm2ObsidianError):
    """Raised when content extraction fails."""
    def __init__(self, message: str, source: str | None = None):
        super().__init__(message)
        self.source = source


class NetworkError(Nblm2ObsidianError):
    """Raised for network-related errors."""
    def __init__(self, message: str, url: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class VaultError(Nblm2ObsidianError):
    """Raised for vault-related errors."""
    pass


class ValidationError(Nblm2ObsidianError):
    """Raised for validation errors."""
    pass