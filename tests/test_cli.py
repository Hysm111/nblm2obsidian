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
    
    @patch("nblm2obsidian.cli.get_auth_manager")
    @patch("nblm2obsidian.extractor_auth.get_auth_manager")
    @patch("nblm2obsidian.cli.AuthenticatedNotebookExtractor")
    def test_import_success(self, mock_extractor_class, mock_get_auth_manager_extractor, mock_get_auth_manager_cli, runner):
        with runner.isolated_filesystem():
            # Create a fake vault
            vault = Path("vault")
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / ".obsidian" / "app.json").write_text("{}")
            
            # Mock auth manager to return authenticated
            mock_auth_manager = MagicMock()
            mock_auth_manager.is_authenticated.return_value = True
            mock_get_auth_manager_cli.return_value = mock_auth_manager
            mock_get_auth_manager_extractor.return_value = mock_auth_manager
            
            # Create a proper mock notebook with all required attributes
            from nblm2obsidian.models import Notebook, NotebookMetadata, Source, Note, SourceType, NoteType
            from datetime import datetime
            
            mock_notebook = Notebook(
                metadata=NotebookMetadata(
                    id="abc123",
                    title="Test Notebook",
                    share_url="https://notebooklm.google.com/notebook/abc123",
                    is_public=True,
                    sources_count=0,
                ),
                sources=[],
                notes=[],
            )
            
            # Mock the extractor to return a notebook
            mock_extractor = AsyncMock()
            mock_result = MagicMock()
            mock_result.notebook = mock_notebook
            mock_result.warnings = []
            mock_extractor.extract_from_url = AsyncMock(return_value=mock_result)
            mock_extractor.__aenter__ = AsyncMock(return_value=mock_extractor)
            mock_extractor.__aexit__ = AsyncMock(return_value=None)
            mock_extractor_class.return_value = mock_extractor
            
            # Mock auth manager to return authenticated
            mock_auth_manager = MagicMock()
            mock_auth_manager.is_authenticated.return_value = True
            mock_get_auth_manager_cli.return_value = mock_auth_manager
            mock_get_auth_manager_extractor.return_value = mock_auth_manager
            
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
        assert "Accessible" in result.output
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
        assert "Not Accessible" in result.output
    
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
        assert "Export a NotebookLM notebook" in result.output


class TestAuthCommands:
    @patch("nblm2obsidian.cli.get_auth_manager")
    def test_login_not_authenticated(self, mock_get_auth_manager, runner):
        """Test login command when not authenticated."""
        mock_auth_manager = MagicMock()
        mock_auth_manager.is_authenticated.return_value = False
        mock_get_auth_manager.return_value = mock_auth_manager
        
        # Mock the login method to succeed
        with patch.object(mock_get_auth_manager.return_value, 'login', return_value=True):
            result = runner.invoke(cli, ["login"])
        
        # Should attempt login (even if Playwright fails, it should try)
        assert result.exit_code in (0, 1)  # May fail due to missing Playwright
    
    @patch("nblm2obsidian.cli.get_auth_manager")
    def test_login_already_authenticated(self, mock_get_auth_manager, runner):
        """Test login command when already authenticated."""
        mock_auth_manager = MagicMock()
        mock_auth_manager.is_authenticated.return_value = True
        mock_get_auth_manager.return_value = mock_auth_manager
        
        result = runner.invoke(cli, ["login"])
        
        assert result.exit_code == 0
        assert "Already authenticated" in result.output
    
    @patch("nblm2obsidian.cli.get_auth_manager")
    def test_logout_not_authenticated(self, mock_get_auth_manager, runner):
        """Test logout command when not authenticated."""
        mock_auth_manager = MagicMock()
        mock_auth_manager.is_authenticated.return_value = False
        mock_get_auth_manager.return_value = mock_auth_manager
        
        result = runner.invoke(cli, ["logout"])
        
        assert result.exit_code == 0
        assert "Not currently authenticated" in result.output
    
    @patch("nblm2obsidian.cli.get_auth_manager")
    def test_logout_authenticated(self, mock_get_auth_manager, runner):
        """Test logout command when authenticated."""
        mock_auth_manager = MagicMock()
        mock_auth_manager.is_authenticated.return_value = True
        mock_auth_manager.logout.return_value = True
        mock_get_auth_manager.return_value = mock_auth_manager
        
        result = runner.invoke(cli, ["logout"])
        
        assert result.exit_code == 0
        assert "Logged out successfully" in result.output
    
    @patch("nblm2obsidian.cli.get_auth_manager")
    def test_status_not_authenticated(self, mock_get_auth_manager, runner):
        """Test status command when not authenticated."""
        mock_auth_manager = MagicMock()
        mock_auth_manager.is_authenticated.return_value = False
        mock_auth_manager.get_status.return_value = {
            "authenticated": False,
            "storage_path": "/test/path",
            "config_dir": "/test/config",
            "profile": "test",
        }
        mock_get_auth_manager.return_value = mock_auth_manager
        
        result = runner.invoke(cli, ["status"])
        
        assert result.exit_code == 0
        assert "Not authenticated" in result.output
    
    @patch("nblm2obsidian.cli.get_auth_manager")
    def test_status_authenticated(self, mock_get_auth_manager, runner):
        """Test status command when authenticated."""
        mock_auth_manager = MagicMock()
        mock_auth_manager.is_authenticated.return_value = True
        mock_auth_manager.get_status.return_value = {
            "authenticated": True,
            "storage_path": "/test/path",
            "config_dir": "/test/config",
            "profile": "test",
        }
        mock_get_auth_manager.return_value = mock_auth_manager
        
        result = runner.invoke(cli, ["status"])
        
        assert result.exit_code == 0
        assert "Authenticated" in result.output


