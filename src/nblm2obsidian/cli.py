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
    """nblm2obsidian - Import publicly shared Google NotebookLM notebooks into Obsidian vaults.

    This tool extracts content from publicly shared NotebookLM notebooks
    and converts them to Obsidian-compatible Markdown files.
    """
    pass


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
    """Import a public NotebookLM notebook into an Obsidian vault or directory."""
    
    # Validate URL
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        print_error(f"Invalid NotebookLM share URL: {url}")
    
    # Validate output target
    if not vault and not output:
        print_error("Either --vault or --output must be specified")
    if vault and output:
        print_error("Cannot specify both --vault and --output")
    
    target = vault or output
    is_vault = vault is not None
    
    async def run_import():
        if verbose:
            print_info(f"Importing notebook {notebook_id} from {url}")
            print_info(f"Target: {target} ({'vault' if is_vault else 'directory'})")
        
        try:
            if is_vault:
                result = await import_notebook(
                    url=url,
                    vault_path=target,
                    folder=folder,
                    force=force,
                    dry_run=dry_run,
                    verbose=verbose,
                )
            else:
                # Use export_to_markdown for non-vault output
                async with __import__('nblm2obsidian.extractor', fromlist=['PublicNotebookExtractor']).PublicNotebookExtractor(verbose=verbose) as extractor:
                    extract_result = await extractor.extract_from_url(url)
                notebook = extract_result.notebook
                warnings = extract_result.warnings
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
            
            # Show structure
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
    """Inspect a public NotebookLM notebook to see what's accessible without downloading."""
    
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        print_error(f"Invalid NotebookLM share URL: {url}")
    
    async def run_inspect():
        if verbose:
            print_info(f"Inspecting notebook {notebook_id}...")
        
        try:
            result = await inspect_notebook_public(url, verbose=verbose)
            
            if json_output:
                console.print_json(json.dumps(result))
                return
            
            # Display results
            accessible = result.get("is_publicly_accessible", False)
            
            if accessible:
                console.print(Panel.fit(
                    f"[green]✓ Publicly Accessible[/green]\n"
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
                console.print(Panel.fit(
                    f"[red]✗ Not Publicly Accessible[/red]\n"
                    f"{result.get('error', 'Unknown reason')}",
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
    """List all sources in a public NotebookLM notebook."""
    
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        print_error(f"Invalid NotebookLM share URL: {url}")
    
    async def run_sources():
        if verbose:
            print_info(f"Fetching sources for notebook {notebook_id}...")
        
        try:
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
    """Export a public NotebookLM notebook to Markdown files (alias for import)."""
    # Reuse import logic
    ctx = click.get_current_context()
    ctx.invoke(import_cmd, url=url, vault=vault, output=output, folder=folder,
               force=force, dry_run=dry_run, json_output=json_output, verbose=verbose)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()