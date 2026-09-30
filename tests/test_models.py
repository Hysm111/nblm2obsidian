"""Tests for models module."""

import pytest
from datetime import datetime

from nblm2obsidian.models import (
    NotebookMetadata,
    Source,
    Note,
    SourceType,
    NoteType,
    Notebook,
    parse_notebook_url,
    sanitize_filename,
)


class TestSanitizeFilename:
    def test_basic(self):
        assert sanitize_filename("Hello World") == "Hello_World"
    
    def test_invalid_chars(self):
        # 9 special chars: < > : " / \ | ? *
        assert sanitize_filename('test<>:"/\\|?*file') == "test_________file"
    
    def test_control_chars(self):
        assert sanitize_filename("test\x00\x1ffile") == "test__file"
    
    def test_multiple_spaces(self):
        assert sanitize_filename("  test   file  ") == "test_file"
    
    def test_empty(self):
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("   ") == "untitled"
    
    def test_truncation(self):
        long_name = "a" * 150
        result = sanitize_filename(long_name, max_length=100)
        assert len(result) == 100
    
    def test_unicode(self):
        assert sanitize_filename("测试文件") == "测试文件"
        assert sanitize_filename("café") == "café"


class TestParseNotebookURL:
    def test_notebooklm_domain_notebook(self):
        url = "https://notebooklm.google.com/notebook/abc123"
        assert parse_notebook_url(url) == "abc123"
    
    def test_notebook_domain_notebook(self):
        url = "https://notebook.google.com/notebook/abc123"
        assert parse_notebook_url(url) == "abc123"
    
    def test_notebooklm_domain_share(self):
        url = "https://notebooklm.google.com/share/abc123"
        assert parse_notebook_url(url) == "abc123"
    
    def test_notebook_domain_share(self):
        url = "https://notebook.google.com/share/abc123"
        assert parse_notebook_url(url) == "abc123"
    
    def test_with_query_params(self):
        url = "https://notebooklm.google.com/notebook/abc123?foo=bar"
        assert parse_notebook_url(url) == "abc123"
    
    def test_invalid_domain(self):
        url = "https://example.com/notebook/abc123"
        assert parse_notebook_url(url) is None
    
    def test_invalid_path(self):
        url = "https://notebooklm.google.com/invalid/abc123"
        assert parse_notebook_url(url) is None


class TestNotebookMetadata:
    def test_to_frontmatter(self):
        meta = NotebookMetadata(
            id="test123",
            title="Test Notebook",
            description="A test notebook",
            share_url="https://notebooklm.google.com/notebook/test123",
            is_public=True,
            view_level="full",
            sources_count=5,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 2, 12, 0, 0),
        )
        fm = meta.to_frontmatter()
        
        assert fm["source"] == "notebooklm"
        assert fm["notebook"] == "Test Notebook"
        assert fm["notebook_id"] == "test123"
        assert fm["type"] == "notebook"
        assert fm["share_url"] == "https://notebooklm.google.com/notebook/test123"
        assert fm["is_public"] is True
        assert fm["view_level"] == "full"
        assert fm["sources_count"] == 5


class TestSource:
    def test_to_frontmatter(self):
        source = Source(
            id="src123",
            notebook_id="nb123",
            title="Test Source",
            source_type=SourceType.URL,
            url="https://example.com",
            summary="A test source",
            metadata={"author": "John Doe"},
        )
        fm = source.to_frontmatter("Test Notebook")
        
        assert fm["source"] == "notebooklm"
        assert fm["notebook"] == "Test Notebook"
        assert fm["type"] == "source"
        assert fm["source_id"] == "src123"
        assert fm["source_type"] == "url"
        assert fm["source_title"] == "Test Source"
        assert fm["source_url"] == "https://example.com"
        assert fm["summary"] == "A test source"
        assert fm["source_author"] == "John Doe"
    
    def test_filename(self):
        source = Source(
            id="src123",
            notebook_id="nb123",
            title="My Source Title",
            source_type=SourceType.URL,
            index=0,
        )
        assert source.filename() == "01 - My_Source_Title.md"
        
        source.index = 9
        assert source.filename() == "10 - My_Source_Title.md"


class TestNote:
    def test_to_frontmatter(self):
        note = Note(
            id="note123",
            notebook_id="nb123",
            title="Test Note",
            note_type=NoteType.SUMMARY,
            content="Note content",
            source_ids=["src1", "src2"],
            metadata={"tags": ["important"]},
        )
        fm = note.to_frontmatter("Test Notebook")
        
        assert fm["source"] == "notebooklm"
        assert fm["notebook"] == "Test Notebook"
        assert fm["type"] == "note"
        assert fm["note_id"] == "note123"
        assert fm["note_type"] == "summary"
        assert fm["title"] == "Test Note"
        assert fm["source_ids"] == ["src1", "src2"]
        assert fm["note_tags"] == ["important"]
    
    def test_filename(self):
        note = Note(
            id="note123",
            notebook_id="nb123",
            title="My Note Title",
            note_type=NoteType.SUMMARY,
            content="Content",
        )
        assert note.filename() == "My_Note_Title.md"


class TestNotebook:
    def test_to_frontmatter(self):
        meta = NotebookMetadata(id="nb123", title="Test")
        notebook = Notebook(metadata=meta)
        fm = notebook.to_frontmatter()
        
        assert fm["notebook_id"] == "nb123"
        assert fm["notebook"] == "Test"