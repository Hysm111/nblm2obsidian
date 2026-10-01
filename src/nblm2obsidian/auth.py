"""Authentication handling for nblm2obsidian using notebooklm-py."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from notebooklm import NotebookLMClient


class AuthManager:
    """Manage NotebookLM authentication using notebooklm-py."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize auth manager.
        
        Args:
            config_dir: Custom config directory. Defaults to ~/.config/nblm2obsidian/
        """
        if config_dir is None:
            config_dir = Path.home() / ".config" / "nblm2obsidian"
        self.config_dir = Path(config_dir).expanduser().resolve()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.profile = "nblm2obsidian"
        self.storage_path = self.config_dir / "storage_state.json"
        self.browser_profile_path = self.config_dir / "browser_profile"
    
    def get_storage_path(self) -> Path:
        """Get the path to the storage state file."""
        return self.storage_path
    
    def is_authenticated(self) -> bool:
        """Check if there's a valid authentication session."""
        return self.storage_path.exists()
    
    def get_client(self, timeout: float = 30.0) -> NotebookLMClient:
        """Create an authenticated NotebookLM client.
        
        Args:
            timeout: HTTP request timeout in seconds.
            
        Returns:
            Authenticated NotebookLMClient instance.
            
        Raises:
            RuntimeError: If no authentication session exists.
        """
        if not self.is_authenticated():
            raise RuntimeError(
                "Not authenticated. Run 'nblm2obsidian login' first."
            )
        
        # Use notebooklm-py's from_storage with our storage path
        return NotebookLMClient.from_storage(
            path=str(self.storage_path),
            timeout=timeout,
        )
    
    def login(self, browser: str = "chromium", timeout: int = 300) -> bool:
        """Perform browser-based login and save session.
        
        Uses notebooklm-py's official login API which handles Playwright
        browser automation, Chromium installation, and session storage.
        
        Args:
            browser: Browser to use ('chromium', 'chrome', 'msedge')
            timeout: Seconds to wait for login completion.
            
        Returns:
            True if login succeeded, False otherwise.
        """
        try:
            from notebooklm.cli.playwright_login_io import (
                BrowserLoginPlan,
                run_login,
                prepare_paths_or_exit,
            )
        except ImportError as e:
            print(f"Failed to import notebooklm-py login API: {e}")
            return False
        
        # Validate browser choice
        valid_browsers = {"chromium", "chrome", "msedge"}
        if browser not in valid_browsers:
            raise ValueError(f"Unknown browser: {browser}. Use 'chromium', 'chrome', or 'msedge'")
        
        # Prepare paths (handles profile, storage, fresh flag)
        try:
            storage_path, browser_profile = prepare_paths_or_exit(
                profile=self.profile,
                storage=str(self.storage_path),
                fresh=False,
            )
        except Exception as e:
            print(f"Failed to prepare login paths: {e}")
            return False
        
        # Create login plan
        plan = BrowserLoginPlan(
            browser=browser,
            browser_profile=browser_profile,
            storage_path=storage_path,
            login_timeout_s=timeout,
        )
        
        try:
            run_login(plan)
            return True
        except SystemExit:
            # run_login may call sys.exit on failure
            return False
        except Exception as e:
            # Check if it's a Chromium/Playwright issue
            error_msg = str(e)
            if "playwright" in error_msg.lower() or "chromium" in error_msg.lower():
                print(f"Browser automation not available: {e}")
                print("On Termux/Android, you may need to install Playwright dependencies:")
                print("  pip install playwright && playwright install chromium")
            else:
                print(f"Login failed: {e}")
            return False
    
    def logout(self) -> bool:
        """Remove stored authentication."""
        try:
            if self.storage_path.exists():
                self.storage_path.unlink()
            # Also remove browser profile
            if self.browser_profile_path.exists():
                import shutil
                shutil.rmtree(self.browser_profile_path)
            return True
        except Exception as e:
            print(f"Logout failed: {e}")
            return False
    
    def import_storage_state(self, source_path: Path) -> bool:
        """Import an existing storage_state.json file.
        
        This allows using a session created on another machine (e.g., desktop with Playwright)
        by copying the storage_state.json file to this device.
        
        Args:
            source_path: Path to the storage_state.json file to import.
            
        Returns:
            True if import succeeded, False otherwise.
        """
        try:
            import shutil
            source_path = Path(source_path).expanduser().resolve()
            
            if not source_path.exists():
                print(f"Source file does not exist: {source_path}")
                return False
            
            if not source_path.is_file():
                print(f"Source path is not a file: {source_path}")
                return False
            
            # Validate the storage state file by trying to load it
            from notebooklm._auth.cookies import build_httpx_cookies_from_storage
            try:
                # This will validate the format and required cookies
                build_httpx_cookies_from_storage(source_path)
            except Exception as e:
                print(f"Invalid storage_state.json: {e}")
                return False
            
            # Copy to our storage location
            self.config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, self.storage_path)
            
            print(f"Successfully imported storage state from {source_path}")
            print(f"Session saved to: {self.storage_path}")
            return True
            
        except Exception as e:
            print(f"Failed to import storage state: {e}")
            return False
    
    def get_status(self) -> dict[str, Any]:
        """Get authentication status."""
        return {
            "authenticated": self.is_authenticated(),
            "storage_path": str(self.storage_path),
            "config_dir": str(self.config_dir),
            "profile": self.profile,
        }


async def test_authenticated_access(notebook_id: str, timeout: float = 30.0) -> dict[str, Any]:
    """Test if we can access a notebook with authenticated client."""
    auth_manager = AuthManager()
    
    if not auth_manager.is_authenticated():
        return {
            "success": False,
            "error": "Not authenticated. Run 'nblm2obsidian login' first.",
        }
    
    try:
        client = auth_manager.get_client(timeout=timeout)
        
        async with client as c:
            # Test basic access
            notebook = await c.notebooks.get(notebook_id)
            
            # Get sources
            sources = await c.sources.list(notebook_id)
            
            # Get notes
            notes = await c.notes.list(notebook_id)
            
            return {
                "success": True,
                "notebook": {
                    "id": notebook.id,
                    "title": notebook.title,
                    "sources_count": len(sources),
                    "notes_count": len(notes) if notes else 0,
                },
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def get_auth_manager(config_dir: Optional[Path] = None) -> AuthManager:
    """Get the global auth manager instance."""
    return AuthManager(config_dir)