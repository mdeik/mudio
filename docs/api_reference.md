# mudio API Reference

This document provides a detailed reference for the internal Python API of `mudio`. It is useful for developers who want to use `mudio` as a library in their own scripts or applications.

---

## Recommended: Use `mudio.processor`

**For most use cases, use the high-level `process_file()` and `process_files()` functions.** They provide automatic backups, verification, filtering, parallel processing, and comprehensive error handling.

### Quick Example

```python
from mudio.processor import process_file
from mudio.operations import write, append, delete

result = process_file(
    "song.mp3",
    ops=[
        write('artist', 'The Beatles'),
        write('album', 'Abbey Road'),
        append('genre', 'Rock'),          # Add to existing genres
        delete('comment')                  # Remove field entirely
    ],
    backup_dir='./backups'
)

if result['passed']:
    print(f"✓ Updated {list(result['changed'].keys())}")
else:
    print(f"✗ {result['error']}")
```

---

## Processing Functions

Mudio provides a layered API with multiple entry points depending on your use case:

1. **`process_file`** - Process a single file with full control
2. **`process_files`** - Process multiple files (takes a list of Paths)
3. **`process_batch`** - High-level batch API with directory scanning and result summarization
4. **`write_fields`** - Convenient shorthand for writing multiple fields at once

---

### `process_file()` - Single File Processing

**`process_file(path: str, ops: List[FieldOperationsType], ...) -> ProcessResultType`**

Processes a single audio file with comprehensive error handling, backup, and verification.

**Parameters:**
- **path** (str): File path to process
- **ops** (List[FieldOperationsType]): List of operation functions to apply (see `mudio.operations`)
- **filters** (List[FilterType], optional): Filter conditions to check before processing
- **dry_run** (bool): If `True`, calculates changes but does not write to disk. Default: `False`
- **backup_dir** (str, optional): Directory to store backups before modification
- **delete_backups** (bool): If `True`, deletes backups after successful operations. Default: `False`
- **force** (bool): If `True`, overwrites existing backups. Default: `False`
- **verify** (bool): If `True`, re-reads file after writing to verify changes. Default: `True`
- **read_schema** (str, optional): Schema for reading metadata (`'canonical'`, `'extended'`, `'raw'`). Default: `None` (uses global config)

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

**Example:**
```python
from mudio.processor import process_file
from mudio.operations import write, prefix

# Process with dry-run to preview changes
result = process_file(
    "song.mp3",
    ops=[
        write('album', 'Greatest Hits'),
        prefix('title', '[Remastered] ')
    ],
    dry_run=True
)

if result['passed']:
    print(f"Planned: {result['planned']}")
    print(f"Would change: {list(result['changed'].keys())}")
```

---

### `process_files()` - Batch File Processing

**`process_files(files: Iterable[Path], ops: List[FieldOperationsType], ...) -> List[ProcessResultType]`**

Processes multiple files. Automatically chooses between sequential and parallel processing based on file count and configuration.

**Parameters:** Same as `process_file()`, plus:
- **files** (Iterable[Path]): Iterable of file paths to process
- **max_workers** (int): Number of parallel threads. Default `0` = auto-detect. Set to `1` for sequential processing

**Returns:** List of `ProcessResultType` dictionaries, one per file

**Example:**
```python
from mudio.processor import process_files
from mudio.operations import write, enlist
from pathlib import Path

# Process files with filtering (only files with specific artist)
results = process_files(
    Path('music').glob('*.flac'),
    ops=[enlist('genre', 'Electronic;Ambient')],
    filters=[('artist', 'Brian Eno', False)],  # Plain text match
    max_workers=4
)

print(f"Updated {sum(r['passed'] for r in results)} files")
```

---

### `process_batch()` - High-Level Batch API

**`process_batch(path: Union[str, Path], operations: List[FieldOperationsType], ...) -> Dict[str, Any]`**

High-level API that combines file collection with batch processing. Automatically scans directories and provides a summary of results.

