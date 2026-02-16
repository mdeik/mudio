# mudio API Reference

This document provides a detailed reference for the internal Python API of `mudio`. It is useful for developers who want to use `mudio` as a library in their own scripts or applications.

---

## Recommended: Use `mudio.processor`

**For most use cases, you should use the high-level `process_file()` and `process_files()` functions.** These provide:

- ✅ **Automatic backups** and rollback on failure
- ✅ **Verification** to ensure changes were written correctly
- ✅ **Filtering** to target specific files
- ✅ **Parallel processing** for large batches
- ✅ **Comprehensive error handling** and reporting

### Quick Example

```python
from mudio.processor import process_file
from mudio.operations import find_replace, enlist

# Apply operations with automatic backups and verification
result = process_file(
    "song.mp3",
    ops={
        'title': find_replace('title', 'Demo', 'Final'),
        'genre': enlist('genre', 'Rock')
    },
    targeted_fields=['title', 'genre'],
    backup_dir='./backups',
    verify=True
)

# result is a dictionary with detailed information
if result['passed']:
    print(f"✓ Success: {result['changed']}")
else:
    print(f"✗ Failed: {result['error']}")
```

---

## Processor (`mudio.processor`)

The processor module handles high-level batch processing, including parallel execution, file validation, backups, and error reporting.

### `process_file()`

**`process_file(path: str, ops: FieldOperationsType, targeted_fields: List[str], ...) -> ProcessResultType`**

Processes a single file with comprehensive error handling.

**Parameters:**
- **path** (str): File path to process
- **ops** (Dict): Dictionary mapping field names to operation functions (see `mudio.operations`)
- **targeted_fields** (List[str]): Fields being modified (used for verification)
- **backup_dir** (str, optional): Path to directory for storing backups
- **dry_run** (bool): If `True`, calculates changes but does not write to disk
- **verify** (bool): If `True`, re-reads file after writing to verify changes
- **filters** (List[FilterType], optional): Filters to apply before processing
- **verbose** (bool): Enables progress printing
- **force** (bool): If `True`, overwrites existing backups where necessary
- **delete_backups** (bool): If `True`, removes backups after successful operations
- **read_schema** (str, optional): Schema to use when reading metadata ('canonical', 'extended', 'raw'). Default: `None` (uses global default).

