"""Obsidian vault writing utilities."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .models import Notebook
from .markdown import generate_all_markdown
from .errors import VaultError


class VaultWriter:
    """Write notebook content to an Obsidian vault."""
    
    def __init__(
        self,
        vault_path: Path,
        folder: str | None = None,
        force: bool = False,
        dry_run: bool = False,
    ):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.folder = folder
        self.force = force
        self.dry_run = dry_run
        self._target_dir: Path | None = None
    
    @property
    def target_dir(self) -> Path:
        """Get the target directory for this notebook."""
        if self._target_dir is None:
            if self.folder:
                self._target_dir = self.vault_path / self.folder
            else:
                self._target_dir = self.vault_path
        return self._target_dir
    
    def validate_vault(self) -> None:
        """Validate that the vault path exists and is a directory."""
        if not self.vault_path.exists():
            raise VaultError(f"Vault path does not exist: {self.vault_path}")
        if not self.vault_path.is_dir():
            raise VaultError(f"Vault path is not a directory: {self.vault_path}")
    
    def prepare_target(self, notebook_title: str) -> Path:
        """Prepare the target directory for writing."""
        from .models import sanitize_filename
        
        if self.folder:
            # Use specified folder, sanitize it
            safe_folder = sanitize_filename(self.folder)
            target = self.vault_path / safe_folder
        else:
            # Use notebook title as folder
            safe_folder = sanitize_filename(notebook_title)
            target = self.vault_path / safe_folder
        
        if target.exists():
            if not self.force:
                raise VaultError(
                    f"Target directory already exists: {target}. Use --force to overwrite."
                )
            if not self.dry_run:
                shutil.rmtree(target)
        
        if not self.dry_run:
            target.mkdir(parents=True, exist_ok=True)
            (target / "Sources").mkdir(exist_ok=True)
            (target / "Notes").mkdir(exist_ok=True)
            (target / "Assets").mkdir(exist_ok=True)
        
        return target
    
    def write_notebook(self, notebook: Notebook, target_dir: Path) -> list[Path]:
        """Write all notebook files to the target directory."""
        written_files = []
        markdown_files = generate_all_markdown(notebook)
        
        for rel_path, content in markdown_files.items():
            file_path = target_dir / rel_path
            if not self.dry_run:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
            written_files.append(file_path)
        
        return written_files
    
    def write(
        self,
        notebook: Notebook,
    ) -> tuple[Path, list[Path]]:
        """Write notebook to vault."""
        self.validate_vault()
        target_dir = self.prepare_target(notebook.metadata.title)
        written_files = self.write_notebook(notebook, target_dir)
        return target_dir, written_files


def create_vault_structure(vault_path: Path) -> None:
    """Create basic Obsidian vault structure if it doesn't exist."""
    vault_path = Path(vault_path).expanduser().resolve()
    vault_path.mkdir(parents=True, exist_ok=True)
    
    # Create .obsidian folder with basic config
    obsidian_dir = vault_path / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    
    # Create minimal config files
    (obsidian_dir / "app.json").write_text('{}', encoding="utf-8")
    (obsidian_dir / "appearance.json").write_text('{}', encoding="utf-8")
    (obsidian_dir / "core-plugins.json").write_text('[]', encoding="utf-8")
    (obsidian_dir / "community-plugins.json").write_text('[]', encoding="utf-8")
    (obsidian_dir / "graph.json").write_text('{}', encoding="utf-8")
    (obsidian_dir / "hotkeys.json").write_text('{}', encoding="utf-8")
    (obsidian_dir / "workspace.json").write_text('{}', encoding="utf-8")