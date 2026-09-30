"""nblm2obsidian - Import publicly shared Google NotebookLM notebooks into Obsidian vaults."""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "nblm2obsidian contributors"
__license__ = "MIT"

from .models import (
    Notebook,
    NotebookMetadata,
    Source,
    Note,
    SourceType,
    NoteType,
    parse_notebook_url,
    sanitize_filename,
)
from .errors import (
    Nblm2ObsidianError,
    InvalidURLError,
    NotebookNotAccessibleError,
    NotebookNotFoundError,
    ExtractionError,
    NetworkError,
    VaultError,
    ValidationError,
)
from .extractor import PublicNotebookExtractor, ExtractionResult
from .notebooklm import import_notebook, inspect_notebook_public, get_notebook_sources, export_to_markdown, ImportResult
from .obsidian import VaultWriter, create_vault_structure

__all__ = [
    # Models
    "Notebook",
    "NotebookMetadata",
    "Source",
    "Note",
    "SourceType",
    "NoteType",
    "parse_notebook_url",
    "sanitize_filename",
    # Errors
    "Nblm2ObsidianError",
    "InvalidURLError",
    "NotebookNotAccessibleError",
    "NotebookNotFoundError",
    "ExtractionError",
    "NetworkError",
    "VaultError",
    "ValidationError",
    # Extractor
    "PublicNotebookExtractor",
    "ExtractionResult",
    # High-level operations
    "import_notebook",
    "inspect_notebook_public",
    "get_notebook_sources",
    "export_to_markdown",
    "ImportResult",
    # Obsidian
    "VaultWriter",
    "create_vault_structure",
]