"""Data models for nblm2obsidian."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse


class SourceType(Enum):
    """Type of notebook source."""
    URL = "url"
    PDF = "pdf"
    TEXT = "text"
    GOOGLE_DOC = "google_doc"
    GOOGLE_DRIVE = "google_drive"
    YOUTUBE = "youtube"
    AUDIO = "audio"
    UNKNOWN = "unknown"


class NoteType(Enum):
    """Type of notebook note/artifact."""
    SUMMARY = "summary"
    FAQ = "faq"
    STUDY_GUIDE = "study_guide"
    TIMELINE = "timeline"
    BRIEFING_DOC = "briefing_doc"
    GENERATED = "generated"
    USER_NOTE = "user_note"
    UNKNOWN = "unknown"


@dataclass
class NotebookMetadata:
    """Metadata for a NotebookLM notebook."""
    id: str
    title: str
    description: str | None = None
    share_url: str | None = None
    is_public: bool = False
    view_level: str = "full"  # "full" or "chat_only"
    sources_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    imported_at: datetime = field(default_factory=datetime.now)
    
    def to_frontmatter(self) -> dict[str, Any]:
        """Convert to YAML frontmatter dict."""
        return {
            "source": "notebooklm",
            "notebook": self.title,
            "notebook_id": self.id,
            "type": "notebook",
            "share_url": self.share_url,
            "is_public": self.is_public,
            "view_level": self.view_level,
            "sources_count": self.sources_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "imported_at": self.imported_at.isoformat(),
        }


@dataclass
class Source:
    """A source in a NotebookLM notebook."""
    id: str
    notebook_id: str
    title: str
    source_type: SourceType
    url: str | None = None
    content: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    index: int = 0  # Display order
    
    def to_frontmatter(self, notebook_title: str) -> dict[str, Any]:
        """Convert to YAML frontmatter dict."""
        fm = {
            "source": "notebooklm",
            "notebook": notebook_title,
            "type": "source",
            "source_id": self.id,
            "source_type": self.source_type.value,
            "source_title": self.title,
            "imported_at": datetime.now().isoformat(),
        }
        if self.url:
            fm["source_url"] = self.url
        if self.summary:
            fm["summary"] = self.summary
        if self.created_at:
            fm["source_created_at"] = self.created_at.isoformat()
        # Add custom metadata
        for k, v in self.metadata.items():
            if k not in fm:
                fm[f"source_{k}"] = v
        return fm
    
    def filename(self) -> str:
        """Generate a safe filename for this source."""
        safe_title = sanitize_filename(self.title)
        return f"{self.index + 1:02d} - {safe_title}.md"


@dataclass
class Note:
    """A note or generated artifact in a NotebookLM notebook."""
    id: str
    notebook_id: str
    title: str
    note_type: NoteType
    content: str
    source_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    
    def to_frontmatter(self, notebook_title: str) -> dict[str, Any]:
        """Convert to YAML frontmatter dict."""
        fm = {
            "source": "notebooklm",
            "notebook": notebook_title,
            "type": "note",
            "note_id": self.id,
            "note_type": self.note_type.value,
            "title": self.title,
            "imported_at": datetime.now().isoformat(),
        }
        if self.source_ids:
            fm["source_ids"] = self.source_ids
        if self.created_at:
            fm["note_created_at"] = self.created_at.isoformat()
        for k, v in self.metadata.items():
            if k not in fm:
                fm[f"note_{k}"] = v
        return fm
    
    def filename(self) -> str:
        """Generate a safe filename for this note."""
        safe_title = sanitize_filename(self.title)
        return f"{safe_title}.md"


@dataclass
class Notebook:
    """Complete notebook with all content."""
    metadata: NotebookMetadata
    sources: list[Source] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    
    def to_frontmatter(self) -> dict[str, Any]:
        """Convert notebook metadata to frontmatter."""
        return self.metadata.to_frontmatter()


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Sanitize a string for use as a filename."""
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*\x00-\x1f'
    for c in invalid_chars:
        name = name.replace(c, '_')
    # Replace multiple spaces/underscores
    name = '_'.join(part for part in name.split() if part)
    # Truncate
    if len(name) > max_length:
        name = name[:max_length].rstrip('_')
    return name or "untitled"


def parse_notebook_url(url: str) -> str | None:
    """Extract notebook ID from a NotebookLM share URL."""
    parsed = urlparse(url)
    if parsed.netloc not in ("notebooklm.google.com", "notebook.google.com"):
        return None
    
    # Pattern: /notebook/<id>, /notebook/<id>/preview, /share/<id>
    path = parsed.path.strip('/')
    parts = path.split('/')
    
    if len(parts) >= 2 and parts[0] in ("notebook", "share"):
        # For /notebook/<id>/preview, the ID is at index 1
        return parts[1]
    
    return None