**Parameters:**
- **path** (Union[str, Path]): Directory or file path to process
- **operations** (List[FieldOperationsType]): List of operation functions to apply
- **recursive** (bool): If `True`, search subdirectories. Default: `False`
- **extensions** (List[str], optional): File extensions to include (e.g., `['.mp3', '.flac']`). Default: all supported formats
- **filters** (List[FilterType], optional): Filter conditions
- **dry_run** (bool): If `True`, show changes without writing. Default: `False`
- **backup_dir** (Union[str, Path], optional): Directory for backups
- **force** (bool): If `True`, allow potentially destructive operations. Default: `False`
- **verbose** (bool): If `True`, show detailed progress. Default: `False`
- **max_workers** (Optional[int]): Number of parallel workers. Default: `None` (auto-detect)
- **verify** (bool): If `True`, verify writes by reading back. Default: `True`

**Returns:** Dict with keys:
- `'processed'` (int): Total files processed
- `'successful'` (int): Files processed successfully
- `'failed'` (int): Files that failed
- `'skipped'` (int): Files skipped by filters
- `'results'` (List[ProcessResultType]): Detailed results for each file

**Example:**
```python
from mudio.batch import process_batch
from mudio.operations import find_replace

# Batch replace text in all files under a directory
result = process_batch(
    'music/albums',
    operations=[find_replace('title', r'\s*\(feat\..*?\)', '', regex=True)],
    recursive=True,
    extensions=['.mp3', '.m4a'],
    backup_dir='./backups'
)

print(f"{result['successful']}/{result['processed']} files updated")
for r in result['results']:
    if r.get('error'):
        print(f"Failed: {r['path']} - {r['error']}")
```

---

### `write_fields()` - Convenience Function

**`write_fields(path: Union[str, Path], fields: Dict[str, Union[str, List[str]]], **kwargs) -> Dict[str, Any]`**

Convenience function to set multiple fields at once. Automatically converts field dictionary into write operations and calls `process_batch()`.

**Parameters:**
- **path** (Union[str, Path]): Directory or file path to process
- **fields** (Dict[str, Union[str, List[str]]]): Dictionary mapping field names to values
- **kwargs**: Additional arguments passed to `process_batch()` (e.g., `recursive`, `dry_run`, `backup_dir`)

**Returns:** Same as `process_batch()`

**Example:**
```python
from mudio.batch import write_fields

# Convenience function for setting canonical fields only
result = write_fields(
    'music/album',
    fields={
        'artist': 'The Beatles',
        'album': 'Abbey Road',
        'date': '1969'
    },
    recursive=True
)

print(f"Updated {result['successful']} files")
```

> [!NOTE]
> `write_fields()` only accepts canonical field names. For custom fields, use `process_batch()` with `write()` operations directly.

---

### Validation

**`validate_file(path: Path) -> Tuple[bool, str]`**

Performs comprehensive file validation. Returns `(success: bool, message: str)` tuple:
- File existence and type
- Read/write permissions
- File size (empty files or files exceeding limits)
- Format validity (supported extension check)

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

All operations return a transformation function: `Callable[[List[str]], List[str]]`

| Operation | Purpose | Example |
|-----------|---------|---------|
| **`write(field, value, delimiter=';')`** | Create/overwrite field | `write('album', 'Greatest Hits')` |
| **`append(field, value, delimiter=';')`** | Add to existing value | `append('title', ' (Remastered)')` |
| **`prefix(field, value)`** | Prepend to value(s) | `prefix('artist', 'DJ ')` |
| **`find_replace(field, find, replace, regex=False, delimiter=';')`** | String substitution | `find_replace('title', r'\\d+', '#', regex=True)` |
| **`enlist(field, value, delimiter=';')`** | Add item(s) to multi-valued field | `enlist('genre', 'Rock;Electronic')` |
| **`delist(field, value, delimiter=';')`** | Remove item(s) from multi-valued field | `delist('genre', 'Pop')` |
| **`clear(field)`** | Set field to empty string | `clear('comment')` |
| **`delete(field)`** | Remove field entirely | `delete('custom_field')` |

