"""Tests for CLI module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from click.testing import CliRunner
from pathlib import Path

from nblm2obsidian.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestCLI:
    def test_import_invalid_url(self, runner):
        result = runner.invoke(cli, ["import", "https://example.com/notebook/123", "--output", "/tmp/out"])
        assert result.exit_code != 0
        assert "Invalid NotebookLM share URL" in result.output
    
    def test_import_no_target(self, runner):
        result = runner.invoke(cli, ["import", "https://notebooklm.google.com/notebook/abc123"])
        assert result.exit_code != 0
        assert "Either --vault or --output must be specified" in result.output
    
    def test_import_both_targets(self, runner):
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["import", "https://notebooklm.google.com/notebook/abc123", "--vault", ".", "--output", "."])
            assert result.exit_code != 0
            assert "Cannot specify both --vault and --output" in result.output
    
    @patch("nblm2obsidian.cli.import_notebook")
    def test_import_success(self, mock_import, runner):
        with runner.isolated_filesystem():
            # Create a fake vault
            vault = Path("vault")
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / ".obsidian" / "app.json").write_text("{}")
            
            mock_result = MagicMock()
            mock_result.notebook.metadata.id = "abc123"
            mock_result.notebook.metadata.title = "Test Notebook"
            mock_result.target_dir = vault / "Test_Notebook"
            mock_result.written_files = []
            mock_result.warnings = []
            
            # Return the result directly (the function is async but Click handles it)
            async def mock_import_func(*args, **kwargs):
                return mock_result
            mock_import.side_effect = mock_import_func
            
            result = runner.invoke(cli, ["import", "https://notebooklm.google.com/notebook/abc123", "--vault", "vault"])
            
            assert result.exit_code == 0
            assert "Imported" in result.output
    
    def test_inspect_invalid_url(self, runner):
        result = runner.invoke(cli, ["inspect", "https://example.com/notebook/123"])
        assert result.exit_code != 0
        assert "Invalid NotebookLM share URL" in result.output
    
    @patch("nblm2obsidian.cli.inspect_notebook_public")
    def test_inspect_accessible(self, mock_inspect, runner):
        # Return the dict directly via an async function
        async def mock_inspect_func(*args, **kwargs):
            return {
                "notebook_id": "abc123",
                "is_publicly_accessible": True,
                "title": "Test Notebook",
                "source_count": 2,
                "notes_count": 1,
                "artifacts_count": 0,
                "source_ids": ["src1", "src2"],
            }
        mock_inspect.side_effect = mock_inspect_func
        
        result = runner.invoke(cli, ["inspect", "https://notebooklm.google.com/notebook/abc123"])
        
        assert result.exit_code == 0
        assert "Publicly Accessible" in result.output
        assert "Test Notebook" in result.output
    
    @patch("nblm2obsidian.cli.inspect_notebook_public")
    def test_inspect_not_accessible(self, mock_inspect, runner):
        async def mock_inspect_func(*args, **kwargs):
            return {
                "notebook_id": "abc123",
                "is_publicly_accessible": False,
                "error": "Notebook is private",
            }
        mock_inspect.side_effect = mock_inspect_func
        
        result = runner.invoke(cli, ["inspect", "https://notebooklm.google.com/notebook/abc123"])
        
        assert result.exit_code == 0
        assert "Not Publicly Accessible" in result.output
    
    def test_sources_invalid_url(self, runner):
        result = runner.invoke(cli, ["sources", "https://example.com/notebook/123"])
        assert result.exit_code != 0
        assert "Invalid NotebookLM share URL" in result.output
    
    @patch("nblm2obsidian.cli.get_notebook_sources")
    def test_sources_success(self, mock_sources, runner):
        async def mock_sources_func(*args, **kwargs):
            return [
                {"id": "src1", "title": "Source One", "type": "url", "url": "https://example.com", "has_content": True, "has_summary": True},
                {"id": "src2", "title": "Source Two", "type": "pdf", "url": None, "has_content": True, "has_summary": False},
            ]
        mock_sources.side_effect = mock_sources_func
        
        result = runner.invoke(cli, ["sources", "https://notebooklm.google.com/notebook/abc123"])
        
        assert result.exit_code == 0
        assert "Source One" in result.output
        assert "Source Two" in result.output
    
    def test_export_alias(self, runner):
        # export is an alias for import, so test that it exists
        result = runner.invoke(cli, ["export", "--help"])
        assert result.exit_code == 0
        assert "Export a public NotebookLM notebook" in result.output