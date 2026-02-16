# mudio

**mudio** is a powerful, friendly command-line music metadata editor and Python library. It provides a unified API for handling metadata across MP3, FLAC, M4A, and more, making batch processing and automation simple and safe.

-   **For full command details, see the [CLI Reference](docs/cli_reference.md).**
-   **For code API details, see the [API Reference](docs/api_reference.md).**

## Features

-   **Unified API**: Write code once, run it on MP3, FLAC, M4A, WAV, OGG, OPUS, and WavPack.
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

`mudio` is designed for efficient batch operations.

### Basic Commands

```bash
# View metadata (truncated if long)
mudio song.mp3 --operation print

# Set Album
mudio *.mp3 --operation write --fields album --value "New Album"

# Overwrite Title
mudio song.flac --operation write --fields title --value "My Song"
```

### Advanced Batch Operations

```bash
# Regex Find & Replace (Fix features)
# Changes "feat." -> "ft." in title and artist
mudio /music --recursive \
  --operation find-replace --find "feat\." --replace "ft." --regex \
  --fields title,artist

# Append to Comment
mudio *.m4a --operation append --fields comment --value " [Remastered]"

# Filtered Processing
# Only add "Rock" genre to tracks by "Led Zeppelin"
mudio /library --recursive \
  --filter "artist=Led Zeppelin" \
  --operation write --fields genre --value "Rock"
```

### Safety Features

```bash
# Dry Run (See what would happen without modifying files)
mudio *.mp3 --operation write --fields album --value "Test" --dry-run

# Create Backups (Kept by default in ./backups/)
mudio *.flac --operation clear --fields comment --backup ./backups

# Delete backups after successful operation (to save space)
mudio *.mp3 --operation write --fields album --value "New" --backup ./backups --delete-backups
```

## Python Library Usage

`mudio` provides a Pythonic wrapper around `mutagen` for scripts and tools.

```python
from mudio import SimpleMusic

# Reading metadata (extended mode by default - includes custom fields)
with SimpleMusic("song.flac") as sm:
    fields = sm.read_fields()  # Default: schema='extended'
    print(fields)
    # {'artist': ['The Band'], 'title': ['The Song'], ...}

# Read with different schemas
with SimpleMusic("song.mp3") as sm:
    canonical = sm.read_fields(schema='canonical')  # Only standard fields
    raw = sm.read_fields(schema='raw')  # Format-specific keys (TIT2, TPE1, etc.)
    extended = sm.read_fields(schema='extended')  # Standard + custom fields

# Writing
with SimpleMusic("song.mp3") as sm:
    sm.write_fields({
        'title': ['New Title'],
        'genre': ['Pop', 'Rock']  # Multi-value support
    })

# Error handling is managed by the context manager
```

### Environment Variables

You can configure `mudio`'s default behavior using environment variables:

- **`MUDIO_SCHEMA`**: Set default schema for reading metadata (`canonical`, `extended`, or `raw`). Default: `extended`.
- **`MUDIO_MAX_WORKERS`**: Default thread count for parallel processing.
- **`MUDIO_BACKUP_DIR`**: Default backup location.
- **`MUDIO_VERBOSE`**: Default verbosity (`0` or `1`).
- **`MUDIO_NAMESPACE`**: Namespace for custom MP4/M4A fields (default: `com.apple.iTunes`). Setting this to something else (e.g. `org.myproject`) allows isolating your custom tags.

```bash
# Example: Use extended schema by default (canonical + custom fields)
export MUDIO_SCHEMA=extended
python your_script.py
```

## Behavior Notes

### Canonical Field Handling (All Formats)

`mudio` normalizes metadata to a **case-insensitive canonical schema** and applies consistent frame/value rules across formats.

#### Reading

* **Canonical keys**: Raw tags that differ only by case or alias are merged into one canonical field (e.g., `GENRE`, `genre` → `genre`; ReplayGain variants collapse).
* **Frame-level deduplication**: If multiple frames for a canonical field contain the *same ordered list of values* (after normalization), only the first is kept.
* **Intra-frame duplicates**: Duplicates *within* a single frame are preserved.
* **Distinct frames**: Frames with different value sequences are preserved and flattened in first-seen order.
* **Unknown fields**: Unrecognized keys are normalized (lowercase) and preserved.
* **Key Sanitization**:
    * **Reading**: Keys are sanitized to **small snake case** (`[a-z0-9_]`). Non-alphanumeric characters are replaced with `_`.
    * **Writing**: Custom keys are sanitized to **caps snake case** (`[A-Z0-9_]`). Non-alphanumeric characters are replaced with `_`.
    * **Alternative Casing**: `mudio` drops alternative casing for custom fields to prevent duplicates (e.g., `MyField` and `myfield` are treated as the same field).

#### Writing

* **Canonical-only state**: Input keys are normalized and merged before write.
* **Single emission per field**: Each canonical field is written once via the format-specific emitter (e.g., ID3 frames, Vorbis comments, MP4 atoms). Aliases are not written.
* **Value collapse**: All values for a canonical field are emitted according to the target format’s conventions (including required frames/atoms), without duplicating equivalent aliases.
* **Deterministic output**: Ordering reflects first occurrence after merge and deduplication.

This ensures consistent behavior across file types while preventing casing/alias duplicates.

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