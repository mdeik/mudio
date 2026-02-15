# mudio

**mudio** is a powerful, friendly command-line music metadata editor and Python library. It provides a unified API for handling metadata across MP3, FLAC, M4A, and more, making batch processing and automation simple and safe.

## Features

-   **Unified API**: Write code once, run it on MP3, FLAC, M4A, WAV, OGG, OPUS, WMA, and WavPack.
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
-   **Windows Media Audio** (`.wma`)
-   **WavPack** (`.wv`)

## Installation

```bash
pip install mudio
```

## CLI Usage

`mudio` is designed for efficient batch operations.

### Basic Commands

```bash
# View metadata
mudio song.mp3 --mode view

# Set Album and Date
mudio *.mp3 --mode set --album "New Album" --date "2024"

# View metadata (truncated if long)
mudio song.mp3 --mode print

# Overwrite Title
mudio song.flac --mode overwrite --fields title --value "My Song"
```

### Advanced Batch Operations

```bash
# Regex Find & Replace (Fix features)
# Changes "feat." -> "ft." in title and artist
mudio /music --recursive \
  --mode find-replace --find "feat\." --replace "ft." --regex \
  --fields title,artist

For full command details, see the [CLI Reference](docs/cli_reference.md).
For code API details, see the [API Reference](docs/api_reference.md).

# Append to Comment
mudio *.m4a --mode append --fields comment --value " [Remastered]"

# Filtered Processing
# Only add "Rock" genre to tracks by "Led Zeppelin"
mudio /library --recursive \
  --filter "artist=Led Zeppelin" \
  --mode overwrite --fields genre --value "Rock"
```

### Safety Features

```bash
# Dry Run (See what would happen without modifying files)
mudio *.mp3 --mode set --album "Test" --dry-run

# Create Backups (Saved to ./backups/)
mudio *.flac --mode clear --fields comment --backup ./backups
```

## Python Library Usage

`mudio` provides a Pythonic wrapper around `mutagen` for scripts and tools.

```python
from mudio import SimpleMusic

# Reading
with SimpleMusic("song.flac") as sm:
    print(sm.read_fields())
    # {'artist': ['The Band'], 'title': ['The Song'], ...}

# Writing
with SimpleMusic("song.mp3") as sm:
    sm.write_fields({
        'title': ['New Title'],
        'genre': ['Pop', 'Rock']  # Multi-value support
    })

# Error handling is managed by the context manager
```

## Comparison with Alternatives

### vs. **Mutagen**
-   **Mutagen** is the low-level library that `mudio` uses. It is powerful but requires learning different APIs for ID3, Vorbis, and MP4 tags.
-   **mudio** abstracts these differences. Use `mudio` if you want a simple, unified API (e.g. `sm.write_fields({'title': ...})` works on everything). Use `mutagen` if you need byte-level control or support for obscure frame types.

### vs. **Beets**
-   **Beets** is a complete library manager with a centralized database, autotagger, and plugin system. It implies a workflow where it "owns" your library.
-   **mudio** is a stateless tool. It modifies files directly without a database. Use `mudio` for quick fixes, batch scripting, or if you prefer managing your file structure manually.

### vs. **Picard**
-   **MusicBrainz Picard** is a GUI application focused on matching files to the MusicBrainz database.
-   **mudio** is a CLI/Library tool. It's better for automation, headless servers, or mass-editing tags based on patterns rather than database matching.

### vs. **music_tag**
-   **music_tag** is a library primarily for Python scripts, offering a dictionary-like interface. It is excellent for simple script usage.
-   **mudio** offers similar library features but includes a **robust CLI** for batch processing, filtering, and safety operations (backups, dry-runs) out of the box.

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