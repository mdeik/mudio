"""
File processing logic for mudio.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Generator, Iterable, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal
import sys
from .core import SimpleMusic, SUPPORTED_EXT
from .utils import Config, get_file_hash, print_progress_safe, EXIT_CODE_INTERRUPTED
from .operations import (
    FieldOperations, 
    FieldOperationsType, 
    FieldValuesType, 
    FilterType, 
    compute_new_fields, 
    apply_filter
)

logger = logging.getLogger(__name__)

ProcessResultType = Dict[str, Any]

# ---------- Signal Handlers ----------
def register_signal_handlers():
    """Register signal handlers for graceful shutdown on Ctrl+C/SIGTERM."""
    def signal_handler(sig, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        sys.exit(EXIT_CODE_INTERRUPTED)
    
    # Only register on platforms that support it
    if sys.platform != "win32":
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except ValueError:
            pass

def unregister_signal_handlers():
    """Unregister signal handlers (restore defaults)."""
    if sys.platform != "win32":
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
        except ValueError:
            pass

# ---------- Parallel Processing ----------
def _process_files_parallel(
    files: Iterable[Path],
    ops: List[FieldOperationsType],
    *,
    max_workers: int = None,
    filters: Optional[List[FilterType]] = None,
    dry_run: bool = False,
    backup_dir: Optional[str] = None,
    delete_backups: bool = False,
    force: bool = False,
    verbose: bool = False,
    verify: bool = True,
    read_schema: Optional[str] = None
) -> List[ProcessResultType]:
    """
    Process multiple files in parallel using a thread pool.
    
    Args:
        files: Iterable of file paths to process
        ops: Operations to apply to fields
        max_workers: Number of parallel threads (None = auto)
        filters: List of (field, pattern, is_regex) tuples to filter files
        dry_run: If True, show changes without writing
        backup_dir: Directory for backups before modification
        delete_backups: If True, delete successful backups
        force: Allow potentially destructive operations
        verbose: Show progress and detailed output

        verify: Verify writes by reading back from disk
        read_schema: Metadata schema to use for reading    
    Returns:
        List of result dictionaries with processing outcomes
    """
    if max_workers is None:
        max_workers = Config.MAX_WORKERS
    
    files_list = list(files)
    total_files = len(files_list)
    
    if total_files == 0:
        return []
    
    results = []
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(
                process_file,
                str(file_path),
                ops,
                filters=filters,
                dry_run=dry_run,
                backup_dir=backup_dir,
                delete_backups=delete_backups,
                force=force,

                verify=verify,
                read_schema=read_schema
            ): file_path for file_path in files_list
        }
        
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            completed += 1
            
            try:
                result = future.result()
                results.append(result)
                
                if verbose and total_files > 10:
                    print_progress_safe(
                        f"Progress: {completed}/{total_files} ({completed/total_files*100:.1f}%) - {file_path.name}",
                        end='\r'
                    )
                
                if verbose and result.get('error'):
                    print_progress_safe(f"\n  ERROR: {result['error']}")
                    
            except Exception as e:
                results.append({
                    'path': str(file_path),
                    'error': f'Unexpected error: {e}',
                    'exception': e,
                    'passed': False,
                    'ext': file_path.suffix.lower()
                })
    
    if verbose and total_files > 10:
        print_progress_safe()  # Newline after progress
    
    return results

def process_files(
    files: Iterable[Path],
    ops: List[FieldOperationsType],
    *,
    max_workers: int = 0,
    filters: Optional[List[FilterType]] = None,
    dry_run: bool = False,
    backup_dir: Optional[str] = None,
    delete_backups: bool = False,
    force: bool = False,
    verbose: bool = False,
    verify: bool = True,
    read_schema: Optional[str] = None
) -> List[ProcessResultType]:
    """
    Smart dispatcher that chooses between parallel and sequential processing.

    Decides whether to use parallel processing based on the number of files and
    available workers. Falls back to sequential processing for small batches or
    when only one worker is available.

    Args:
        files: Iterable of file paths to process.
        ops: List of operations to apply to fields.
        max_workers: Maximum number of threads to use (0 or None = auto-detect).
        filters: Optional list of filters to exclude files.
        dry_run: If True, simulate operations without writing changes.
        backup_dir: Directory to store backups.
        delete_backups: If True, remove backups after successful processing.
        force: If True, allow overwriting existing files/backups.
        verbose: If True, print detailed progress and debug info.
        verify: If True, re-read files after writing to verify changes.
        read_schema: Schema to use when reading metadata ('canonical', 'extended', 'raw').

    Returns:
        List of result dictionaries containing processing status and metadata.
    """
    files_list = list(files)
    total_files = len(files_list)
    
    if total_files == 0:
        return []

    # Treat 0 as auto (None previously)
    effective_workers = max_workers if max_workers > 0 else Config.MAX_WORKERS
    
    # Auto-select parallelism: use threads when there are enough files to benefit
    should_use_parallel = (
        total_files >= Config.MIN_FILES_FOR_PARALLEL and
        effective_workers != 1
    )
    
    if should_use_parallel:
        with Config.PROGRESS_LOCK:
            logger.info(f"Using parallel processing with {effective_workers} workers")
            if verbose:
                print(f"Processing {total_files} files in parallel...")
        
        return _process_files_parallel(
            files_list, ops,
            max_workers=effective_workers, 
            filters=filters,
            dry_run=dry_run,
            backup_dir=backup_dir,
            delete_backups=delete_backups,
            force=force,
            verbose=verbose,
            verify=verify,
            read_schema=read_schema
        )
    else:
        with Config.PROGRESS_LOCK:
            logger.info("Using sequential processing")
            if verbose:
                print(f"Processing {total_files} files sequentially...")
        
        results = []
        for i, file_path in enumerate(files_list, 1):
            if verbose:
                progress_msg = f"Progress: {i}/{total_files} ({i/total_files*100:.1f}%)"
                print(progress_msg, end='\r' if i < total_files else '\n')
            
            result = process_file(
                str(file_path), ops,
                filters=filters,
                dry_run=dry_run,
                backup_dir=backup_dir,
                delete_backups=delete_backups,
                force=force,
                verify=verify,
                read_schema=read_schema
            )
            results.append(result)
            
            if verbose and result.get('error'):
                print(f"  ERROR: {result['error']}")
        
        return results

# ---------- File Validation ----------
def validate_file(path: Path, check_write: bool = True) -> Tuple[bool, str]:
    """
    Comprehensive file validation.

    Checks existence, type, size constraints, permissions, and extension support.

    Args:
        path: Path to the file to validate.
        check_write: If True, check for write permissions (default: True).

    Returns:
        Tuple of (is_valid, message). Message explains failure reason if invalid.
    """
    try:
        if not path.exists():
            return False, "File does not exist"
        if not path.is_file():
            return False, "Path is not a file"
        
        file_size = path.stat().st_size
        if file_size > Config.MAX_FILE_SIZE:
            return False, f"File too large ({file_size} bytes)"
        if file_size == 0:
            return False, "File is empty"
        
        if not os.access(path, os.R_OK):
            return False, "No read permission"
        
        if check_write and not os.access(path, os.W_OK):
            return False, "No write permission"
        
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXT:
            return False, f"Unsupported file extension: {ext}"
        
        return True, "Valid"
    except Exception as e:
        return False, f"Validation error: {e}"

def create_backup_path(original_path: Path, backup_dir: Path) -> Path:
    """
    Create a secure backup path with collision handling.

    Generates a unique backup path within the backup directory. If a file with
    the same name exists, appends a counter (e.g., file_1.mp3) until a unique
    name is found or the retry limit is reached.

    Args:
        original_path: Path of the file being backed up.
        backup_dir: Directory where the backup should be placed.

    Returns:
        Path object for the new backup file.

    Raises:
        ValueError: If backup_dir is inside the source directory tree.
        RuntimeError: If a unique name cannot be generated after retry limit.
    """
    try:
        backup_dir.resolve().relative_to(original_path.resolve().parent)
    except ValueError:
        pass
    else:
        raise ValueError("Backup directory cannot be inside the source directory tree")
    
    safe_name = original_path.name
    base_backup_path = backup_dir / safe_name
    
    backup_path = base_backup_path
    counter = 1
    while backup_path.exists():
        name, ext = os.path.splitext(base_backup_path.name)
        backup_path = backup_dir / f"{name}_{counter}{ext}"
        counter += 1
        if counter > Config.BACKUP_RETRY_LIMIT:
            raise RuntimeError(f"Could not find unique backup name after {Config.BACKUP_RETRY_LIMIT} attempts")
    
    return backup_path

def safe_file_copy(src: Path, dst: Path, exclusive: bool = False) -> bool:
    """Safely copy file with error handling and verification.
    
    Args:
        src: Source file path
        dst: Destination file path
        exclusive: If True, fail if destination already exists (atomic creation)
    
    Raises:
        FileExistsError: If exclusive=True and destination exists
        RuntimeError: If file copy verification fails
    """
    src_hash = get_file_hash(src)
    
    mode = 'xb' if exclusive else 'wb'
    with open(src, 'rb') as f_src, open(dst, mode) as f_dst:
        for chunk in iter(lambda: f_src.read(Config.CHUNK_SIZE), b""):
            f_dst.write(chunk)
    
    dst_hash = get_file_hash(dst)
    if src_hash != dst_hash:
        raise RuntimeError("File copy verification failed - checksum mismatch")
    
    return True

def verify_written(path: Path, expected_fields: FieldValuesType, read_schema: Optional[str] = None) -> Dict[str, bool]:
    """
    Verify that fields were written correctly to the file.

    Re-reads the file metadata and compares specific fields against expected values.
    Handles field name normalization (case-insensitivity) and value normalization
    (integer conversion for track/disc numbers).

    Args:
        path: Path to the file to verify.
        expected_fields: Dictionary of field names and their expected values.
        read_schema: Schema to use when reading back (default: Config.DEFAULT_SCHEMA).

    Returns:
        Dictionary mapping field names to boolean success status.
    """
    try:
        with SimpleMusic.managed(path) as sm:
            # Use provided schema or default
            actual_schema = read_schema if read_schema else Config.DEFAULT_SCHEMA
            reloaded = sm.read_fields(schema=actual_schema)
            results = {}
            
            for field, expected in expected_fields.items():
                expected_norm = FieldOperations.normalize_values(field, expected)
                # Try exact key, then lowercase key
                got_values = reloaded.get(field)
                if got_values is None:
                    got_values = reloaded.get(field.lower())
                if got_values is None:
                    got_values = reloaded.get(field.upper(), [])
                
                got_norm = FieldOperations.normalize_values(field, got_values)
                
                if field in ('track', 'disc', 'totaltracks', 'totaldiscs'):
                    try:
                        exp_int = int(expected_norm[0]) if expected_norm and expected_norm[0] else None
                        got_int = int(got_norm[0]) if got_norm and got_norm[0] else None
                        results[field] = (exp_int == got_int)
                    except (ValueError, IndexError):
                        results[field] = (expected_norm == got_norm)
                else:
                    results[field] = (expected_norm == got_norm)
            
            return results
    except Exception as e:
        logger.error(f"Verification failed for {path}: {e}")
        return {field: False for field in expected_fields}

# ---------- File Processing Components ----------
def _validate_and_read_file(path: Path, read_schema: str = 'extended', check_write: bool = True) -> Tuple[bool, str, Optional[FieldValuesType]]:
    """
    Validate file and read original fields.

    Helper function that combines validation and initial read.

    Args:
        path: Path to the file.
        read_schema: Schema to use for reading metadata.
        check_write: If True, check for write permissions.

    Returns:
        Tuple of (success, error_message, fields). Fields is None on failure.
    """
    ext = path.suffix.lower()
    
    is_valid, validation_msg = validate_file(path, check_write=check_write)
    if not is_valid:
        return False, f'file validation failed: {validation_msg}', None
    
    try:
        with SimpleMusic.managed(path) as sm:
            orig = sm.read_fields(schema=read_schema)
        return True, "", orig
    except Exception as e:
        return False, f'file error: {e}', None

def _apply_filters(filters: List[FilterType], orig: FieldValuesType) -> bool:
    """
    Apply all filters to fields.

    Args:
        filters: List of (field, pattern, is_regex) tuples.
        orig: Dictionary of original field values.

    Returns:
        True if the file matches ALL filters, False otherwise.
    """
    if not filters:
        return True
        
    for (field, pattern, regex_flag) in filters:
        if not apply_filter(field, pattern, regex_flag, orig):
            return False
    return True

def _create_backup(path: Path, backup_dir: Optional[Path]) -> Tuple[Optional[Path], Optional[str]]:
    """
    Create backup of file with retry on race condition.

    Args:
        path: Path of the file to back up.
        backup_dir: Directory to store the backup.

    Returns:
        Tuple of (backup_path, error_message). backup_path is None if backup failed
        or wasn't requested. error_message is None on success.
    """
    if not backup_dir:
        return None, None
        
    try:
        backup_dir_path = Path(backup_dir)
        backup_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Retry loop to handle race conditions when multiple threads
        # try to create backups with similar names simultaneously
        for attempt in range(Config.BACKUP_RETRY_LIMIT):
            backup_path = create_backup_path(path, backup_dir_path)
            try:
                safe_file_copy(path, backup_path, exclusive=True)
                with Config.PROGRESS_LOCK:
                    logger.info(f"Backup created: {backup_path}")
                return backup_path, None
            except FileExistsError:
                # Another thread created this file between check and create
                # Loop will retry with a new path
                continue
        
        return None, f'backup failed: could not find unique name after {Config.BACKUP_RETRY_LIMIT} attempts'
    except Exception as e:
        return None, f'backup failed: {e}'

def _write_new_fields(path: Path, new_fields: FieldValuesType) -> Tuple[bool, Optional[str]]:
    """
    Write new fields to file.

    Args:
        path: Path to the file.
        new_fields: Dictionary of new metadata to write.

    Returns:
        Tuple of (success, error_message).
    """
    try:
        with SimpleMusic.managed(path) as sm_write:
            sm_write.write_fields(new_fields)
        with Config.PROGRESS_LOCK:
            logger.info(f"Successfully wrote metadata to: {path}")
        return True, None
    except Exception as e:
        return False, f'write failed: {e}'

def _restore_from_backup(path: Path, backup_path: Optional[Path]) -> bool:
    """
    Restore file from backup.

    Args:
        path: Path to the file to restore.
        backup_path: Path to the backup file.

    Returns:
        True if restoration was successful, False otherwise.
    """
    if not backup_path or not backup_path.exists():
        return False
        
    try:
        safe_file_copy(backup_path, path)
        with Config.PROGRESS_LOCK:
            logger.info(f"Restored from backup after write failure: {path}")
        return True
    except Exception as restore_error:
        logger.error(f"Failed to restore from backup: {restore_error}")
        return False

def _cleanup_backup(backup_path: Optional[Path], force: bool, delete_backups: bool) -> None:
    """
    Clean up backup file if appropriate.

    Deletes the backup file if delete_backups is True.

    Args:
        backup_path: Path to the backup file.
        force: (Unused currently, but reserved for forced cleanup logic).
        delete_backups: Whether to delete the backup.
    """
    if backup_path and backup_path.exists():
        if not delete_backups:
             logger.debug(f"Keeping backup: {backup_path}")
             return

        # Delete only if delete_backups is True
        try:
            backup_path.unlink()
            logger.debug(f"Cleaned up backup: {backup_path}")
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to clean up backup {backup_path}: {e}")

# ---------- Process One File ----------
def process_file(path: str, 
                ops: List[FieldOperationsType], 
                *,
                filters: Optional[List[FilterType]] = None,
                dry_run: bool = False, 
                backup_dir: Optional[str] = None, 
                delete_backups: bool = False,
                force: bool = False,
                verify: bool = True,
                read_schema: Optional[str] = None) -> ProcessResultType:
    """
    Process a single file with comprehensive error handling.

    Executes the full processing pipeline for a single file:
    1. Validation
    2. Reading original metadata
    3. Filtering
    4. Computing new field values
    5. Creating backup (if requested)
    6. Writing new metadata
    7. Verifying write (if requested)
    8. Cleaning up backup (on success) or keeping it (on failure)

    Args:
        path: Path to the file.
        ops: List of operations to apply.
        filters: Optional filters.
        dry_run: Simulate only.
        backup_dir: Directory for backups.
        delete_backups: Remove backup on success.
        force: Force operations.
        verify: Verify writes.
        read_schema: Schema for reading.

    Returns:
        Dictionary containing processing results (status, changes, errors).
    """
    file_path = Path(path)
    ext = file_path.suffix.lower()
    
    # Quick check: reject unsupported file types before doing any I/O
    if ext not in SUPPORTED_EXT:
         return {
            'path': str(file_path), 
            'error': f"Unsupported file extension: {ext}", 
            'passed': False, 
            'ext': ext
        }

    # Explicit validation with dry-run awareness
    is_valid, val_msg = validate_file(file_path, check_write=not dry_run)
    if not is_valid:
        return {
            'path': str(file_path), 
            'error': f"Validation failed: {val_msg}", 
            'passed': False, 
            'ext': ext
        }
    
    try:
        # Use a single context manager for the entire read-modify-write cycle
        with SimpleMusic.managed(file_path) as sm:
            # Read original fields
            actual_read_schema = read_schema if read_schema else Config.DEFAULT_SCHEMA
            orig = sm.read_fields(schema=actual_read_schema)
            
            # Apply filters
            if not _apply_filters(filters or [], orig):
                return {
                    'path': str(file_path), 
                    'skipped': True, 
                    'reason': 'filter not match', 
                    'ext': ext
                }
            
            # Compute new fields
            new_fields, changed = compute_new_fields(orig, ops)
            
            # Effective targeted fields are those that were touched by operations
            effective_targeted_fields = list(changed.keys())
            
            any_changed = any(changed.values())
            
            record = {
                'path': str(file_path),
                'ext': ext,
                'original': orig,
                'planned': new_fields,
                'changed': changed,
                'wrote': False,
                'verified': {},
                'error': None,
                'exception': None,
                'backup_path': None,
                'backup_kept': None
            }
            
            if not any_changed:
                return {**record, 'passed': True, 'note': 'no changes'}
            
            if dry_run:
                return {**record, 'passed': True, 'note': 'dry-run'}
            
            # Create backup
            if backup_dir:
                backup_path, backup_error = _create_backup(file_path, Path(backup_dir))
                if backup_error:
                    return {**record, 'error': backup_error, 'passed': False}
                record['backup_path'] = str(backup_path)
            else:
                backup_path = None
            
            # Write new fields
            try:
                sm.write_fields(new_fields)
                # Log success at debug level (verbose handled by logger config)
                logger.debug(f"Successfully wrote metadata to: {path}")
                record['wrote'] = True
            except Exception as e:
                write_error = f'write failed: {e}'
                # Restore from backup if write failed
                if backup_path:
                    _restore_from_backup(file_path, backup_path)
                return {**record, 'error': write_error, 'exception': e, 'passed': False}
            
            # Re-read the file from disk to confirm our writes persisted correctly
            if verify:
                try:
                    record['verified'] = verify_written(
                        file_path, 
                        {k: new_fields[k] for k in effective_targeted_fields},
                        read_schema=actual_read_schema
                    )
                    record['passed'] = all(record['verified'].values())
                    
                    if not record['passed']:
                        logger.warning(f"Verification failed for {file_path}: {record['verified']}")
                except Exception as e:
                    logger.error(f"Verification process error: {e}")
                    record['passed'] = False
            else:
                record['verified'] = {}
                record['passed'] = True
            
            # On success: optionally delete the backup. On failure: always keep it.
            if record['passed']:
                 _cleanup_backup(backup_path, force, delete_backups)
                 if backup_path:
                     record['backup_kept'] = not delete_backups
            else:
                 # If failed, ALWAYS keep backup
                 if backup_path and backup_path.exists():
                     logger.debug(f"Keeping backup due to failure: {backup_path}")
                     record['backup_kept'] = True
            
            return record

    except Exception as e:
         return {
            'path': str(file_path), 
            'error': f"file error: {e}", 
            'exception': e,
            'passed': False, 
            'ext': ext
        }

def collect_files_generator(path: Path, recursive: bool = False, ext_set: Optional[set] = None) -> Generator[Path, None, None]:
    """
    Generator to collect files efficiently without loading all into memory.

    Args:
        path: Base path (file or directory).
        recursive: If True, recurse into subdirectories.
        ext_set: Optional set of allowed extensions (e.g. {'.mp3', '.flac'}).

    Yields:
        Path objects for each matching file.
    """
    if path.is_file():
        yield path
        return
    
    walker = path.rglob('*') if recursive else path.glob('*')
    
    for item in walker:
        if item.is_file():
            ext = item.suffix.lower()
            if ext_set and ext not in ext_set:
                continue
            if ext in SUPPORTED_EXT:
                yield item

# ---------- Batch Processing ----------
def process_batch(
    path: Union[str, Path],
    operations: List[FieldOperationsType],
    recursive: bool = False,
    extensions: Optional[List[str]] = None,
    filters: Optional[List[FilterType]] = None,
    dry_run: bool = False,
    backup_dir: Optional[Union[str, Path]] = None,
    delete_backups: bool = False,
    force: bool = False,
    verbose: bool = False,
    max_workers: Optional[int] = None,
    verify: bool = True,
    read_schema: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process multiple audio files with a clean Python API.
    
    Supports parallel processing for large batches, automatically using multiple 
    threads when beneficial unless disabled.
    
    Args:
        path: Directory or file path to process
        operations: List of operation functions
        recursive: If True, search subdirectories
        extensions: List of file extensions to include (e.g. ['.mp3', '.flac'])
        filters: List of (field, pattern, is_regex) tuples to filter files
        dry_run: If True, show changes without writing
        backup_dir: Directory to store backups before modifying files
        delete_backups: If True, delete backups after successful operations
        force: If True, allow potentially destructive operations
        verbose: If True, show detailed progress
        max_workers: Number of parallel workers (None = auto)
        verify: If True, verify writes by reading back metadata
    
    Returns:
        Dict with keys: processed, successful, failed, skipped, results
    """
    if verbose:
        logging.basicConfig(level=logging.INFO)
    
    path = Path(path)
    ext_set = set(extensions) if extensions else None
    
    # Collect files
    files = list(collect_files_generator(path, recursive=recursive, ext_set=ext_set))
    
    if not files:
        logger.warning("No matching files found")
        return {"processed": 0, "successful": 0, "failed": 0, "skipped": 0, "results": []}
    
    # Process collected files using the smart dispatcher which handles parallelism
    results = process_files(
        files,
        operations,
        max_workers=max_workers or 0,
        filters=filters,
        dry_run=dry_run,
        backup_dir=str(backup_dir) if backup_dir else None,
        delete_backups=delete_backups,
        force=force,
        verbose=verbose,
        verify=verify,
        read_schema=read_schema
    )
    
    # Summarize results
    summary = {
        "processed": len(results),
        "successful": sum(1 for r in results if r.get('passed', False)),
        "failed": sum(1 for r in results if not r.get('passed', False) and not r.get('skipped', False)),
        "skipped": sum(1 for r in results if r.get('skipped', False)),
        "results": results
    }
    
    return summary

def write_fields(
    path: Union[str, Path],
    fields: Dict[str, str],
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to set multiple fields at once.
    """
    from .operations import write
    
    operations = []
    
    for field_name, value in fields.items():
        operations.append(write(field_name, value))
    
    return process_batch(path, operations, **kwargs)