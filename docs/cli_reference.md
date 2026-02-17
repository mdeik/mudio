# mudio CLI Reference Manual

This document provides a comprehensive guide to all commands, options, and fields supported by `mudio`.

## Synopsis

```bash
mudio [PATH] [OPTIONS]
```

**PATH**: The file or directory to process. Defaults to current directory (`.`) if omitted.

## Global Options

These options apply to all operations.

| Option | Description |
| :--- | :--- |
| `--recursive` | Recursively search for audio files in subdirectories. |
| `--ext LIST` | Comma-separated list of extensions to process (e.g. `mp3,flac`). Defaults to all supported types. |
| `--threads N` | Number of threads to use for parallel processing. Default: `0` (auto-detect based on CPU count). Set to `1` for sequential processing. |
| `--dry-run` | Simulation mode. Shows what *would* change without modifying files. |
| `--verbose` | Enable verbose logging and progress output. |
| `--backup DIR` | Create backups of original files in `DIR` before modifying. |
| `--delete-backups` | Delete backup files if operation is successful (default: kept). |
| `--force` | Force operations (e.g. overwrite existing backups). |
| `--json-report FILE` | Write a detailed processing report to a JSON file. |
| `--delimiter CHAR(S)` | Delimiter(s) for splitting multi-value fields. Default: `;`. Supports multiple: `--delimiter ";,/"` splits on any. |
| `--schema SCHEMA` | Metadata schema: `canonical`, `extended`, or `raw`. Default: `extended` (or configured via `MUDIO_SCHEMA`). |
| `--namespace NS` | Namespace for custom MP4 fields (env: `MUDIO_NAMESPACE`). Default: `com.apple.iTunes`. |

---

## Operations

Select an operation using `--operation NAME`.

| Operation | Purpose | Required Args | Example |
|-----------|---------|---------------|----------|
| **`print`** | Display metadata to console | None | `mudio song.mp3 --operation print` |
| **`write`** | Set field value(s) | `--fields`, `--value` | `mudio . --operation write --fields artist --value "Beatles"` |
| **`append`** | Add to existing value | `--fields`, `--value` | `mudio . --operation append --fields title --value " (Remix)"` |
| **`prefix`** | Prepend to value(s) | `--fields`, `--value` | `mudio . --operation prefix --fields title --value "[2024] "` |
| **`find-replace`** | Find/replace text | `--fields`, `--find`, `--replace` | `mudio . --operation find-replace --fields title --find "_" --replace " "` |
| **`enlist`** | Add to multi-valued field (if not present) | `--fields`, `--value` | `mudio . --operation enlist --fields genre --value "Rock"` |
| **`delist`** | Remove from multi-valued field | `--fields`, `--value` | `mudio . --operation delist --fields genre --value "Pop"` |
| **`clear`** | Set field to empty string | `--fields` | `mudio . --operation clear --fields comment` |
| **`delete`** | Remove field entirely | `--fields` | `mudio . --operation delete --fields lyrics` |
| **`purge`** | ⚠️ Remove ALL metadata | None | `mudio . --operation purge --dry-run` |

### Operation Details

**`print`**
- Schema options via `--schema`: `canonical` (standard fields), `extended` (+ custom fields), `raw` (format-specific keys)
- Long fields (>150 chars) are truncated with `...`

**`write`**
- Multi-value: Use `--delimiter` to split (e.g., `--value "Rock;Pop"` creates two genre entries)
- Primary operation for setting tags

**`append` / `prefix`**
- Appends/prepends text to all values in the field
- Note: `append` adds text as-is (no space added automatically)

**`find-replace`**
- Add `--regex` flag to use regex patterns
- Example: `--find "^Track" --replace "Song" --regex`

**`enlist` / `delist`**
- Case-insensitive matching
- Adds/removes values from the field's value list

---

## Fields

Select which fields to operate on using the following arguments:

*   `--fields LIST`: Comma-separated list of specific fields (e.g. `title,artist`).


These are the canonical field names supported across all audio formats.

| Field | Description |
| :--- | :--- |
| `title` | Track title |
| `artist` | Track artist |
| `album` | Album name |
| `albumartist` | Album artist |
| `genre` | Genre |
| `date` | Release date/year |
| `comment` | Comments |
| `track` | Track number |
| `totaltracks` | Total tracks count |
| `disc` | Disc number |
| `totaldiscs` | Total discs count |
| `composer` | Composer |
| `performer` | Performer |

### Custom Fields

You are not limited to the canonical fields above. You can read and write **any** custom field supported by the underlying format.

*   **Usage**: Simply use the field name in `--fields` (e.g. `--fields MY_CUSTOM_TAG`).
*   **Multi-Value**: Custom fields are treated as multi-valued, like all other fields.
*   **Storage**:
    *   **MP3 (ID3)**: `TXXX:MY_CUSTOM_TAG`
    *   **FLAC/Vorbis**: `MY_CUSTOM_TAG=Value`
    *   **MP4**: `----:com.apple.iTunes:MY_CUSTOM_TAG` (Namespace is configurable via `MUDIO_NAMESPACE`)

### Key Sanitization

*   **Reading**: Custom keys are read as **small snake case** (e.g., `MY_TAG` -> `my_tag`).
*   **Writing**: Custom keys are written as **caps snake case** (e.g., `my_tag` -> `MY_TAG`).
*   **Deduplication**: Alternative casing is dropped to prevent duplicates.



---

## Filtering

