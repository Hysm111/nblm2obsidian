"""High-level NotebookLM operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .extractor import PublicNotebookExtractor, inspect_notebook, list_sources
from .markdown import generate_all_markdown
from .models import Notebook, NotebookMetadata, Source, Note
from .obsidian import VaultWriter, create_vault_structure
from .errors import (
    InvalidURLError,
    NotebookNotAccessibleError,
    NotebookNotFoundError,
    VaultError,
)


@dataclass
class ImportResult:
    """Result of an import operation."""
    notebook: Notebook
    target_dir: Path
    written_files: list[Path]
    warnings: list[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


async def import_notebook(
    url: str,
    vault_path: Path | str,
    folder: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> ImportResult:
    """Import a public NotebookLM notebook into an Obsidian vault."""
    vault_path = Path(vault_path).expanduser().resolve()
    
    # Extract notebook content
    async with PublicNotebookExtractor(verbose=verbose) as extractor:
        result = await extractor.extract_from_url(url)
    
    notebook = result.notebook
    warnings = result.warnings
    
    # Write to vault
    writer = VaultWriter(vault_path, folder=folder, force=force, dry_run=dry_run)
    target_dir, written_files = writer.write(notebook)
    
    return ImportResult(
        notebook=notebook,
        target_dir=target_dir,
        written_files=written_files,
        warnings=warnings,
    )


async def inspect_notebook_public(url: str, verbose: bool = False) -> dict[str, Any]:
    """Inspect what's publicly accessible in a notebook."""
    return await inspect_notebook(url, verbose=verbose)


async def get_notebook_sources(url: str, verbose: bool = False) -> list[dict[str, Any]]:
    """Get list of sources from a public notebook."""
    return await list_sources(url, verbose=verbose)


def export_to_markdown(
    notebook: Notebook,
    output_dir: Path | str,
    force: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """Export notebook to markdown files in a directory (not necessarily a vault)."""
    output_dir = Path(output_dir).expanduser().resolve()
    
    if output_dir.exists() and not force and not dry_run:
        raise VaultError(f"Output directory already exists: {output_dir}. Use --force to overwrite.")
    
    if not dry_run:
        if output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "Sources").mkdir(exist_ok=True)
        (output_dir / "Notes").mkdir(exist_ok=True)
        (output_dir / "Assets").mkdir(exist_ok=True)
    
    markdown_files = generate_all_markdown(notebook)
    written = []
    
    for rel_path, content in markdown_files.items():
        file_path = output_dir / rel_path
        if not dry_run:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        written.append(file_path)
    
    return written