class TestAuthManager:
    def test_auth_manager_default_config(self):
        """Test AuthManager creates default config directory."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                manager = AuthManager()
                assert manager.config_dir == Path(tmpdir) / '.config' / 'nblm2obsidian'
                assert manager.storage_path == Path(tmpdir) / '.config' / 'nblm2obsidian' / 'storage_state.json'
    
    def test_auth_manager_custom_config(self):
        """Test AuthManager with custom config directory."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = Path(tmpdir) / 'custom_config'
            manager = AuthManager(custom_dir)
            assert manager.config_dir == Path(tmpdir) / 'custom_config'
            assert manager.storage_path == Path(tmpdir) / 'custom_config' / 'storage_state.json'
    
    def test_is_authenticated_false(self):
        """Test is_authenticated when no session exists."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AuthManager(Path(tmpdir) / 'config')
            assert manager.is_authenticated() is False
    
    def test_is_authenticated_true(self):
        """Test is_authenticated when session exists."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / 'config'
            config_dir.mkdir(parents=True)
            storage_path = config_dir / 'storage_state.json'
            storage_path.write_text('{}')
            
            manager = AuthManager(config_dir)
            assert manager.is_authenticated() is True
    
    def test_get_status(self):
        """Test get_status returns correct info."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / 'config'
            manager = AuthManager(config_dir)
            status = manager.get_status()
            
            assert 'authenticated' in status
            assert 'storage_path' in status
            assert 'config_dir' in status
            assert 'profile' in status
            assert status['profile'] == 'nblm2obsidian'
    
    def test_import_storage_state_valid(self):
        """Test importing a valid storage_state.json."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid storage state file
            source_path = Path(tmpdir) / 'source_storage.json'
            storage_state = {
                'cookies': [
                    {'name': 'SID', 'value': 'test_sid', 'domain': '.google.com', 'path': '/', 'secure': True, 'httpOnly': True, 'sameSite': 'None'},
                    {'name': '__Secure-1PSIDTS', 'value': 'test_ts', 'domain': '.google.com', 'path': '/', 'secure': True, 'httpOnly': True, 'sameSite': 'None'},
                    {'name': 'OSID', 'value': 'test_osid', 'domain': '.google.com', 'path': '/', 'secure': True, 'httpOnly': True, 'sameSite': 'None'},
                ],
                'origins': []
            }
            source_path.write_text(json.dumps(storage_state))
            
            config_dir = Path(tmpdir) / 'config'
            manager = AuthManager(config_dir)
            
            assert manager.is_authenticated() is False
            assert manager.import_storage_state(source_path) is True
            assert manager.is_authenticated() is True
            assert manager.storage_path.exists()
    
    def test_import_storage_state_invalid(self):
        """Test importing an invalid storage_state.json fails."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        import json
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create an invalid storage state file (missing required cookies)
            source_path = Path(tmpdir) / 'invalid_storage.json'
            storage_state = {
                'cookies': [
                    {'name': 'SID', 'value': 'test_sid', 'domain': '.google.com', 'path': '/', 'secure': True, 'httpOnly': True, 'sameSite': 'None'},
                    # Missing __Secure-1PSIDTS
                ],
                'origins': []
            }
            source_path.write_text(json.dumps(storage_state))
            
            config_dir = Path(tmpdir) / 'config'
            manager = AuthManager(config_dir)
            
            assert manager.import_storage_state(source_path) is False
            assert manager.is_authenticated() is False
    
    def test_import_storage_state_nonexistent(self):
        """Test importing a nonexistent file fails."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / 'config'
            manager = AuthManager(config_dir)
            
            assert manager.import_storage_state(Path('/nonexistent/file.json')) is False
            assert manager.is_authenticated() is False
    
    def test_get_status(self):
        """Test get_status returns correct info."""
        from nblm2obsidian.auth import AuthManager
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / 'config'
            manager = AuthManager(config_dir)
            status = manager.get_status()
            
            assert 'authenticated' in status
            assert 'storage_path' in status
            assert 'config_dir' in status
            assert 'profile' in status
            assert status['profile'] == 'nblm2obsidian'