Apply changes only to files that match specific criteria using `--filter`.

**Syntax**: `--filter FIELD=PATTERN`

*   **Case-insensitive**: Matches are case-insensitive by default.
*   **Multiple Filters**: You can provide multiple `--filter` arguments. All must match (AND logic).
*   **Regex**: Add `--filter-regex` to treat patterns as regular expressions.
*   **Quoting & Escaping**:
    *   Enclose argument in quotes if it contains spaces: `--filter "artist=The Beatles"`
    *   To match a literal `=` in the value, use regex mode: `--filter-regex --filter "title=Equation 1\+1=2"` (the first `=` is the separator).
    *   To match a generic pattern with spaces in regex: `--filter-regex --filter "title=.*Love.*"`

**Examples**:
*   `--filter artist="The Beatles"`: Only process files by The Beatles.
*   `--filter "title=Love"`: Only process files with "Love" anywhere in the title.
*   `--filter-regex --filter "date=^199"`: Only process files from the 1990s.

---

## Safety & Backups

### Dry Run
Use `--dry-run` to preview changes. The output will show the "Original" state and the "Planned" state for every file, but no files will be modified.

```bash
mudio . --operation purge --dry-run
```

### Backups
Use `--backup PATH` to save copies of files before they are modified.

*   `mudio` will create a copy of the original file in the specified directory.
*   If the operation succeeds, the backup is **kept by default**.
*   Use `--delete-backups` to automatically delete the backup after a successful operation (to save space).
*   If the operation fails, the backup is **always preserved** regardless of flags.
*   Use `--force` to overwrite existing files (including existing backups).

---

## Supported Formats

*   MP3 (`.mp3`)
*   FLAC (`.flac`)
*   M4A / MP4 (`.m4a`, `.mp4`)
*   Ogg Vorbis (`.ogg`)
*   Opus (`.opus`)
*   WAV (`.wav`) - *ID3 chunks in WAV*

## Common Patterns

### Preview Changes Before Applying
Always use `--dry-run` first to see what will change:
```bash
mudio music/ --operation write --fields albumartist --value "Various Artists" --recursive --dry-run
```

### Set Metadata with Backup
Create backups before modifying files:
```bash
mudio album/ --operation write --fields date --value "2024" --recursive --backup ./backups
```

### Clean Up Title Formatting
```bash
# Remove unwanted text from titles
mudio . --operation find-replace --fields title --find " (Demo)" --replace "" --recursive

# Normalize whitespace with regex
mudio . --operation find-replace --fields title --find "\\s+" --replace " " --regex --recursive
```

### Conditional Updates with Filtering
Only process files matching specific criteria:
```bash
# Update only Beatles songs
mudio music/ --operation enlist --fields genre --value "Rock" \
  --filter "artist=Beatles" --recursive

# Update only 1990s tracks
mudio music/ --operation write --fields decade --value "90s" \
  --filter-regex --filter "date=^199" --recursive
```

### Multi-Value Field Management
```bash
# Add genre without duplicates
mudio . --operation enlist --fields genre --value "Electronic" --recursive

# Remove unwanted artist credit
mudio . --operation delist --fields artist --value "Unknown Artist" --recursive
```

### Parallel Processing Control
```bash
# Use 8 threads for large library
mudio /music --operation write --fields albumartist --value "Various" --threads 8 --recursive

# Sequential processing for network shares
mudio /nas/music --operation enlist --fields genre --value "Jazz" --threads 1 --recursive
```

## Version Compatibility

*   **Python**: Requires Python 3.8 or newer.
*   **Dependencies**: Relies on `mutagen` for low-level file handling.
*   **Formats**: ID3v2.3 and ID3v2.4 are supported for MP3. Vorbis Comments for FLAC/Ogg.

## Performance Considerations

*   **Parallel Processing**: Enabled by default. Uses one thread per CPU core.
    *   **Recommendation**: Use `--threads 1` when processing files on a network share (NAS) or purely mechanical HDD to avoid thrashing.
*   **Memory Usage**: `mudio` processes files in streams where possible, but loading large directories recursively consumes memory proportional to the file count.
*   **Backups**: Creating backups doubles the disk I/O. For maximum speed on strictly safe data, verify backups are off (default is on-demand).

## Error Handling

mudio uses standard exit codes to indicate success or failure:

*   **0**: Success. All files processed successfully (or dry-run completed).
*   **1**: General error (unexpected crash or failure).
*   **2**: Usage error (invalid arguments, missing required options, or configuration error).
*   **3**: No files matched. The operation completed but found no files to process.
*   **4**: Permission denied (system level).
*   **5**: Disk full.
*   **130**: Operation interrupted (Ctrl+C).

Failures are logged to stderr. Use `--json-report` to generate a machine-readable report of which files succeeded and which failed.

### JSON Report Schema

When using `--json-report`, the output file follows this structure:

```json
{
  "version": "1.0",
  "timestamp": "ISO8601 String",
  "summary": {
    "total": 100,
    "success": 95,
    "failed": 5,
    "skipped": 0,
    "backups_created": 5,
    "backups_removed": 95
  },
  "files": [
    {
      "path": "/absolute/path/to/file.mp3",
      "status": "success|error|skipped",
      "changes": {
        "title": {"old": ["Old Title"], "new": ["New Title"]}
      },
      "error": "Error message if failed",
      "backup_path": "/path/to/backup.mp3 (optional)",
      "backup_kept": false
    }
  ]
}
```