**Returns:** `ProcessResultType` (Dict) with keys:
- `'passed'` (bool): Whether processing succeeded
- `'path'` (str): File path that was processed
- `'ext'` (str): File extension
- `'original'` (Dict): Original field values
- `'planned'` (Dict): New field values that were computed
- `'changed'` (Dict): Which fields actually changed
- `'wrote'` (bool): Whether write operation succeeded
- `'verified'` (Dict): Verification results (if enabled)
- `'error'` (str or None): Error message if failed
- `'skipped'` (bool): If file was skipped (e.g., filter didn't match)
- `'note'` (str): Additional notes (e.g., 'no changes', 'dry-run')

**Processing Steps:**
1. Validates file (permissions, format, size)
2. Applies filters to determine if file matches criteria
3. Computes new tag values using `ops`
4. Creates backup (if `backup_dir` specified)
5. Writes changes to file
6. Verifies changes by re-reading (if `verify=True`)
7. Cleans up or preserves backup based on success

### `process_files()`

**`process_files(files: Iterable[Path], ops: FieldOperationsType, targeted_fields: List[str], ...) -> List[ProcessResultType]`**

Batch processes multiple files. Automatically chooses between sequential and parallel processing based on file count and configuration.

**Parameters:** Same as `process_file()`, plus:
- **files** (Iterable[Path]): Iterable of file paths to process
- **max_workers** (int): Number of threads. Default `0` means auto-detect. Set to `1` for sequential processing
- **use_parallel** (bool): If `False`, forces sequential processing even for large batches

**Returns:** List of `ProcessResultType` dictionaries, one per file

**Example:**
```python
from mudio.processor import process_files
from mudio.operations import write
from pathlib import Path

files = Path('/music').glob('*.mp3')
results = process_files(
    files,
    ops={'album': write('album', 'Greatest Hits')},
    targeted_fields=['album'],
    max_workers=4,
    backup_dir='./backups'
)

# Analyze results
success = sum(1 for r in results if r['passed'])
print(f"Processed {success}/{len(results)} files successfully")
```

### Validation

**`validate_file(path: Path) -> None`**

Performs comprehensive file validation. Raises exceptions on failure:
- File existence and type
- Read/write permissions
- File size (empty files or files exceeding limits)
- Format validity (can mutagen parse it?)

---

## Operations (`mudio.operations`)

This module defines how field values are transformed. Operations are used with `process_file()` and `process_files()`.

### How Operations Work

Operations are **factory functions** that return transformation functions:

```python
from mudio.operations import find_replace

# Create an operation
op = find_replace('title', 'Demo', 'Final')

# The operation is a function: List[str] -> List[str]
result = op(['Demo Track'])  # Returns ['Final Track']
```

### Operation Functions

All operations return `Callable[[List[str]], List[str]]` - a function that transforms field values.

*   **`write(field, value, delimiter=';')`**: Creates or overwrites the field with the given value(s)
    - Splits strings on `delimiter` for multi-valued fields
    - Example: `write('album', 'Greatest Hits')` 

*   **`append(field, value, delimiter=';')`**: Adds to existing values
    - Single-valued fields: Appends string to existing value
    - Multi-valued fields: Adds new item(s) if not present
    - Example: `append('title', ' (Remastered)')`

*   **`prefix(field, value)`**: Prepends string to values
    - Single-valued: Prepends to the first value
    - Multi-valued: Prepends to all values
    - Example: `prefix('artist', 'DJ ')`

*   **`find_replace(field, find, replace, regex=False, delimiter=';')`**: String substitution
    - Supports literal or regex patterns
    - If result contains `delimiter`, splits into multiple values (for multi-valued fields)
    - Example: `find_replace('title', r'\d+', '#', regex=True)`

*   **`enlist(field, value, delimiter=';')`**: Adds value(s) to multi-valued field
    - Only adds if not already present (case-insensitive)
    - Example: `enlist('genre', 'Rock;Electronic')`

*   **`delist(field, value, delimiter=';')`**: Removes specific value(s)
    - Case-insensitive removal
    - Example: `delist('artist', 'Old Artist')`

*   **`clear(field)`**: Sets field to empty string
    - Returns `[""]` - field remains present but empty
    - Behavior varies by format (some may omit empty fields)

*   **`delete(field)`**: Removes field key entirely
    - Returns `[]` - field is removed from metadata
    - More complete removal than `clear()`

### Field Types

The `FieldOperations` class categorizes fields:

- **Single-valued**: `title`, `album`, `date`, `track`, `disc`, etc.
  - Operations take only the first value
- **Multi-valued**: `artist`, `genre`, `albumartist`, `performer`, `composer`
  - Operations maintain full list, deduplicate case-insensitively
- **Special**: `comment` - can be multi-valued but doesn't deduplicate

---

## Low-Level: `SimpleMusic` (Advanced Users)

> **⚠️ Most users should use `process_file()` instead.** Use `SimpleMusic` directly only if you need fine-grained control or custom logic that doesn't fit standard operations.

`SimpleMusic` is the underlying class that provides direct read/write access to audio metadata. It's used internally by `mudio.processor`.

### When to Use `SimpleMusic`

Use `SimpleMusic` directly when:
- You need custom logic that doesn't fit standard operations
- You're building your own tools with different safety/backup requirements
- You want maximum control over the read/write workflow
- You don't need automatic backups, verification, or filtering

### Basic Usage

```python
from mudio.core import SimpleMusic

# Always use context manager for proper cleanup
with SimpleMusic.managed("song.mp3") as sm:
    # Read metadata
    fields = sm.read_fields()
    
    # Your custom logic here
    if 'artist' in fields:
        fields['artist'] = [a.upper() for a in fields['artist']]
    
    # Write back
    sm.write_fields(fields)
```

### Methods

**`SimpleMusic(path: Union[str, Path])`**
- **path**: File path to open
- **Raises**: `FormatError`, `RuntimeError`

**`SimpleMusic.read_fields(schema: str = 'extended') -> Dict[str, List[str]]`**

Reads metadata from the file.

- **schema**:
  - `'canonical'`: Only standardized fields (title, artist, date, etc.)
  - `'extended'` (default): Canonical fields **plus** any custom/extra fields
  - `'raw'`: Same as extended but with format-specific keys (TIT2, ©nam, etc.)

- **Returns**: Dictionary where keys are field names and values are **lists of strings**
  - All values are lists for consistency, even single-valued fields
  - See `FieldOperations` for which fields are semantically single vs. multi-valued
  - **Key Sanitization**:
    - **Read**: Keys are normalized to **small snake case** (`[a-z0-9_]`).
    - **Write**: Custom keys are normalized to **caps snake case** (`[A-Z0-9_]`).
    - **Normalization**: Drops alternative casing to prevent duplicates.

**`SimpleMusic.write_fields(fields: Dict[str, List[str]])`**

Writes metadata to the file.

- **fields**: Dictionary of field names to value lists
  - Keys can be canonical names (`title`, `artist`) or custom strings
  - Custom fields are written as format-specific tags (TXXX, freeform, etc.)
  - Fields not in the dictionary are **preserved** (not deleted)
  - To delete a field, pass `[]` as the value

- **Raises**: `PermissionError`, `RuntimeError`

**`SimpleMusic.managed(path: Union[str, Path])`** (class method)

Context manager that ensures proper file cleanup.

**`SimpleMusic.parse_list_string(s: Optional[str], delimiter: str = ';') -> List[str]`** (static)

Utility to split delimited strings into lists.

---

## Utilities (`mudio.utils`)

**`Config`**

Global configuration settings loaded from environment variables:
- `MUDIO_SCHEMA`: Default schema (`canonical`, `extended`, or `raw`). Default: `extended`
- `MUDIO_MAX_WORKERS`: Default thread count for parallel processing
- `MUDIO_BACKUP_DIR`: Default backup location
- `MUDIO_VERBOSE`: Default verbosity (`0` or `1`)
- `MUDIO_NAMESPACE`: Default namespace for MP4/M4A custom fields (default: `com.apple.iTunes`)

```python
from mudio.utils import Config

print(f"Default schema: {Config.DEFAULT_SCHEMA}")
```

**`get_file_hash(path: Path) -> str`**

Calculates SHA-256 hash of a file for verification.

---

## Types and Errors

### Error Hierarchy

```python
class MudioError(Exception): ...
class ValidationError(MudioError): ...      # Invalid arguments or state
class FormatError(MudioError): ...          # File format issues
class PermissionError(MudioError): ...      # Filesystem permission issues
class VerificationError(MudioError): ...    # Post-write verification failed
```

### Type Definitions

```python
FieldOperationsType = Dict[str, Callable[[List[str]], List[str]]]
FieldValuesType = Dict[str, List[str]]
FilterType = Tuple[str, str, bool]
ProcessResultType = Dict[str, Any]
```

*   **`FieldOperationsType`**: Maps field names to transformation functions
*   **`FieldValuesType`**: Standard metadata dictionary (field → list of strings)
*   **`FilterType`**: Tuple of (field, pattern, is_regex)
*   **`ProcessResultType`**: Result dictionary from `process_file()`