**Combining Operations:**
```python
from mudio.operations import write, enlist, find_replace

ops = [
    write('album', 'Best Of Collection'),
    enlist('genre', 'Rock;Classic'),        # Add genres if not present
    find_replace('title', r'\\s+', ' ', regex=True)  # Normalize whitespace
]
```

### Field Types

The `FieldOperations` class categorizes fields:

- **Single-valued**: `title`, `album`, `date`, `track`, `disc`, etc.
  - Operations take only the first value
- **Multi-valued**: `artist`, `genre`, `albumartist`, `performer`, `composer`
  - Operations maintain full list, deduplicate case-insensitively
- **Special**: `comment` - can be multi-valued but doesn't deduplicate

---

## Low-Level: `SimpleMusic` (Advanced Users)

> **⚠️ Most users should use `process_file()` instead.** Use `SimpleMusic` only if you need fine-grained control or custom logic beyond standard operations.

### Basic Usage

```python
from mudio.core import SimpleMusic

# Always use context manager for proper cleanup
with SimpleMusic.managed("song.mp3") as sm:
    # Read metadata
    fields = sm.read_fields(schema='extended')
    
    # Custom transformation
    if 'artist' in fields:
        fields['artist'] = [a.upper() for a in fields['artist']]
    
    # Write back
    sm.write_fields(fields)
```

### Methods

**`SimpleMusic(path: Union[str, Path])`**

Opens an audio file for metadata access. Raises `FormatError` or `RuntimeError` on failure.

**`read_fields(schema: str = 'extended') -> Dict[str, List[str]]`**

Reads metadata from the file. Returns a dict where keys are field names and values are **lists of strings** (even for single-valued fields).

**Schema Options:**
- `'canonical'`: Only standard fields (title, artist, album, date, etc.)
- `'extended'` (default): Canonical **plus** custom/extra fields with normalized keys
- `'raw'`: Returns all fields with format-specific native keys (e.g., `TIT2`, `TXXX:FIELD` for MP3, `©nam` for M4A)

> [!NOTE]
> **Raw mode** returns format-native keys unchanged, while **extended mode** returns normalized keys. For example:
> - **Extended**: `my_custom_field`, `artist`, `title` (portable across formats)
> - **Raw**: `TXXX:MY_CUSTOM_FIELD`, `TPE1`, `TIT2` (MP3-specific ID3 frames)

**Key Normalization (Extended/Canonical modes only):**
- **Canonical fields** always use standard lowercase names (`artist`, `album`, `title`, etc.)
- **Custom field read keys** are sanitized to lowercase `[a-z0-9_]` (e.g., `My-Field!` → `my_field_`)
- **Custom field write keys** are sanitized to uppercase `[A-Z0-9_]` for format-specific storage
- Prevents duplicate fields with different casing

**`write_fields(fields: Dict[str, List[str]])`**

Writes metadata to the file. Custom fields are written as format-specific tags. Fields not in the dict are **preserved**. To delete a field, pass an empty list: `[]`.

**`SimpleMusic.managed(path)` (class method)**

Returns a context manager for safe file handling.

**`SimpleMusic.parse_list_string(s, delimiter=';')` (static)**

Utility to split delimited strings into lists.


---

## Utilities (`mudio.utils`)

**`Config`**

Global configuration settings loaded from environment variables:
- `MUDIO_SCHEMA`: Default schema (`canonical`, `extended`, or `raw`). Default: `extended`
- `MUDIO_MAX_WORKERS`: Default thread count for parallel processing
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
FieldOperationsType = Callable[[List[str]], List[str]]  # Transformation function
FieldValuesType = Dict[str, List[str]]                  # Metadata dictionary
FilterType = Tuple[str, str, bool]                      # (field, pattern, is_regex)
ProcessResultType = Dict[str, Any]                      # Result from process_file()
```
