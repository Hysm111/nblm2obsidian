"""Authenticated extractor for NotebookLM notebooks using notebooklm-py."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from notebooklm import NotebookLMClient

from .models import (
    Notebook,
    NotebookMetadata,
    Source,
    SourceType,
    Note,
    NoteType,
    parse_notebook_url,
)
from .errors import (
    InvalidURLError,
    NotebookNotAccessibleError,
    NotebookNotFoundError,
    ExtractionError,
    NetworkError,
)
from .auth import AuthManager, get_auth_manager


@dataclass
class ExtractionResult:
    """Result of notebook extraction."""
    notebook: Notebook
    warnings: list[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class AuthenticatedNotebookExtractor:
    """Extract content from NotebookLM notebooks using authenticated client."""
    
    def __init__(
        self,
        auth_manager: Optional[AuthManager] = None,
        timeout: float = 30.0,
        verbose: bool = False,
    ):
        self.timeout = timeout
        self.verbose = verbose
        self.auth_manager = auth_manager or get_auth_manager()
        self._client: Optional[NotebookLMClient] = None
    
    async def __aenter__(self):
        if not self.auth_manager.is_authenticated():
            raise RuntimeError(
                "Not authenticated. Run 'nblm2obsidian login' first."
            )
        self._client = self.auth_manager.get_client(timeout=self.timeout)
        await self._client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)
    
    def _log(self, msg: str):
        if self.verbose:
            print(f"[auth-extractor] {msg}")
    
    async def extract_from_url(self, url: str) -> ExtractionResult:
        """Extract notebook content from a share URL."""
        notebook_id = parse_notebook_url(url)
        if not notebook_id:
            raise InvalidURLError(f"Invalid NotebookLM share URL: {url}")
        
        self._log(f"Extracted notebook ID: {notebook_id}")
        return await self.extract(notebook_id, share_url=url)
    
    async def extract(self, notebook_id: str, share_url: str | None = None) -> ExtractionResult:
        """Extract notebook content by notebook ID."""
        warnings = []
        
        # Verify we can access the notebook
        try:
            notebook = await self._client.notebooks.get(notebook_id)
        except Exception as e:
            raise NotebookNotAccessibleError(
                f"Notebook {notebook_id} is not accessible: {e}",
                notebook_id=notebook_id,
                url=share_url,
            )
        
        self._log(f"Accessing notebook: {notebook.title}")
        
        # Extract notebook metadata
        metadata = await self._extract_metadata(notebook_id, share_url, notebook)
        
        # Extract sources
        sources = await self._extract_sources(notebook_id)
        if not sources:
            warnings.append("No sources found or accessible in this notebook")
        
        # Extract notes/artifacts
        notes = await self._extract_notes(notebook_id)
        
        result_notebook = Notebook(
            metadata=metadata,
            sources=sources,
            notes=notes,
        )
        
        return ExtractionResult(notebook=result_notebook, warnings=warnings)
    
    async def _extract_metadata(self, notebook_id: str, share_url: str | None, notebook: Any) -> NotebookMetadata:
        """Extract notebook metadata from authenticated client."""
        title = getattr(notebook, 'title', notebook_id)
        description = None
        sources_count = getattr(notebook, 'sources_count', 0)
        created_at = getattr(notebook, 'created_at', None)
        updated_at = getattr(notebook, 'modified_at', None) or getattr(notebook, 'last_viewed_at', None)
        
        # Try to get description from notebook guide
        try:
            guide = await self._client.notebooks.get_description(notebook_id)
            if guide and guide.summary:
                description = guide.summary
        except Exception as e:
            self._log(f"Failed to get notebook guide: {e}")
        
        return NotebookMetadata(
            id=notebook_id,
            title=title,
            description=description,
            share_url=share_url,
            is_public=True,  # We have authenticated access
            view_level="full",
            sources_count=sources_count,
            created_at=created_at,
            updated_at=updated_at,
        )
    
    async def _extract_sources(self, notebook_id: str) -> list[Source]:
        """Extract all sources from the notebook."""
        sources = []
        
        try:
            # List all sources
            source_list = await self._client.sources.list(notebook_id)
            
            for idx, src in enumerate(source_list):
                source = await self._extract_source(notebook_id, src, idx)
                if source:
                    sources.append(source)
        except Exception as e:
            self._log(f"Failed to extract sources: {e}")
        
        return sources
    
    async def _extract_source(self, notebook_id: str, src: Any, index: int) -> Source | None:
        """Extract a single source."""
        try:
            source_id = getattr(src, 'id', str(src))
            title = getattr(src, 'title', 'Untitled Source')
            
            # Get full source content
            try:
                full_source = await self._client.sources.get(source_id)
                
                # Extract content
                content = getattr(full_source, 'fulltext', None)
                if content is None:
                    content = getattr(full_source, 'content', None)
                
                summary = getattr(full_source, 'summary', None)
                url = getattr(full_source, 'url', None) or getattr(full_source, 'source_url', None)
                
                # Determine source type
                source_type = SourceType.UNKNOWN
                src_type = getattr(full_source, 'type', None) or getattr(full_source, 'source_type', None)
                if src_type:
                    type_map = {
                        1: SourceType.URL,
                        2: SourceType.PDF,
                        3: SourceType.TEXT,
                        4: SourceType.GOOGLE_DOC,
                        5: SourceType.GOOGLE_DRIVE,
                        6: SourceType.YOUTUBE,
                        7: SourceType.AUDIO,
                        'url': SourceType.URL,
                        'pdf': SourceType.PDF,
                        'text': SourceType.TEXT,
                        'google_doc': SourceType.GOOGLE_DOC,
                        'google_drive': SourceType.GOOGLE_DRIVE,
                        'youtube': SourceType.YOUTUBE,
                        'audio': SourceType.AUDIO,
                    }
                    source_type = type_map.get(str(src_type).lower(), SourceType.UNKNOWN)
                
                created_at = getattr(full_source, 'created_at', None)
                
                return Source(
                    id=source_id,
                    notebook_id=notebook_id,
                    title=title,
                    source_type=source_type,
                    url=url,
                    content=content,
                    summary=summary,
                    metadata={},
                    created_at=created_at,
                    index=index,
                )
            except Exception as e:
                self._log(f"Failed to get full source {source_id}: {e}")
                # Return basic source info
                return Source(
                    id=source_id,
                    notebook_id=notebook_id,
                    title=title,
                    source_type=SourceType.UNKNOWN,
                    index=index,
                )
        except Exception as e:
            self._log(f"Failed to extract source: {e}")
            return None
    
    async def _extract_notes(self, notebook_id: str) -> list[Note]:
        """Extract notes and generated artifacts from the notebook."""
        notes = []
        
        try:
            # Get user notes
            notes_list = await self._client.notes.list(notebook_id)
            
            for note_data in notes_list:
                note = self._parse_note(notebook_id, note_data)
                if note:
                    notes.append(note)
        except Exception as e:
            self._log(f"Failed to extract notes: {e}")
        
        # Try to get artifacts
        try:
            artifacts = await self._client.artifacts.list(notebook_id)
            for artifact in artifacts:
                note = self._parse_artifact(notebook_id, artifact)
                if note:
                    notes.append(note)
        except Exception as e:
            self._log(f"Failed to extract artifacts: {e}")
        
        return notes
    
    def _parse_note(self, notebook_id: str, data: Any) -> Note | None:
        """Parse a note from authenticated client."""
        try:
            note_id = getattr(data, 'id', str(data))
            title = getattr(data, 'title', 'Untitled Note')
            content = getattr(data, 'content', '') or ''
            note_type = NoteType.USER_NOTE
            source_ids = getattr(data, 'source_ids', []) or []
            created_at = getattr(data, 'created_at', None)
            
            # Determine note type
            note_type_val = getattr(data, 'type', None)
            if note_type_val:
                type_map = {
                    1: NoteType.SUMMARY,
                    2: NoteType.FAQ,
                    3: NoteType.STUDY_GUIDE,
                    4: NoteType.TIMELINE,
                    5: NoteType.BRIEFING_DOC,
                    6: NoteType.GENERATED,
                    'summary': NoteType.SUMMARY,
                    'faq': NoteType.FAQ,
                    'study_guide': NoteType.STUDY_GUIDE,
                    'timeline': NoteType.TIMELINE,
                    'briefing_doc': NoteType.BRIEFING_DOC,
                }
                note_type = type_map.get(str(note_type_val).lower(), NoteType.USER_NOTE)
            
            return Note(
                id=note_id,
                notebook_id=notebook_id,
                title=title,
                note_type=note_type,
                content=content,
                source_ids=source_ids,
                created_at=created_at,
            )
        except Exception as e:
            self._log(f"Failed to parse note: {e}")
            return None
    
    def _parse_artifact(self, notebook_id: str, data: Any) -> Note | None:
        """Parse an artifact as a note."""
        try:
            artifact_id = getattr(data, 'id', str(data))
            title = getattr(data, 'title', 'Untitled Artifact')
            content = getattr(data, 'content', '') or getattr(data, 'text', '') or ''
            artifact_type = getattr(data, 'type', 0)
            
            # Map artifact types to note types
            type_map = {
                1: NoteType.SUMMARY,
                2: NoteType.FAQ,
                3: NoteType.STUDY_GUIDE,
                4: NoteType.TIMELINE,
                5: NoteType.BRIEFING_DOC,
                6: NoteType.GENERATED,
                7: NoteType.GENERATED,  # Audio
                8: NoteType.GENERATED,  # Video
                'summary': NoteType.SUMMARY,
                'faq': NoteType.FAQ,
                'study_guide': NoteType.STUDY_GUIDE,
                'timeline': NoteType.TIMELINE,
                'briefing_doc': NoteType.BRIEFING_DOC,
                'audio': NoteType.GENERATED,
                'video': NoteType.GENERATED,
            }
            note_type = type_map.get(str(artifact_type).lower(), NoteType.GENERATED)
            
            return Note(
                id=artifact_id,
                notebook_id=notebook_id,
                title=title,
                note_type=note_type,
                content=content,
                metadata={"artifact_type": artifact_type},
            )
        except Exception as e:
            self._log(f"Failed to parse artifact: {e}")
            return None


async def inspect_notebook_authenticated(url: str, verbose: bool = False) -> dict[str, Any]:
    """Inspect a notebook using authenticated client."""
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        raise InvalidURLError(f"Invalid NotebookLM share URL: {url}")
    
    auth_manager = get_auth_manager()
    
    if not auth_manager.is_authenticated():
        return {
            "notebook_id": notebook_id,
            "share_url": url,
            "is_authenticated": False,
            "error": "Not authenticated. Run 'nblm2obsidian login' first.",
        }
    
    try:
        async with AuthenticatedNotebookExtractor(verbose=verbose) as extractor:
            # Test access
            notebook = await extractor._client.notebooks.get(notebook_id)
            
            # Get sources
            sources = await extractor._client.sources.list(notebook_id)
            
            # Get notes
            notes = await extractor._client.notes.list(notebook_id)
            
            # Get artifacts
            artifacts = await extractor._client.artifacts.list(notebook_id)
            
            return {
                "notebook_id": notebook_id,
                "share_url": url,
                "is_authenticated": True,
                "title": getattr(notebook, 'title', notebook_id),
                "description": None,
                "source_count": len(sources) if sources else 0,
                "notes_count": len(notes) if notes else 0,
                "artifacts_count": len(artifacts) if artifacts else 0,
            }
    except Exception as e:
        return {
            "notebook_id": notebook_id,
            "share_url": url,
            "is_authenticated": True,
            "error": f"Failed to access notebook: {e}",
        }


async def list_sources_authenticated(url: str, verbose: bool = False) -> list[dict[str, Any]]:
    """List sources from a notebook using authenticated client."""
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        raise InvalidURLError(f"Invalid NotebookLM share URL: {url}")
    
    auth_manager = get_auth_manager()
    
    if not auth_manager.is_authenticated():
        raise NotebookNotAccessibleError("Not authenticated. Run 'nblm2obsidian login' first.")
    
    async with AuthenticatedNotebookExtractor(verbose=verbose) as extractor:
        sources = await extractor._client.sources.list(notebook_id)
        
        result = []
        for src in sources:
            source_id = getattr(src, 'id', str(src))
            title = getattr(src, 'title', 'Untitled')
            
            # Try to get more details
            content = None
            summary = None
            source_url = None
            source_type = "unknown"
            
            try:
                full_source = await extractor._client.sources.get(source_id)
                content = getattr(full_source, 'fulltext', None)
                summary = getattr(full_source, 'summary', None)
                source_url = getattr(full_source, 'url', None) or getattr(full_source, 'source_url', None)
                src_type = getattr(full_source, 'type', None)
                if src_type:
                    type_map = {
                        1: 'url', 2: 'pdf', 3: 'text', 4: 'google_doc',
                        5: 'google_drive', 6: 'youtube', 7: 'audio',
                        'url': 'url', 'pdf': 'pdf', 'text': 'text',
                        'google_doc': 'google_doc', 'google_drive': 'google_drive',
                        'youtube': 'youtube', 'audio': 'audio',
                    }
                    source_type = type_map.get(str(src_type).lower(), 'unknown')
            except Exception:
                pass
            
            result.append({
                "id": source_id,
                "title": title,
                "type": source_type,
                "url": source_url,
                "has_content": content is not None and len(str(content)) > 0,
                "has_summary": summary is not None and len(str(summary)) > 0,
                "summary_preview": str(summary)[:200] if summary else None,
            })
        
        return result