"""Tests for obsidian module."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from nblm2obsidian.models import Notebook, NotebookMetadata, Source, Note, SourceType, NoteType
from nblm2obsidian.obsidian import VaultWriter, create_vault_structure
from nblm2obsidian.errors import VaultError


@pytest.fixture
def temp_vault():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test_vault"
        vault_path.mkdir()
        # Create minimal .obsidian structure
        (vault_path / ".obsidian").mkdir()
        (vault_path / ".obsidian" / "app.json").write_text("{}")
        yield vault_path


@pytest.fixture
def sample_notebook():
    meta = NotebookMetadata(
        id="nb123",
        title="Test Notebook",
        share_url="https://notebooklm.google.com/notebook/nb123",
        is_public=True,
    )
    sources = [
        Source(id="src1", notebook_id="nb123", title="Source One", source_type=SourceType.URL, index=0),
    ]
    notes = [
        Note(id="note1", notebook_id="nb123", title="Test Note", note_type=NoteType.SUMMARY, content="Content"),
    ]
    return Notebook(metadata=meta, sources=sources, notes=notes)


class TestVaultWriter:
    def test_validate_vault_success(self, temp_vault):
        writer = VaultWriter(temp_vault)
        writer.validate_vault()  # Should not raise
    
    def test_validate_vault_not_exists(self):
        writer = VaultWriter(Path("/nonexistent/vault"))
        with pytest.raises(VaultError, match="does not exist"):
            writer.validate_vault()
    
    def test_validate_vault_not_dir(self, temp_vault):
        file_path = temp_vault / "not_a_dir.txt"
        file_path.write_text("test")
        writer = VaultWriter(file_path)
        with pytest.raises(VaultError, match="not a directory"):
            writer.validate_vault()
    
    def test_prepare_target_new(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault)
        target = writer.prepare_target("Test Notebook")
        
        assert target.name == "Test_Notebook"
        assert target.parent == temp_vault
        assert target.exists()
        assert (target / "Sources").exists()
        assert (target / "Notes").exists()
        assert (target / "Assets").exists()
    
    def test_prepare_target_with_folder(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault, folder="MyFolder")
        target = writer.prepare_target("Test Notebook")
        
        assert target == temp_vault / "MyFolder"
    
    def test_prepare_target_exists_no_force(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault, force=False)
        target = writer.prepare_target("Test Notebook")  # Creates dir
        
        # Try again without force
        writer2 = VaultWriter(temp_vault, force=False)
        with pytest.raises(VaultError, match="already exists"):
            writer2.prepare_target("Test Notebook")
    
    def test_prepare_target_exists_with_force(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault, force=True)
        target = writer.prepare_target("Test Notebook")
        target.joinpath("test.txt").write_text("test")
        
        # Force should remove and recreate
        writer2 = VaultWriter(temp_vault, force=True)
        target2 = writer2.prepare_target("Test Notebook")
        
        assert not target2.joinpath("test.txt").exists()
    
    def test_prepare_target_dry_run(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault, dry_run=True)
        target = writer.prepare_target("Test Notebook")
        
        # In dry run, directories shouldn't be created
        assert not target.exists()
    
    def test_write_notebook(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault)
        target = writer.prepare_target("Test Notebook")
        written = writer.write_notebook(sample_notebook, target)
        
        assert len(written) == 3  # Notebook.md + 1 source + 1 note
        assert (target / "Notebook.md").exists()
        assert (target / "Sources" / "01 - Source_One.md").exists()
        assert (target / "Notes" / "Test_Note.md").exists()
    
    def test_write_notebook_dry_run(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault, dry_run=True)
        target = writer.prepare_target("Test Notebook")
        written = writer.write_notebook(sample_notebook, target)
        
        assert len(written) == 3
        # Files shouldn't actually exist in dry run
        assert not (target / "Notebook.md").exists()
    
    def test_write_full(self, temp_vault, sample_notebook):
        writer = VaultWriter(temp_vault)
        target_dir, written_files = writer.write(sample_notebook)
        
        assert target_dir.name == "Test_Notebook"
        assert len(written_files) == 3
        assert (target_dir / "Notebook.md").exists()


class TestCreateVaultStructure:
    def test_create_new_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "new_vault"
            create_vault_structure(vault_path)
            
            assert vault_path.exists()
            assert (vault_path / ".obsidian").exists()
            assert (vault_path / ".obsidian" / "app.json").exists()
            assert (vault_path / ".obsidian" / "appearance.json").exists()
            assert (vault_path / ".obsidian" / "core-plugins.json").exists()
            assert (vault_path / ".obsidian" / "community-plugins.json").exists()
            assert (vault_path / ".obsidian" / "graph.json").exists()
            assert (vault_path / ".obsidian" / "hotkeys.json").exists()
            assert (vault_path / ".obsidian" / "workspace.json").exists()
    
    def test_create_existing_vault(self, temp_vault):
        # Should not raise
        create_vault_structure(temp_vault)
        assert (temp_vault / ".obsidian" / "app.json").exists()