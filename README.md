# nblm2obsidian

Import publicly shared Google NotebookLM notebooks into an Obsidian vault.

## Overview

`nblm2obsidian` is a lightweight CLI tool that extracts content from publicly shared Google NotebookLM notebooks and converts them into clean, Obsidian-compatible Markdown files. It requires no Google credentials, cookies, or browser automation — only a public share URL.

## Installation

```bash
pip install nblm2obsidian
```

Or from source:

```bash
git clone https://github.com/yourusername/nblm2obsidian
cd nblm2obsidian
pip install -e .
```

Requires Python 3.11+.

## Usage

### Import a notebook into an Obsidian vault

```bash
nblm2obsidian import "https://notebooklm.google.com/notebook/abc123" --vault ~/Obsidian/MyVault
```

### Import into a subfolder

```bash
nblm2obsidian import "https://notebooklm.google.com/notebook/abc123" --vault ~/Obsidian/MyVault --folder "Research/NotebookLM"
```

### Export to a directory (not necessarily a vault)

```bash
nblm2obsidian import "https://notebooklm.google.com/notebook/abc123" --output ./exports
```

### Inspect what's publicly accessible before downloading

```bash
nblm2obsidian inspect "https://notebooklm.google.com/notebook/abc123"
```

### List sources in a notebook

```bash
nblm2obsidian sources "https://notebooklm.google.com/notebook/abc123"
```

### Dry run (preview without writing)

```bash
nblm2obsidian import "https://notebooklm.google.com/notebook/abc123" --vault ~/Obsidian/MyVault --dry-run
```

### Force overwrite existing files

```bash
nblm2obsidian import "https://notebooklm.google.com/notebook/abc123" --vault ~/Obsidian/MyVault --force
```

### JSON output for scripting

```bash
nblm2obsidian import "https://notebooklm.google.com/notebook/abc123" --vault ~/Obsidian/MyVault --json
```

## Commands

| Command | Description |
|---------|-------------|
| `import` | Import a notebook into a vault or directory |
| `export` | Alias for `import` |
| `inspect` | Show what's publicly accessible without downloading |
| `sources` | List all sources in a notebook |

## Options

| Option | Description |
|--------|-------------|
| `--vault PATH` | Path to Obsidian vault |
| `--output PATH` | Output directory (alternative to --vault) |
| `--folder NAME` | Subfolder name in vault/output |
| `--force` | Overwrite existing files |
| `--dry-run` | Show what would be done without writing |
| `--json` | Output result as JSON |
| `--verbose` | Verbose output |

## Output Structure

```
<output>/
├── Notebook.md           # Main notebook index with metadata and wikilinks
├── Sources/
│   ├── 01 - Source Name.md
│   ├── 02 - Another Source.md
│   └── ...
├── Notes/
│   ├── Summary.md
│   ├── FAQ.md
│   └── ...
└── Assets/
    └── ...
```

## Frontmatter

Every Markdown file includes YAML frontmatter for Obsidian compatibility:

```yaml
---
source: notebooklm
notebook: "Notebook Name"
type: source
source_id: "src123"
source_type: url
source_title: "Source Name"
source_url: "https://example.com"
summary: "Source summary"
imported_at: "2024-01-15T10:30:00"
---
```

## What Can Be Extracted

From a **publicly shared** NotebookLM notebook (shared with "Anyone with the link"), the following may be accessible:

| Content | Availability |
|---------|--------------|
| Notebook metadata (title, description) | ✅ Usually |
| Source list (titles, types, URLs) | ✅ Usually |
| Full source text (for web pages, PDFs, text) | ⚠️ Sometimes (depends on source type and permissions) |
| Source summaries | ✅ Usually |
| User notes | ⚠️ Sometimes |
| Generated artifacts (FAQ, Study Guide, Briefing Doc, etc.) | ⚠️ Sometimes |
| Audio/Video artifacts | ❌ Not accessible (require authentication) |
| Chat history | ❌ Not accessible (private) |
| Private sources (Google Drive docs not shared) | ❌ Not accessible |

**Key limitations:**
- Only content exposed by the public share URL is accessible
- No authentication bypass — private notebooks cannot be accessed
- Google Drive sources only work if the Drive file is also publicly shared
- YouTube sources show metadata but not transcripts
- Audio overviews and video generation require authentication
- Some generated artifacts may not be exposed publicly

If a notebook is not publicly shared, you'll see a clear error message.

## URL Formats Supported

- `https://notebooklm.google.com/notebook/<notebook-id>`
- `https://notebook.google.com/notebook/<notebook-id>`
- `https://notebooklm.google.com/share/<notebook-id>`
- `https://notebook.google.com/share/<notebook-id>`

## How It Works

1. Parses the notebook ID from the share URL
2. Fetches the public notebook page to verify accessibility
3. Uses NotebookLM's internal batchexecute RPC API (unauthenticated) to extract:
   - Notebook metadata
   - Source list and content
   - Notes and generated artifacts
4. Converts everything to Obsidian-compatible Markdown with wikilinks
5. Writes to the specified vault or directory

## Idempotency

Imports are idempotent — running the same import multiple times produces identical output. Filenames are stable (based on source order and title).

## Safety & Ethics

- **Only accesses publicly shared content** — no authentication, no cookies, no login
- **Respects access controls** — private notebooks are rejected with clear errors
- **No credential storage** — nothing sensitive is ever saved
- **No rate limit evasion** — respects server responses

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy src/nblm2obsidian
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Disclaimer

This tool uses undocumented Google NotebookLM APIs that may change without notice. It only accesses content that is already publicly shared by the notebook owner. This is not an official Google product.