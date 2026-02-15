# mudio API Reference

This document provides a detailed reference for the internal Python API of `mudio`. It is useful for developers who want to use `mudio` as a library in their own scripts or applications.

## Core (`mudio.core`)

The core module handles the abstraction layer for reading and writing metadata across different audio formats.

### `SimpleMusic`

The primary interface for interacting with audio files. It automatically handles format detection (MP3, FLAC, M4A, etc.) and provides a unified dictionary-based API for tags.

```python
from mudio.core import SimpleMusic, managed_simple_music

# Recommended: Use context manager to ensure files are closed safely
with managed_simple_music("path/to/song.mp3") as sm:
    fields = sm.read_fields()
    sm.write_fields({"title": ["New Title"]})
```

#### Class Reference

**`SimpleMusic(path: Union[str, Path])`**
*   **path**: The file path to open.
*   **Raises**:
    *   `FormatError`: If the file format is unsupported or corrupted.
    *   `RuntimeError`: If the file does not exist.

**`SimpleMusic.read_fields(mode: str = 'canonical') -> Dict[str, List[str]]`**
Reads metadata fields from the file.
*   **mode**:
    *   `'canonical'` (default): Returns a standardized dictionary using `mudio`'s canonical field names (e.g. `title`, `artist`, `date`).
    *   `'raw'`: Returns the raw mapping of tags as they appear in the file (e.g. `TIT2` for MP3 title, `©nam` for MP4).
    *   `'extended'`: Returns all canonical fields **plus** any other fields found in the file that didn't map to a canonical one (e.g. `acoustid_id`, custom TXXX frames).
*   **Returns**: A dictionary where keys are field names and values are a **list of strings**.
    *   **Note**: `mudio` uses a unified list-based structure for I/O consistency. However, fields have semantic cardinality:
        *   **Single-valued** (e.g. `title`, `date`, `track`): Logic operations will typically use only the first value.
        *   **Multi-valued** (e.g. `artist`, `genre`): Logic operations maintain the full list.
    *   See `mudio.operations` for field definitions.

**`SimpleMusic.write_fields(fields: Dict[str, List[str]])`**
Writes metadata to the file.
*   **Raises**:
    *   `PermissionError`: If the file is not writable.
    *   `RuntimeError`: If no file is loaded.
*   **fields**: A dictionary of fields to write. Keys can be canonical field names (like `title`, `artist`) or **any custom string**.
*   **Behavior**:
    *   **Custom Fields**: Arbitrary keys are written as format-specific custom tags (TXXX for ID3, comments for Vorbis, freeform atoms for MP4).
    *   Existing fields not in the input dictionary are **preserved**. (To delete a field, use `delete_fields` or pass an empty list `[]` as the value).
    *   This method transparently handles format-specific details.

**`SimpleMusic.delete_fields(fields: List[str])`**
Deletes the specified fields from the file.
*   **fields**: List of canonical or custom field names to remove.

**`SimpleMusic.close()`**
Closes the underlying file handle. Automatically called when using the context manager.

**`SimpleMusic.parse_list_string(s: Optional[str], delimiter: str = ';') -> List[str]`**
Static utility method to split a string into a list based on a delimiter.
*   **s**: The string to parse.
*   **delimiter**: The delimiter character (default `;`).
*   **Returns**: List of strings, stripped of whitespace.

---

## Processor (`mudio.processor`)

The processor module handles high-level batch processing, including parallel execution, file validation, backups, and error reporting.

### Batch Processing Functions

**`process_files(files: Iterable[Path], ops: FieldOperationsType, targeted_fields: List[str], ...)`**
The main entry point for processing a batch of files. It automatically chooses between sequential and parallel processing based on the number of files and configuration.

