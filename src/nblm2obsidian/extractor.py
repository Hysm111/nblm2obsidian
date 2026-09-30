"""Extractor for public NotebookLM notebooks."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .models import (
    Notebook,
    NotebookMetadata,
    Source,
    SourceType,
    Note,
    NoteType,
    parse_notebook_url,
    sanitize_filename,
)
from .errors import (
    InvalidURLError,
    NotebookNotAccessibleError,
    NotebookNotFoundError,
    ExtractionError,
    NetworkError,
)


# RPC Method IDs from notebooklm-py
RPC_METHODS = {
    "GET_NOTEBOOK": "rLM1Ne",
    "LIST_SOURCES": "hizoJc",  # GET_SOURCE
    "GET_NOTEBOOK_GUIDE": "VfAZjd",  # SUMMARIZE / GenerateNotebookGuide
    "GET_NOTES": "cFji9",  # GET_NOTES_AND_MIND_MAPS
    "LIST_ARTIFACTS": "gArtLc",
    "GET_SHARE_STATUS": "JFMDGd",
}

BATCHEXECUTE_URL = "https://notebook.google.com/_/LabsTailwindUi/data/batchexecute"


@dataclass
class ExtractionResult:
    """Result of notebook extraction."""
    notebook: Notebook
    warnings: list[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class PublicNotebookExtractor:
    """Extract content from publicly shared NotebookLM notebooks."""
    
    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        verbose: bool = False,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.verbose = verbose
        self._client: httpx.AsyncClient | None = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    def _log(self, msg: str):
        if self.verbose:
            print(f"[extractor] {msg}")
    
    async def extract_from_url(self, url: str) -> ExtractionResult:
        """Extract notebook content from a public share URL."""
        notebook_id = parse_notebook_url(url)
        if not notebook_id:
            raise InvalidURLError(f"Invalid NotebookLM share URL: {url}")
        
        self._log(f"Extracted notebook ID: {notebook_id}")
        return await self.extract(notebook_id, share_url=url)
    
    async def extract(self, notebook_id: str, share_url: str | None = None) -> ExtractionResult:
        """Extract notebook content by notebook ID."""
        warnings = []
        
        # First, check if the notebook is publicly accessible
        is_accessible, share_status = await self._check_public_access(notebook_id, share_url)
        if not is_accessible:
            raise NotebookNotAccessibleError(
                f"Notebook {notebook_id} is not publicly accessible or does not exist",
                notebook_id=notebook_id,
                url=share_url,
            )
        
        self._log(f"Notebook is publicly accessible: {share_status}")
        
        # Extract notebook metadata
        metadata = await self._extract_metadata(notebook_id, share_url, share_status)
        
        # Extract sources
        sources = await self._extract_sources(notebook_id)
        if not sources:
            warnings.append("No sources found or accessible in this notebook")
        
        # Extract notes/artifacts
        notes = await self._extract_notes(notebook_id)
        
        notebook = Notebook(
            metadata=metadata,
            sources=sources,
            notes=notes,
        )
        
        return ExtractionResult(notebook=notebook, warnings=warnings)
    
    async def _check_public_access(self, notebook_id: str, share_url: str | None = None) -> tuple[bool, dict[str, Any]]:
        """Check if a notebook is publicly accessible by fetching the share page."""
        # Determine the URL to check - use the share_url if provided, otherwise default
        urls_to_try = []
        
        if share_url:
            parsed = urlparse(share_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            # Add the original share URL
            urls_to_try.append(share_url)
            # Also try the base notebook URL (without /preview)
            if "/preview" in parsed.path:
                base_path = parsed.path.replace("/preview", "")
                urls_to_try.append(f"{base_url}{base_path}")
        else:
            urls_to_try.append(f"https://notebook.google.com/notebook/{notebook_id}")
        
        for url in urls_to_try:
            try:
                resp = await self._client.get(url)
                final_url = str(resp.url)
                
                # If we're redirected to login, try next URL
                if "accounts.google.com" in final_url or "signin" in final_url:
                    self._log(f"Notebook {notebook_id} redirects to login at {url}")
                    continue
                
                # Check if the page contains notebook data
                if self._page_contains_notebook_data(resp.text):
                    self._log(f"Notebook {notebook_id} page contains notebook data at {url}")
                    return True, {"share_url": share_url or url, "is_public": True}
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    continue  # Try next URL
                raise NetworkError(f"HTTP error checking access: {e}", url=url, status_code=e.response.status_code)
            except httpx.RequestError as e:
                self._log(f"Network error checking {url}: {e}")
                continue
        
        # Try to get share status via RPC as fallback
        share_status = await self._get_share_status_rpc(notebook_id)
        if share_status.get("is_public"):
            return True, share_status
        
        return False, {}
    
    def _page_contains_notebook_data(self, html: str) -> bool:
        """Check if the HTML page contains notebook data (not just login page)."""
        # Look for indicators of notebook content
        indicators = [
            "notebooklm",
            "LabsTailwindUi",
            "batchexecute",
            "notebook",
            "source",
        ]
        html_lower = html.lower()
        return any(ind in html_lower for ind in indicators) and "signin" not in html_lower
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def _batchexecute_call(self, method_id: str, params: list[Any]) -> Any:
        """Make a batchexecute RPC call."""
        payload = [[[method_id, json.dumps(params), None, "generic"]]]
        
        resp = await self._client.post(
            BATCHEXECUTE_URL,
            data={"f.req": json.dumps(payload)},
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Referer": "https://notebook.google.com/",
                "Origin": "https://notebook.google.com",
            },
        )
        resp.raise_for_status()
        
        # Parse the response
        return self._parse_batchexecute_response(resp.text)
    
    def _parse_batchexecute_response(self, text: str) -> Any:
        """Parse Google's batchexecute response format."""
        # Response format: )]}'\n[[...]]
        lines = text.strip().split('\n')
        if not lines:
            return None
        
        # Find the JSON line
        json_line = None
        for line in lines:
            if line.startswith('['):
                json_line = line
                break
        
        if not json_line:
            return None
        
        try:
            data = json.loads(json_line)
            # The response is typically: [[method_id, result, ...], ...]
            if isinstance(data, list) and len(data) > 0:
                # First element is usually the response
                first = data[0]
                if isinstance(first, list) and len(first) > 1:
                    return first[1]  # The actual result
            return data
        except json.JSONDecodeError:
            return None
    
    async def _get_share_status_rpc(self, notebook_id: str) -> dict[str, Any]:
        """Get share status via RPC."""
        try:
            result = await self._batchexecute_call(RPC_METHODS["GET_SHARE_STATUS"], [notebook_id])
            if result:
                # Parse the share status response
                # Format: [user_entries, public_block, max_limit, is_public_sharing_allowed, ...]
                is_public = False
                if isinstance(result, list) and len(result) > 1:
                    public_block = result[1]
                    if isinstance(public_block, list) and len(public_block) > 0:
                        is_public = bool(public_block[0])
                
                return {
                    "is_public": is_public,
                    "share_url": f"https://notebook.google.com/notebook/{notebook_id}" if is_public else None,
                }
        except Exception as e:
            self._log(f"Failed to get share status via RPC: {e}")
        return {}
    
    async def _extract_metadata(self, notebook_id: str, share_url: str | None, share_status: dict) -> NotebookMetadata:
        """Extract notebook metadata."""
        # Try to get notebook data via RPC
        notebook_data = await self._get_notebook_rpc(notebook_id)
        
        title = notebook_id
        description = None
        sources_count = 0
        created_at = None
        updated_at = None
        
        if notebook_data:
            # Parse notebook data
            # Format varies, try to extract common fields
            if isinstance(notebook_data, list) and len(notebook_data) > 0:
                nb = notebook_data[0]
                if isinstance(nb, list):
                    # Typical format: [id, title, created_timestamp, ...]
                    if len(nb) > 1:
                        title = str(nb[1]) if nb[1] else notebook_id
                    if len(nb) > 2 and nb[2]:
                        try:
                            created_at = datetime.fromtimestamp(nb[2] / 1000 if nb[2] > 1e12 else nb[2])
                        except (ValueError, TypeError):
                            pass
                    if len(nb) > 3 and nb[3]:
                        try:
                            updated_at = datetime.fromtimestamp(nb[3] / 1000 if nb[3] > 1e12 else nb[3])
                        except (ValueError, TypeError):
                            pass
        
        # Try to get description from notebook guide
        guide = await self._get_notebook_guide(notebook_id)
        if guide and isinstance(guide, str) and guide.strip():
            description = guide.strip()
        
        return NotebookMetadata(
            id=notebook_id,
            title=title,
            description=description,
            share_url=share_url,
            is_public=share_status.get("is_public", False),
            view_level=share_status.get("view_level", "full"),
            sources_count=sources_count,
            created_at=created_at,
            updated_at=updated_at,
        )
    
    async def _get_notebook_rpc(self, notebook_id: str) -> Any:
        """Get notebook data via RPC."""
        try:
            return await self._batchexecute_call(RPC_METHODS["GET_NOTEBOOK"], [notebook_id])
        except Exception as e:
            self._log(f"Failed to get notebook via RPC: {e}")
        return None
    
    async def _get_notebook_guide(self, notebook_id: str) -> str | None:
        """Get notebook guide/summary via RPC."""
        try:
            result = await self._batchexecute_call(RPC_METHODS["GET_NOTEBOOK_GUIDE"], [notebook_id])
            if result and isinstance(result, list) and len(result) > 0:
                # Guide format: [summary, suggested_topics...]
                return str(result[0]) if result[0] else None
        except Exception as e:
            self._log(f"Failed to get notebook guide: {e}")
        return None
    
    async def _extract_sources(self, notebook_id: str) -> list[Source]:
        """Extract all sources from the notebook."""
        sources = []
        
        # First, try to get source IDs from the notebook
        source_ids = await self._get_source_ids(notebook_id)
        
        for idx, source_id in enumerate(source_ids):
            source = await self._extract_source(notebook_id, source_id, idx)
            if source:
                sources.append(source)
        
        return sources
    
    async def _get_source_ids(self, notebook_id: str) -> list[str]:
        """Get all source IDs from a notebook."""
        # Try to get from notebook data
        notebook_data = await self._get_notebook_rpc(notebook_id)
        source_ids = []
        
        if notebook_data and isinstance(notebook_data, list):
            # Source IDs are typically in notebook_data[0][1] or similar
            def extract_ids(obj):
                if isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, str) and len(item) > 10 and item.startswith(("source_", "src_")):
                            source_ids.append(item)
                        elif isinstance(item, (list, dict)):
                            extract_ids(item)
                elif isinstance(obj, dict):
                    for v in obj.values():
                        extract_ids(v)
            
            extract_ids(notebook_data)
        
        # If no source IDs found, try to get from sources listing
        if not source_ids:
            # Try listing sources via GET_SOURCE with empty params? Not sure if this works
            pass
        
        return source_ids
    
    async def _extract_source(self, notebook_id: str, source_id: str, index: int) -> Source | None:
        """Extract a single source."""
        try:
            result = await self._batchexecute_call(RPC_METHODS["LIST_SOURCES"], [source_id])
            
            if not result:
                return None
            
            # Parse source data
            # Format varies, try to extract common fields
            title = source_id
            source_type = SourceType.UNKNOWN
            url = None
            content = None
            summary = None
            metadata = {}
            created_at = None
            
            if isinstance(result, list) and len(result) > 0:
                src = result[0]
                if isinstance(src, list):
                    # Typical format: [id, title, type, url, content, ...]
                    if len(src) > 1 and src[1]:
                        title = str(src[1])
                    if len(src) > 2:
                        type_val = src[2]
                        if isinstance(type_val, int):
                            # Map type codes to SourceType
                            type_map = {
                                1: SourceType.URL,
                                2: SourceType.PDF,
                                3: SourceType.TEXT,
                                4: SourceType.GOOGLE_DOC,
                                5: SourceType.GOOGLE_DRIVE,
                                6: SourceType.YOUTUBE,
                                7: SourceType.AUDIO,
                            }
                            source_type = type_map.get(type_val, SourceType.UNKNOWN)
                    if len(src) > 3 and src[3]:
                        url = str(src[3])
                    if len(src) > 4 and src[4]:
                        content = str(src[4])
                    if len(src) > 5 and src[5]:
                        summary = str(src[5])
                    if len(src) > 6 and src[6]:
                        try:
                            created_at = datetime.fromtimestamp(
                                src[6] / 1000 if src[6] > 1e12 else src[6]
                            )
                        except (ValueError, TypeError):
                            pass
            
            return Source(
                id=source_id,
                notebook_id=notebook_id,
                title=title,
                source_type=source_type,
                url=url,
                content=content,
                summary=summary,
                metadata=metadata,
                created_at=created_at,
                index=index,
            )
        except Exception as e:
            self._log(f"Failed to extract source {source_id}: {e}")
            return None
    
    async def _extract_notes(self, notebook_id: str) -> list[Note]:
        """Extract notes and generated artifacts from the notebook."""
        notes = []
        
        try:
            # Try to get notes via RPC
            result = await self._batchexecute_call(RPC_METHODS["GET_NOTES"], [notebook_id])
            
            if result and isinstance(result, list):
                for item in result:
                    note = self._parse_note(notebook_id, item)
                    if note:
                        notes.append(note)
        except Exception as e:
            self._log(f"Failed to extract notes: {e}")
        
        # Also try to get artifacts
        try:
            artifacts = await self._get_artifacts(notebook_id)
            for artifact in artifacts:
                note = self._parse_artifact(notebook_id, artifact)
                if note:
                    notes.append(note)
        except Exception as e:
            self._log(f"Failed to extract artifacts: {e}")
        
        return notes
    
    def _parse_note(self, notebook_id: str, data: Any) -> Note | None:
        """Parse a note from RPC response."""
        try:
            if not isinstance(data, list):
                return None
            
            # Note format: [id, title, content, type, source_ids, ...]
            note_id = str(data[0]) if data else "unknown"
            title = str(data[1]) if len(data) > 1 and data[1] else "Untitled Note"
            content = str(data[2]) if len(data) > 2 and data[2] else ""
            note_type = NoteType.USER_NOTE
            source_ids = []
            
            if len(data) > 3:
                type_val = data[3]
                if isinstance(type_val, int):
                    type_map = {
                        1: NoteType.SUMMARY,
                        2: NoteType.FAQ,
                        3: NoteType.STUDY_GUIDE,
                        4: NoteType.TIMELINE,
                        5: NoteType.BRIEFING_DOC,
                        6: NoteType.GENERATED,
                    }
                    note_type = type_map.get(type_val, NoteType.USER_NOTE)
            
            if len(data) > 4 and isinstance(data[4], list):
                source_ids = [str(s) for s in data[4] if s]
            
            return Note(
                id=note_id,
                notebook_id=notebook_id,
                title=title,
                note_type=note_type,
                content=content,
                source_ids=source_ids,
            )
        except Exception:
            return None
    
    async def _get_artifacts(self, notebook_id: str) -> list[Any]:
        """Get generated artifacts from the notebook."""
        try:
            result = await self._batchexecute_call(RPC_METHODS["LIST_ARTIFACTS"], [notebook_id])
            if result and isinstance(result, list):
                return result
        except Exception as e:
            self._log(f"Failed to get artifacts: {e}")
        return []
    
    def _parse_artifact(self, notebook_id: str, data: Any) -> Note | None:
        """Parse an artifact as a note."""
        try:
            if not isinstance(data, list):
                return None
            
            # Artifact format: [id, title, type, content, ...]
            artifact_id = str(data[0]) if data else "unknown"
            title = str(data[1]) if len(data) > 1 and data[1] else "Untitled Artifact"
            artifact_type = data[2] if len(data) > 2 else 0
            content = str(data[3]) if len(data) > 3 and data[3] else ""
            
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
            }
            note_type = type_map.get(artifact_type, NoteType.GENERATED)
            
            return Note(
                id=artifact_id,
                notebook_id=notebook_id,
                title=title,
                note_type=note_type,
                content=content,
                metadata={"artifact_type": artifact_type},
            )
        except Exception:
            return None


