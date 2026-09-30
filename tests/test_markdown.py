"""Tests for markdown generation."""

import pytest
from datetime import datetime

from nblm2obsidian.models import (
    Notebook,
    NotebookMetadata,
    Source,
    Note,
    SourceType,
    NoteType,
)
from nblm2obsidian.markdown import (
    generate_frontmatter,
    generate_notebook_markdown,
    generate_source_markdown,
    generate_note_markdown,
    generate_all_markdown,
)


@pytest.fixture
def sample_notebook():
    meta = NotebookMetadata(
        id="nb123",
        title="Test Notebook",
        description="A test notebook description",
        share_url="https://notebooklm.google.com/notebook/nb123",
        is_public=True,
        view_level="full",
        sources_count=2,
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 2, 12, 0, 0),
    )
    
    sources = [
        Source(
            id="src1",
            notebook_id="nb123",
            title="Source One",
            source_type=SourceType.URL,
            url="https://example.com/1",
            content="Full content of source one",
            summary="Summary of source one",
            index=0,
        ),
        Source(
            id="src2",
            notebook_id="nb123",
            title="Source Two",
            source_type=SourceType.PDF,
            content="Full content of source two",
            index=1,
        ),
    ]
    
    notes = [
        Note(
            id="note1",
            notebook_id="nb123",
            title="Summary Note",
            note_type=NoteType.SUMMARY,
            content="This is a summary",
            source_ids=["src1", "src2"],
        ),
        Note(
            id="note2",
            notebook_id="nb123",
            title="FAQ",
            note_type=NoteType.FAQ,
            content="Q: What? A: This.",
        ),
    ]
    
    return Notebook(metadata=meta, sources=sources, notes=notes)


class TestGenerateFrontmatter:
    def test_basic(self):
        data = {"key": "value", "num": 42}
        result = generate_frontmatter(data)
        assert result.startswith("---\n")
        assert result.endswith("---\n")
        assert "key: value" in result
        assert "num: 42" in result
    
    def test_none_values_removed(self):
        data = {"key": "value", "none_key": None}
        result = generate_frontmatter(data)
        assert "none_key" not in result
    
    def test_unicode(self):
        data = {"title": "测试"}
        result = generate_frontmatter(data)
        assert "测试" in result


class TestGenerateNotebookMarkdown:
    def test_basic_structure(self, sample_notebook):
        md = generate_notebook_markdown(sample_notebook)
        
        assert md.startswith("---\n")
        assert "# Test Notebook" in md
        assert "A test notebook description" in md
        assert "## Metadata" in md
        assert "**Notebook ID**: `nb123`" in md
        assert "**Share URL**: https://notebooklm.google.com/notebook/nb123" in md
        assert "**Public**: Yes" in md
        assert "**Sources**: 2" in md
        assert "**Notes/Artifacts**: 2" in md
    
    def test_sources_table(self, sample_notebook):
        md = generate_notebook_markdown(sample_notebook)
        
        assert "## Sources" in md
        assert "| # | Title | Type | URL | Content | Summary |" in md
        assert "Source One" in md
        assert "Source Two" in md
        assert "url" in md
        assert "pdf" in md
        assert "[Link](https://example.com/1)" in md
    
    def test_source_files_wikilinks(self, sample_notebook):
        md = generate_notebook_markdown(sample_notebook)
        
        assert "### Source Files" in md
        # Sources have index 0 and 1, so filenames are 01 and 02
        assert "[[Sources/01 - Source_One.md|Source One]]" in md
        assert "[[Sources/02 - Source_Two.md|Source Two]]" in md
    
    def test_notes_wikilinks(self, sample_notebook):
        md = generate_notebook_markdown(sample_notebook)
        
        assert "## Notes & Artifacts" in md
        assert "[[Notes/Summary_Note.md|Summary Note]] (summary)" in md
        assert "[[Notes/FAQ.md|FAQ]] (faq)" in md


class TestGenerateSourceMarkdown:
    def test_with_all_fields(self, sample_notebook):
        source = sample_notebook.sources[0]
        md = generate_source_markdown(source, "Test Notebook")
        
        assert md.startswith("---\n")
        assert "# Source One" in md
        assert "**Source ID**: `src1`" in md
        assert "**Type**: url" in md
        assert "**URL**: https://example.com/1" in md
        assert "## Summary" in md
        assert "Summary of source one" in md
        assert "## Full Content" in md
        assert "Full content of source one" in md
        assert "*Source from [[Test Notebook]]*" in md
    
    def test_without_content(self):
        source = Source(
            id="src3",
            notebook_id="nb123",
            title="No Content Source",
            source_type=SourceType.URL,
            url="https://example.com/3",
        )
        md = generate_source_markdown(source, "Test Notebook")
        
        assert "*Full content not available in public share.*" in md


class TestGenerateNoteMarkdown:
    def test_basic(self, sample_notebook):
        note = sample_notebook.notes[0]
        md = generate_note_markdown(note, "Test Notebook")
        
        assert md.startswith("---\n")
        assert "# Summary Note" in md
        assert "**Note ID**: `note1`" in md
        assert "**Type**: summary" in md
        assert "**Source IDs**: `src1`, `src2`" in md
        assert "## Content" in md
        assert "This is a summary" in md
        assert "*Note from [[Test Notebook]]*" in md


class TestGenerateAllMarkdown:
    def test_all_files(self, sample_notebook):
        files = generate_all_markdown(sample_notebook)
        
        assert "Notebook.md" in files
        assert "Sources/01 - Source_One.md" in files
        assert "Sources/02 - Source_Two.md" in files
        assert "Notes/Summary_Note.md" in files
        assert "Notes/FAQ.md" in files
        
        # Check content
        assert "# Test Notebook" in files["Notebook.md"]
        assert "# Source One" in files["Sources/01 - Source_One.md"]
        assert "# Summary Note" in files["Notes/Summary_Note.md"]