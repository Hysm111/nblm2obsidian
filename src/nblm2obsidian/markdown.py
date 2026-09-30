"""Markdown generation for Obsidian-compatible output."""

from __future__ import annotations

import yaml
from datetime import datetime
from typing import Any

from .models import Notebook, Source, Note, NotebookMetadata, sanitize_filename


def generate_frontmatter(data: dict[str, Any]) -> str:
    """Generate YAML frontmatter string."""
    # Remove None values
    cleaned = {k: v for k, v in data.items() if v is not None}
    yaml_str = yaml.dump(cleaned, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{yaml_str}---\n"


def generate_notebook_markdown(notebook: Notebook) -> str:
    """Generate the main notebook index markdown file."""
    fm = generate_frontmatter(notebook.to_frontmatter())
    
    lines = [
        fm,
        f"# {notebook.metadata.title}",
        "",
    ]
    
    if notebook.metadata.description:
        lines.extend([
            notebook.metadata.description,
            "",
        ])
    
    lines.extend([
        "## Metadata",
        "",
        f"- **Notebook ID**: `{notebook.metadata.id}`",
        f"- **Share URL**: {notebook.metadata.share_url or 'N/A'}",
        f"- **Public**: {'Yes' if notebook.metadata.is_public else 'No'}",
        f"- **View Level**: {notebook.metadata.view_level}",
        f"- **Sources**: {len(notebook.sources)}",
        f"- **Notes/Artifacts**: {len(notebook.notes)}",
        f"- **Imported**: {notebook.metadata.imported_at.isoformat()}",
        "",
    ])
    
    if notebook.metadata.created_at:
        lines.append(f"- **Created**: {notebook.metadata.created_at.isoformat()}")
    if notebook.metadata.updated_at:
        lines.append(f"- **Updated**: {notebook.metadata.updated_at.isoformat()}")
    
    lines.append("")
    
    # Sources section
    if notebook.sources:
        lines.extend([
            "## Sources",
            "",
            "| # | Title | Type | URL | Content | Summary |",
            "|---|-------|------|-----|---------|---------|",
        ])
        for src in notebook.sources:
            url_display = f"[Link]({src.url})" if src.url else "—"
            content_display = "✓" if src.content else "✗"
            summary_display = "✓" if src.summary else "✗"
            # Escape pipes in title
            title_escaped = src.title.replace("|", "\\|")
            lines.append(f"| {src.index + 1} | {title_escaped} | {src.source_type.value} | {url_display} | {content_display} | {summary_display} |")
        lines.append("")
        
        # Wikilinks to source files
        lines.append("### Source Files")
        lines.append("")
        for src in notebook.sources:
            fname = src.filename()
            lines.append(f"- [[Sources/{fname}|{src.title}]]")
        lines.append("")
    
    # Notes section
    if notebook.notes:
        lines.extend([
            "## Notes & Artifacts",
            "",
        ])
        for note in notebook.notes:
            fname = note.filename()
            lines.append(f"- [[Notes/{fname}|{note.title}]] ({note.note_type.value})")
        lines.append("")
    
    return "\n".join(lines)


def generate_source_markdown(source: Source, notebook_title: str) -> str:
    """Generate markdown for a single source."""
    fm = generate_frontmatter(source.to_frontmatter(notebook_title))
    
    lines = [
        fm,
        f"# {source.title}",
        "",
    ]
    
    # Source metadata
    lines.extend([
        "## Source Info",
        "",
        f"- **Source ID**: `{source.id}`",
        f"- **Type**: {source.source_type.value}",
    ])
    if source.url:
        lines.append(f"- **URL**: {source.url}")
    if source.created_at:
        lines.append(f"- **Added**: {source.created_at.isoformat()}")
    lines.append("")
    
    # Summary
    if source.summary:
        lines.extend([
            "## Summary",
            "",
            source.summary,
            "",
        ])
    
    # Full content
    if source.content:
        lines.extend([
            "## Full Content",
            "",
            source.content,
            "",
        ])
    else:
        lines.extend([
            "## Full Content",
            "",
            "*Full content not available in public share.*",
            "",
        ])
    
    # Metadata
    if source.metadata:
        lines.extend([
            "## Additional Metadata",
            "",
        ])
        for k, v in source.metadata.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    
    # Backlink to notebook
    lines.extend([
        "---",
        f"*Source from [[{notebook_title}]]*",
    ])
    
    return "\n".join(lines)


def generate_note_markdown(note: Note, notebook_title: str) -> str:
    """Generate markdown for a note/artifact."""
    fm = generate_frontmatter(note.to_frontmatter(notebook_title))
    
    lines = [
        fm,
        f"# {note.title}",
        "",
    ]
    
    # Note metadata
    lines.extend([
        "## Note Info",
        "",
        f"- **Note ID**: `{note.id}`",
        f"- **Type**: {note.note_type.value}",
    ])
    if note.created_at:
        lines.append(f"- **Created**: {note.created_at.isoformat()}")
    if note.source_ids:
        lines.append(f"- **Source IDs**: {', '.join(f'`{sid}`' for sid in note.source_ids)}")
    lines.append("")
    
    # Content
    if note.content:
        lines.extend([
            "## Content",
            "",
            note.content,
            "",
        ])
    
    # Metadata
    if note.metadata:
        lines.extend([
            "## Additional Metadata",
            "",
        ])
        for k, v in note.metadata.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    
    # Backlink to notebook
    lines.extend([
        "---",
        f"*Note from [[{notebook_title}]]*",
    ])
    
    return "\n".join(lines)


def generate_all_markdown(notebook: Notebook) -> dict[str, str]:
    """Generate all markdown files for a notebook."""
    files = {}
    
    # Main notebook file
    files["Notebook.md"] = generate_notebook_markdown(notebook)
    
    # Sources
    for source in notebook.sources:
        fname = f"Sources/{source.filename()}"
        files[fname] = generate_source_markdown(source, notebook.metadata.title)
    
    # Notes
    for note in notebook.notes:
        fname = f"Notes/{note.filename()}"
        files[fname] = generate_note_markdown(note, notebook.metadata.title)
    
    return files