async def inspect_notebook(url: str, verbose: bool = False) -> dict[str, Any]:
    """Inspect a public notebook and return what's accessible."""
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        raise InvalidURLError(f"Invalid NotebookLM share URL: {url}")
    
    async with PublicNotebookExtractor(verbose=verbose) as extractor:
        # Check accessibility
        is_accessible, share_status = await extractor._check_public_access(notebook_id)
        
        result = {
            "notebook_id": notebook_id,
            "share_url": url,
            "is_publicly_accessible": is_accessible,
            "share_status": share_status,
        }
        
        if is_accessible:
            # Try to get basic metadata
            metadata = await extractor._extract_metadata(notebook_id, url, share_status)
            result["title"] = metadata.title
            result["description"] = metadata.description
            
            # Try to get source count
            source_ids = await extractor._get_source_ids(notebook_id)
            result["source_count"] = len(source_ids)
            result["source_ids"] = source_ids
            
            # Try to get notes count
            notes_result = await extractor._batchexecute_call(RPC_METHODS["GET_NOTES"], [notebook_id])
            result["notes_count"] = len(notes_result) if notes_result and isinstance(notes_result, list) else 0
            
            # Try to get artifacts count
            artifacts = await extractor._get_artifacts(notebook_id)
            result["artifacts_count"] = len(artifacts)
        else:
            result["error"] = "Notebook is not publicly accessible (private, deleted, or invalid)"
        
        return result


async def list_sources(url: str, verbose: bool = False) -> list[dict[str, Any]]:
    """List sources from a public notebook."""
    notebook_id = parse_notebook_url(url)
    if not notebook_id:
        raise InvalidURLError(f"Invalid NotebookLM share URL: {url}")
    
    async with PublicNotebookExtractor(verbose=verbose) as extractor:
        is_accessible, _ = await extractor._check_public_access(notebook_id)
        if not is_accessible:
            raise NotebookNotAccessibleError(f"Notebook {notebook_id} is not publicly accessible")
        
        sources = await extractor._extract_sources(notebook_id)
        return [
            {
                "id": s.id,
                "title": s.title,
                "type": s.source_type.value,
                "url": s.url,
                "has_content": s.content is not None and len(s.content) > 0,
                "has_summary": s.summary is not None and len(s.summary) > 0,
                "summary_preview": s.summary[:200] if s.summary else None,
            }
            for s in sources
        ]