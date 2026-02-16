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
| `--threads N` | Number of threads to use for parallel processing. Default: `0` (auto-detect based on CPU count). |
| `--no-parallel` | Force sequential processing (single-threaded). |
| `--dry-run` | Simulation mode. Shows what *would* change without modifying files. |
| `--verbose` | Enable verbose logging and progress output. |
| `--backup DIR` | Create backups of original files in `DIR` before modifying. |
| `--delete-backups` | Delete backup files if operation is successful (default: kept). |
| `--force` | Force operations (e.g. overwrite existing backups). |
| `--json-report FILE` | Write a detailed processing report to a JSON file. |
| `--delimiter CHAR` | Delimiter for splitting multi-value fields (default: `;`). |
| `--schema SCHEMA` | Metadata schema: `canonical`, `extended` (default), or `raw`. |
| `--namespace NS` | Namespace for custom MP4 fields (env: `MUDIO_NAMESPACE`). Default: `com.apple.iTunes`. |

---

## Operations

Select an operation using `--operation NAME`.

### `write`
Writes specific metadata fields using a convenient syntax. This is the primary operation for assigning values.
*   **Use Case**: Precision editing of standard tags (dates, track numbers) or batch assignment of arbitrary fields.
*   **Requires**: `--fields` and `--value`.
*   **Arguments**:
    *   `--fields LIST`: Comma-separated list of fields to set (e.g. `album`, `date`, `track`).
    *   `--value VAL`: The value to assign to the specified fields.
*   **Multi-value**: Use `--delimiter` to split values (e.g. `mudio . --operation write --fields genre --value "Rock|Pop" --delimiter "|"`)
*   **Example**: `mudio . --operation write --fields track --value "1"`

### `print`
Prints the metadata of the files to the console in a readable format.
*   **Options**:
    *   `--schema SCHEMA`: Metadata schema to use. Choices:
        - `canonical`: Standard fields only.
        - `extended`: Standard + custom fields (default).
        - `raw`: Raw tag keys (e.g. TIT2).
*   **Behavior**: Long fields (>150 characters) are truncated with `...`.
*   **Requires**: None.

### `delete`
Removes the specified fields entirely from the file (deletes the key).
*   **Requires**: `--fields`.
*   **Example**: `mudio . --operation delete --fields comment,lyrics`

### `clear`
Writes the specified fields to an empty value (e.g. empty string), without removing the key (if format supports empty tags).
*   **Requires**: `--fields`.
*   **Use Case**: When you want to blank out a field but keep the tag present (rare, usually `delete` is preferred).
*   **Note**: Behavior of empty values varies by format. ID3 tags may store empty frames; Vorbis comments typically omit empty values.

### `append`
Appends a value to the existing field.
*   **Behavior**:
    *   **Single-valued fields** (e.g. title): Appends text to the string **as-is**.
        *   Example: `--value "[Remix]"` -> "Title[Remix]" (No space).
        *   To add space: `--value " [Remix]"` -> "Title [Remix]".
    *   **Multi-valued fields** (e.g. artist): Adds a new entry (e.g. ["Artist A"] -> ["Artist A", "New Artist"]).
*   **Requires**: `--fields`, `--value`.

### `prefix`
Prepends a value to the existing field.
*   **Behavior**:
    *   **Single-valued**: "Title" -> "Prefix Title"
    *   **Multi-valued**: "Artist A" -> "Prefix Artist A" (Applied to ALL values).
*   **Requires**: `--fields`, `--value`.

### `enlist`
Adds a value to a multi-valued field only if it does not already exist.
*   **Requires**: `--fields`, `--value`.
*   **Example**: `mudio . --operation enlist --fields genre --value "Pop"`

### `delist`
Removes specific value(s) from a multi-valued field.
*   **Requires**: `--fields`, `--value`.
*   **Example**: `mudio . --operation delist --fields genre --value "Rock"`


### `find-replace`
Search and replace text within tags.
*   **Requires**: `--fields`, `--find`, `--replace`.
*   **Options**:
    *   `--regex`: Treat the `--find` pattern as a Regular Expression.
*   **Warning**: If the replacement result contains the delimiter (default `;`), it will be split into multiple values for multi-valued fields.
    *   Example: replacing "and" with ";" in "A and B" results in ["A ", " B"].
*   **Example**: `mudio . --operation find-replace --fields title --find "feat." --replace "ft."`

### `purge`
**DANGER**: Removes ALL metadata tags from the files, leaving them clean.
*   **Requires**: None (implicitly targets all fields).

---

## Fields

Select which fields to operate on using the following arguments:

*   `--fields LIST`: Comma-separated list of specific fields (e.g. `title,artist`).


These are the canonical field names supported across all audio formats.

| Field | Description |
| :--- | :--- |
| `title` | Track title |
| `artist` | Track artist (Multi-value) |
| `album` | Album name |
| `albumartist` | Album artist (Multi-value) |
| `genre` | Genre (Multi-value) |
| `date` | Release date/year |
| `comment` | Comments |
| `track` | Track number |
| `totaltracks` | Total tracks count |
| `disc` | Disc number |
| `totaldiscs` | Total discs count |
| `composer` | Composer (Multi-value) |
| `performer` | Performer (Multi-value) |

### Custom Fields

You are not limited to the canonical fields above. You can read and write **any** custom field supported by the underlying format.

*   **Usage**: Simply use the field name in `--fields` (e.g. `--fields MY_CUSTOM_TAG`).
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
*   `--filter artist="The Beatles"`: Matches tracks by The Beatles.
*   `--filter "title=Love"`: Matches tracks with "Love" in the title.
*   `--filter-regex --filter "date=^199."`: Matches tracks from the 90s.

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

### Copy Metadata
To copy specific metadata from one batch of files to another structure (implied manual process as `mudio` operates in-place):
Currently `mudio` focuses on in-place modification. To copy tags, you would typically read valid tags from one source and apply them to another script-wise.

### Fix "Various Artists" Compilations
To ensure compilations are grouped correctly:

```bash
# Set Album Artist to "Various Artists" and compilation flag (if supported by format)
mudio . --operation write --fields albumartist --value "Various Artists" --filter "compilation=1"
```

### Normalize Messy Metadata
Clean up inconsistent capitalization:

```bash
# This requires a script using `mudio` library as CLI only supports fixed transformations
```
Actually, CLI supports regex find-replace:

```bash
# Replace underscores with spaces in titles
mudio . --operation find-replace --fields title --find "_" --replace " "
```

## Version Compatibility

*   **Python**: Requires Python 3.8 or newer.
*   **Dependencies**: Relies on `mutagen` for low-level file handling.
*   **Formats**: ID3v2.3 and ID3v2.4 are supported for MP3. Vorbis Comments for FLAC/Ogg.

## Performance Considerations

*   **Parallel Processing**: Enabled by default. Uses one thread per CPU core.
    *   **Recommendation**: Use `--no-parallel` when processing files on a network share (NAS) or purely mechanical HDD to avoid thrashing.
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
