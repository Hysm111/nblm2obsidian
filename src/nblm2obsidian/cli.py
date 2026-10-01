"""Command-line interface for nblm2obsidian."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .notebooklm import import_notebook, inspect_notebook_public, get_notebook_sources, export_to_markdown
from .models import parse_notebook_url
from .errors import (
    Nblm2ObsidianError,
    InvalidURLError,
    NotebookNotAccessibleError,
    NotebookNotFoundError,
    VaultError,
)
from .auth import get_auth_manager
from .extractor_auth import (
    AuthenticatedNotebookExtractor,
    inspect_notebook_authenticated,
    list_sources_authenticated,
)

console = Console()


def print_error(msg: str, exit_code: int = 1):
    """Print error message and exit."""
    console.print(f"[red]Error:[/red] {msg}")
    sys.exit(exit_code)


def print_warning(msg: str):
    """Print warning message."""
    console.print(f"[yellow]Warning:[/yellow] {msg}")


def print_success(msg: str):
    """Print success message."""
    console.print(f"[green]Success:[/green] {msg}")


def print_info(msg: str):
    """Print info message."""
    console.print(f"[blue]Info:[/blue] {msg}")


@click.group()
@click.version_option(version="0.1.0", prog_name="nblm2obsidian")
def cli():
    """nblm2obsidian - Import Google NotebookLM notebooks into Obsidian vaults.

    This tool extracts content from NotebookLM notebooks (public or authenticated)
    and converts them to Obsidian-compatible Markdown files.
    """
    pass


# ===== Authentication Commands =====

@cli.command()
@click.option(
    "--browser",
    type=click.Choice(["chromium", "chrome", "msedge"], case_sensitive=False),
    default="chromium",
    help="Browser to use for login (default: chromium)",
)
@click.option(
    "--timeout",
    type=click.IntRange(min=30),
    default=300,
    help="Seconds to wait for login completion (default: 300)",
)
@click.option(
    "--storage-state",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="Path to an existing storage_state.json file to import (created on another device with Playwright)",
)
@click.option("--verbose", is_flag=True, help="Verbose output")
def login(browser: str, timeout: int, storage_state: Optional[Path], verbose: bool):
    """Log in to NotebookLM and save session for authenticated access.

    Two modes:
    
    1. Browser login (requires Playwright/Chromium):
       nblm2obsidian login
       Opens a browser window for Google login. Requires Playwright/Chromium.
    
    2. Import existing session (works on Termux/Android):
       nblm2obsidian login --storage-state /path/to/storage_state.json
       Imports a storage_state.json file created on another device (e.g., desktop
       with Playwright/Chromium). No browser automation needed.
    """
    auth_manager = get_auth_manager()
    
    if auth_manager.is_authenticated():
        print_warning("Already authenticated. Use 'nblm2obsidian logout' first to switch accounts.")
        return
    
    if storage_state:
        # Import existing storage state
        if verbose:
            print_info(f"Importing storage state from {storage_state}...")
        
        success = auth_manager.import_storage_state(storage_state)
        
        if success:
            print_success("Storage state imported successfully! Session saved.")
            status = auth_manager.get_status()
            print_info(f"Session stored at: {status['storage_path']}")
        else:
            print_error("Failed to import storage state. Please verify the file is a valid storage_state.json.")
    else:
        # Browser-based login
        def run_login():
            if verbose:
                print_info(f"Starting browser login with {browser}...")
            
            success = auth_manager.login(browser=browser, timeout=timeout)
            
            if success:
                print_success("Login successful! Session saved.")
                status = auth_manager.get_status()
                print_info(f"Session stored at: {status['storage_path']}")
            else:
                print_error("Login failed. Please try again.")
        
        run_login()


@cli.command()
@click.option("--verbose", is_flag=True, help="Verbose output")
def logout(verbose: bool):
    """Log out and remove saved NotebookLM session."""
    auth_manager = get_auth_manager()
    
    if not auth_manager.is_authenticated():
        print_info("Not currently authenticated.")
        return
    
    if auth_manager.logout():
        print_success("Logged out successfully. Session removed.")
    else:
        print_error("Logout failed.")


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--verbose", is_flag=True, help="Verbose output")
def status(json_output: bool, verbose: bool):
    """Show authentication status."""
    auth_manager = get_auth_manager()
    status_info = auth_manager.get_status()
    
    if json_output:
        console.print_json(json.dumps(status_info))
        return
    
    if status_info["authenticated"]:
        print_success("Authenticated")
        print_info(f"Session: {status_info['storage_path']}")
        print_info(f"Config dir: {status_info['config_dir']}")
    else:
        print_warning("Not authenticated")
        print_info("Run 'nblm2obsidian login' to authenticate.")


# ===== Notebook Commands =====

@cli.command()
@click.argument("url")
@click.option("--vault", "-v", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
              help="Path to Obsidian vault")
@click.option("--output", "-o", type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
              help="Output directory (alternative to --vault)")
@click.option("--folder", "-f", type=str, help="Subfolder name in vault/output")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--dry-run", is_flag=True, help="Show what would be done without writing")
@click.option("--json", "json_output", is_flag=True, help="Output result as JSON")
@click.option("--verbose", is_flag=True, help="Verbose output")
def import_cmd(
    url: str,
    vault: Optional[Path],
    output: Optional[Path],
    folder: Optional[str],
    force: bool,
    dry_run: bool,
    json_output: bool,
    verbose: bool,
):
    """Import a NotebookLM notebook into an Obsidian vault or directory.

    Uses authenticated access if logged in, otherwise tries public access.
    """
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        print_error(f"Invalid NotebookLM share URL: {url}")
    
    if not vault and not output:
        print_error("Either --vault or --output must be specified")
    if vault and output:
        print_error("Cannot specify both --vault and --output")
    
    target = vault or output
    is_vault = vault is not None
    
    auth_manager = get_auth_manager()
    use_auth = auth_manager.is_authenticated()
    
    async def run_import():
        if verbose:
            print_info(f"Importing notebook {notebook_id} from {url}")
            print_info(f"Target: {target} ({'vault' if is_vault else 'directory'})")
            print_info(f"Mode: {'authenticated' if use_auth else 'public'}")
        
        try:
            if use_auth:
                # Use authenticated extractor
                async with AuthenticatedNotebookExtractor(verbose=verbose) as extractor:
                    extract_result = await extractor.extract_from_url(url)
                notebook = extract_result.notebook
                warnings = extract_result.warnings
            else:
                # Use public extractor
                from .extractor import PublicNotebookExtractor
                async with PublicNotebookExtractor(verbose=verbose) as extractor:
                    extract_result = await extractor.extract_from_url(url)
                notebook = extract_result.notebook
                warnings = extract_result.warnings
            
            if is_vault:
                from .obsidian import VaultWriter
                writer = VaultWriter(target, folder=folder, force=force, dry_run=dry_run)
                target_dir, written_files = writer.write(notebook)
                from .notebooklm import ImportResult
                result = ImportResult(
                    notebook=notebook,
                    target_dir=target_dir,
                    written_files=written_files,
                    warnings=warnings,
                )
            else:
                from .notebooklm import export_to_markdown
                written_files = export_to_markdown(
                    notebook=notebook,
                    output_dir=target / (folder or notebook.metadata.title),
                    force=force,
                    dry_run=dry_run,
                )
                from .notebooklm import ImportResult
                result = ImportResult(
                    notebook=notebook,
                    target_dir=target / (folder or notebook.metadata.title),
                    written_files=written_files,
                    warnings=warnings,
                )
            
            if json_output:
                output_data = {
                    "notebook_id": result.notebook.metadata.id,
                    "title": result.notebook.metadata.title,
                    "target_dir": str(result.target_dir),
                    "files_written": len(result.written_files),
                    "warnings": result.warnings,
                    "dry_run": dry_run,
                    "mode": "authenticated" if use_auth else "public",
                }
                console.print_json(json.dumps(output_data))
                return
            
            if dry_run:
                print_info("DRY RUN - No files were written")
            
            print_success(f"Imported '{result.notebook.metadata.title}' to {result.target_dir}")
            console.print(f"Files written: {len(result.written_files)}")
            
            if result.warnings:
                for w in result.warnings:
                    print_warning(w)
            
            if not json_output and not dry_run:
                console.print("\n[bold]Structure:[/bold]")
                console.print(f"  {result.target_dir.name}/")
                console.print(f"  ├── Notebook.md")
                console.print(f"  ├── Sources/ ({len(result.notebook.sources)} files)")
                console.print(f"  ├── Notes/ ({len(result.notebook.notes)} files)")
                console.print(f"  └── Assets/")
        
        except NotebookNotAccessibleError as e:
            print_error(f"Notebook not accessible: {e}")
        except NotebookNotFoundError as e:
            print_error(f"Notebook not found: {e}")
        except VaultError as e:
            print_error(f"Vault error: {e}")
        except Nblm2ObsidianError as e:
            print_error(str(e))
        except Exception as e:
            if verbose:
                import traceback
                traceback.print_exc()
            print_error(f"Unexpected error: {e}")
    
    asyncio.run(run_import())


@cli.command()
@click.argument("url")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--verbose", is_flag=True, help="Verbose output")
def inspect(url: str, json_output: bool, verbose: bool):
    """Inspect a NotebookLM notebook to see what's accessible.

    Uses authenticated access if logged in, otherwise tries public access.
    """
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        print_error(f"Invalid NotebookLM share URL: {url}")
    
    auth_manager = get_auth_manager()
    use_auth = auth_manager.is_authenticated()
    
    async def run_inspect():
        if verbose:
            print_info(f"Inspecting notebook {notebook_id}...")
            print_info(f"Mode: {'authenticated' if use_auth else 'public'}")
        
        try:
            if use_auth:
                result = await inspect_notebook_authenticated(url, verbose=verbose)
            else:
                result = await inspect_notebook_public(url, verbose=verbose)
            
            if json_output:
                console.print_json(json.dumps(result))
                return
            
            # Display results
            is_accessible = result.get("is_publicly_accessible", False) or result.get("is_authenticated", False)
            
            if is_accessible:
                mode = "authenticated" if result.get("is_authenticated") else "public"
                console.print(Panel.fit(
                    f"[green]✓ Accessible ({mode})[/green]\n"
                    f"Title: {result.get('title', 'Unknown')}\n"
                    f"Sources: {result.get('source_count', 0)}\n"
                    f"Notes: {result.get('notes_count', 0)}\n"
                    f"Artifacts: {result.get('artifacts_count', 0)}",
                    title=f"Notebook: {notebook_id}",
                    border_style="green",
                ))
                
                if result.get("source_ids"):
                    console.print("\n[bold]Source IDs:[/bold]")
                    for sid in result["source_ids"]:
                        console.print(f"  - {sid}")
            else:
                error_msg = result.get('error', 'Unknown reason')
                console.print(Panel.fit(
                    f"[red]✗ Not Accessible[/red]\n"
                    f"{error_msg}",
                    title=f"Notebook: {notebook_id}",
                    border_style="red",
                ))
                
                if result.get("share_status"):
                    console.print("\n[bold]Share Status:[/bold]")
                    console.print_json(json.dumps(result["share_status"]))
        
        except InvalidURLError as e:
            print_error(str(e))
        except Exception as e:
            if verbose:
                import traceback
                traceback.print_exc()
            print_error(f"Inspection failed: {e}")
    
    asyncio.run(run_inspect())


@cli.command()
@click.argument("url")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--verbose", is_flag=True, help="Verbose output")
def sources(url: str, json_output: bool, verbose: bool):
    """List all sources in a NotebookLM notebook.

    Uses authenticated access if logged in, otherwise tries public access.
    """
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        print_error(f"Invalid NotebookLM share URL: {url}")
    
    auth_manager = get_auth_manager()
    use_auth = auth_manager.is_authenticated()
    
    async def run_sources():
        if verbose:
            print_info(f"Fetching sources for notebook {notebook_id}...")
            print_info(f"Mode: {'authenticated' if use_auth else 'public'}")
        
        try:
            if use_auth:
                source_list = await list_sources_authenticated(url, verbose=verbose)
            else:
                source_list = await get_notebook_sources(url, verbose=verbose)
            
            if json_output:
                console.print_json(json.dumps(source_list))
                return
            
            if not source_list:
                print_info("No sources found or accessible")
                return
            
            table = Table(title=f"Sources in Notebook {notebook_id}")
            table.add_column("#", style="cyan")
            table.add_column("Title", style="white")
            table.add_column("Type", style="green")
            table.add_column("URL", style="blue")
            table.add_column("Content", style="yellow")
            table.add_column("Summary", style="magenta")
            
            for i, src in enumerate(source_list):
                table.add_row(
                    str(i + 1),
                    src["title"][:60] + "..." if len(src["title"]) > 60 else src["title"],
                    src["type"],
                    "✓" if src["url"] else "✗",
                    "✓" if src["has_content"] else "✗",
                    "✓" if src["has_summary"] else "✗",
                )
            
            console.print(table)
            
            if verbose:
                for src in source_list:
                    if src.get("summary_preview"):
                        console.print(f"\n[dim]{src['title']}:[/dim] {src['summary_preview']}")
        
        except NotebookNotAccessibleError as e:
            print_error(f"Notebook not accessible: {e}")
        except NotebookNotFoundError as e:
            print_error(f"Notebook not found: {e}")
        except Exception as e:
            if verbose:
                import traceback
                traceback.print_exc()
            print_error(f"Failed to list sources: {e}")
    
    asyncio.run(run_sources())


@cli.command()
@click.argument("url")
@click.option("--vault", "-v", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
              help="Path to Obsidian vault")
@click.option("--output", "-o", type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
              help="Output directory (alternative to --vault)")
@click.option("--folder", "-f", type=str, help="Subfolder name in vault/output")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--dry-run", is_flag=True, help="Show what would be done without writing")
@click.option("--json", "json_output", is_flag=True, help="Output result as JSON")
@click.option("--verbose", is_flag=True, help="Verbose output")
def export(
    url: str,
    vault: Optional[Path],
    output: Optional[Path],
    folder: Optional[str],
    force: bool,
    dry_run: bool,
    json_output: bool,
    verbose: bool,
):
    """Export a NotebookLM notebook to Markdown files (alias for import)."""
    ctx = click.get_current_context()
    ctx.invoke(import_cmd, url=url, vault=vault, output=output, folder=folder,
               force=force, dry_run=dry_run, json_output=json_output, verbose=verbose)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()