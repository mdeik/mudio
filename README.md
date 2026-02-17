# mudio

**mudio** is a powerful, friendly command-line music metadata editor and Python library. It provides a unified API for handling metadata across MP3, FLAC, M4A, and more, making batch processing and automation simple and safe.

-   **For full command details, see the [CLI Reference](docs/cli_reference.md).**
-   **For code API details, see the [API Reference](docs/api_reference.md).**

## Features

-   **Unified API**: Write code once, run it on MP3, FLAC, M4A, WAV, OGG, and OPUS.
-   **Batch Processing**: robust CLI for processing thousands of files.
-   **Parallel Execution**: Automatically uses multi-threading for large batches.
-   **Safety First**: Built-in **backup** system, **dry-run** mode, and careful validation.
-   **Powerful Operations**:
    -   **Find & Replace**: Regex-supported search and replace in tags.
    -   **Mass Edits**: Set, overwrite, append, prefix, or clear tags.
    -   **Filtering**: Apply changes only to files matching specific criteria (e.g. `artist="The Beatles"`).

## Supported Formats

-   **MP3** (`.mp3`) - ID3v2.3/v2.4
-   **FLAC** (`.flac`) - Vorbis Comments
-   **M4A / MP4** (`.m4a`, `.mp4`) - MP4 Tags
-   **Ogg Vorbis** (`.ogg`)
-   **Opus** (`.opus`)
-   **WAV** (`.wav`)

## Installation

```bash
pip install mudio
```

## CLI Usage

### Simple: Update metadata for files
```bash
# Set album name for all MP3 files
mudio *.mp3 --operation write --fields album --value "Greatest Hits"
```

### Advanced: Conditional batch processing with backup
```bash
# Fix title formatting for 1990s Rock tracks, with backups and regex
mudio /music --recursive --backup ./backups \
  --filter-regex --filter "date=^199" --filter "genre=Rock" \
  --operation find-replace --fields title --find "\s+" --replace " " --regex
```

> **💡 Tip**: Use `--dry-run` to preview changes before applying them.

## Python Library Usage

### Simple: Read and write metadata
```python
from mudio.processor import process_file
from mudio.operations import write

# Update a single file with automatic verification
result = process_file(
    "song.mp3",
    ops=[write('artist', 'The Beatles')]
)
print(f"Success: {result['passed']}")  # True if successful
```

### Advanced: Batch processing with operations
```python
from mudio.processor import process_files
from mudio.operations import write, enlist, find_replace
from pathlib import Path

# Process multiple files with complex operations
results = process_files(
    Path('music').rglob('*.flac'),
    ops=[
        enlist('genre', 'Rock;Classic'),           # Add genres if not present
        find_replace('title', r'\s+', ' ', regex=True),  # Normalize whitespace
        write('albumartist', 'Various Artists')
    ],
    filters=[('date', '^199', True)],  # Only 1990s tracks (regex)
    backup_dir='./backups',
    max_workers=4
)

print(f"Updated {sum(r['passed'] for r in results)} files")
```

### Environment Variables

You can configure `mudio`'s default behavior using environment variables:

- **`MUDIO_SCHEMA`**: Set default schema for reading metadata (`canonical`, `extended`, or `raw`). Default: `extended`.
- **`MUDIO_MAX_WORKERS`**: Default thread count for parallel processing.
- **`MUDIO_VERBOSE`**: Default verbosity (`0` or `1`).
- **`MUDIO_NAMESPACE`**: Namespace for custom MP4/M4A fields (default: `com.apple.iTunes`). Setting this to something else (e.g. `org.myproject`) allows isolating your custom tags.

```bash
# Example: Use extended schema by default (canonical + custom fields)
export MUDIO_SCHEMA=extended
python your_script.py
```

## Behavior Notes

### Field Handling (All Formats)

`mudio` normalizes metadata to a **case-insensitive canonical schema** and applies consistent rules across formats.

#### Reading

* **Canonical fields**: Tags are normalized to standard names (e.g., `TIT2` → `title`).
* **Strict whitespace handling**: All values are stripped of leading/trailing whitespace. Empty or whitespace-only values are dropped.
* **Empty field representation**: If a field exists but all values are empty after stripping, it returns `['']` (a list with a single empty string).
* **Deduplication**: All field values are deduplicated case-insensitively, and identical frames are merged.

#### Writing

* **Canonical fields**: Written to format-specific native tags.
* **Strict whitespace handling**: Values are stripped; empty strings are dropped from lists.
* **Smart empty**: A single `['']` (e.g. from `clear()`) is preserved and written, allowing explicit "empty" tags.
* **Deletion**: Writing `[]` (empty list) deletes the field entirely.
* **All fields are multi-valued**: All unique values are written.
* **Custom fields**: Keys are sanitized to caps snake case (e.g., `MY_CUSTOM_FIELD`).

**Example - Custom Field Writing:**
```python
# Writing with various custom key formats
sm.write_fields({
    'my-custom-field': ['value1'],  # Written as: MY_CUSTOM_FIELD
    'AnotherField': ['value2'],      # Written as: ANOTHERFIELD
})
```

### Canonical Fields

The following canonical fields are recognized by `mudio` across all audio formats:

`title` · `artist` · `album` · `albumartist` · `genre` · `comment` · `composer` · `performer` · `date` · `track` · `totaltracks` · `disc` · `totaldiscs`

**Note**: All field names are case-insensitive. Common variations (e.g., `album_artist`, `tracknumber`, `discnumber`) are automatically mapped to their canonical form.

## Comparison with Alternatives

### vs. **Mutagen**
-   **Mutagen** is the low-level library that `mudio` uses. It is powerful but requires learning different APIs for ID3, Vorbis, and MP4 tags.
-   **mudio** abstracts these differences. Use `mudio` if you want a simple, unified API (e.g. `sm.write_fields({'title': ...})` works on everything). Use `mutagen` if you need byte-level control or support for obscure frame types.

### vs. **music_tag**
-   **music_tag** is a library primarily for Python scripts, offering a dictionary-like interface. It is excellent for simple script usage.
-   **mudio** offers similar library features but includes a **robust CLI** for batch processing, filtering, and safety operations (backups, dry-runs) out of the box.

### vs. **Beets**
-   **Beets** is a complete library manager with a centralized database, autotagger, and plugin system. It implies a workflow where it "owns" your library.
-   **mudio** is a stateless tool. It modifies files directly without a database. Use `mudio` for quick fixes, batch scripting, or if you prefer managing your file structure manually.

### vs. **Picard**
-   **MusicBrainz Picard** is a GUI application focused on matching files to the MusicBrainz database.
-   **mudio** is a CLI/Library tool. It's better for automation, headless servers, or mass-editing tags based on patterns rather than database matching.

### vs. **EyeD3**
-   **EyeD3** is excellent but specific to MP3/ID3.
-   **mudio** supports FLAC, M4A, OGG, and more with the same commands.

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest
```