*   **files**: An iterable of `Path` objects to process.
*   **ops**: A dictionary mapping field names to operation functions (see `mudio.operations`).
*   **targeted_fields**: A list of fields being modified (used for verification).
*   **max_workers** (int): Number of threads to use (default: CPU count).
*   **dry_run** (bool): If `True`, calculates changes but does not write to disk.
*   **backup_dir** (str): Path to directory for storing backups.
*   **force** (bool): If `True`, overwrites existing backups/files where necessary.
*   **verbose** (bool): Enables progress printing.
*   **filters** (List): A list of filters to apply before processing.

**`process_file(path: str, ops: FieldOperationsType, targeted_fields: List[str], ...)`**
Processes a single file.
1.  Validates file (permissions, format).
2.  Applies filters.
3.  Computes new tag values using `ops`.
4.  Creates backup (if requested).
5.  Writes changes.
6.  Verifies changes by re-reading the file.

### Validation

**`validate_file(path: Path) -> Tuple[bool, str]`**
Performs comprehensive checks:
*   Existence and file type.
*   Read/Write permissions.
*   File size (checks for empty files or files exceeding limits).
*   Format validity (can `mutagen` parse it?).

---

## Operations (`mudio.operations`)

This module defines how field values are transformed. It provides the logic for "Set", "Append", "Regex Replace", etc.

### `FieldOperations` Class

**`FieldOperations.normalize_values(field_name: str, values: List[str]) -> List[str]`**
Ensures field values are consistent.
*   **Multi-valued fields** (artist, genre, etc.): Deduplicates values while preserving order (case-insensitive).
*   **Single-valued fields** (title, date, track): Takes only the first value.

### Operation Factories

These functions return a callable `op(values: List[str]) -> List[str]` that transforms existing values into new ones.

*   **`op_overwrite(field, value, delimiter=';')`**: Replaces existing values. Splits strings on `delimiter` for multi-valued fields.
*   **`op_append(field, value, delimiter=';')`**:
    *   Single-valued: Appends string.
    *   Multi-valued: Adds new item(s) (split by `delimiter`) if not present.
*   **`op_prefix(field, value)`**: Prepends string to values.
*   **`op_find_replace(field, find, replace, regex=False, delimiter=';')`**: Performs string substitution. If result contains `delimiter`, splits into multiple values (for multi-valued fields).
*   **`op_enlist(field, value, delimiter=';')`**: Enlists value(s) (split by `delimiter`) to a multi-valued field list only if it doesn't already exist.
*   **`op_delist(field, value, delimiter=';')`**: Delists (removes) specific value(s) from a multi-valued field.
*   **`op_clear(field)`**: Returns `[""]` (empty string), setting the tag to empty but keeping the key.
*   **`op_delete(field)`**: Returns `[]` (empty list), removing the tag key entirely.

    > **Note**: Behavior of empty values varies by format. ID3 tags may store empty frames; Vorbis comments typically omit empty values.

---

## Utilities (`mudio.utils`)

**`Config`**
Global configuration settings, loaded from environment variables.
*   `MUDIO_MAX_WORKERS`: Default thread count.
*   `MUDIO_BACKUP_DIR`: Default backup location.
*   `MUDIO_VERBOSE`: Default verbosity.

**`get_file_hash(path: Path)`**
Calculates SHA-256 hash of a file for verification.

---

## Types and Errors

### Error Hierarchy

The API defines a hierarchy of exceptions for robust error handling:

```python
class MudioError(Exception): ...
class ValidationError(MudioError): ...      # Invalid arguments or state
class FormatError(MudioError): ...          # File format issues
class PermissionError(MudioError): ...      # Filesystem permission issues
class VerificationError(MudioError): ...    # Post-write verification failed
```

### Type Definitions

Common type aliases used in function signatures:

```python
FieldOperationsType = Dict[str, Callable[[List[str]], List[str]]]
FieldValuesType = Dict[str, List[str]]
FilterType = Tuple[str, str, bool]
```

*   **`FieldOperationsType`**: Maps target field names to transformation functions.
*   **`FieldValuesType`**: Standard dictionary for metadata (Field -> List of Strings).
