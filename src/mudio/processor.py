"""
File processing logic for mudio.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional, Any, Generator, Iterable, Callable
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
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        sys.exit(EXIT_CODE_INTERRUPTED)
    
    # Only register on platforms that support it (Windows has limited signal support)
    if sys.platform != "win32":
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except ValueError:
            # Signals may not be supported in all contexts (e.g., threads)
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
def process_files_parallel(
    files: Iterable[Path],
    ops: FieldOperationsType,
    targeted_fields: List[str],
    *,
    max_workers: int = None,
    filters: Optional[List[FilterType]] = None,
    dry_run: bool = False,
    backup_dir: Optional[str] = None,
    delete_backups: bool = False,
    force: bool = False,
    verbose: bool = False,
    dynamic_op: Optional[Callable[[str], Any]] = None,
    verify: bool = True
) -> List[ProcessResultType]:
    """
    Process multiple files in parallel using a thread pool.
    
    Args:
        files: Iterable of file paths to process
        ops: Operations to apply to fields
        targeted_fields: Fields to modify
        max_workers: Number of parallel threads (None = auto)
        filters: List of (field, pattern, is_regex) tuples to filter files
        dry_run: If True, show changes without writing
        backup_dir: Directory for backups before modification
        delete_backups: If True, delete successful backups
        force: Allow potentially destructive operations
        verbose: Show progress and detailed output
        dynamic_op: Optional function for dynamic operation generation
        verify: Verify writes by reading back from disk
    
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
                targeted_fields,
                filters=filters,
                dry_run=dry_run,
                backup_dir=backup_dir,
                delete_backups=delete_backups,
                force=force,
                dynamic_op=dynamic_op,
                verify=verify
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
    ops: FieldOperationsType,
    targeted_fields: List[str],
    *,
    max_workers: Optional[int] = None,
    use_parallel: bool = True,
    verify: bool = True,
    delete_backups: bool = False,
    **kwargs
) -> List[ProcessResultType]:
    """
    Smart dispatcher that chooses between parallel and sequential processing.
    """
    files_list = list(files)
    total_files = len(files_list)
    
    if total_files == 0:
        return []
    
    should_use_parallel = (
        use_parallel and 
        total_files >= Config.MIN_FILES_FOR_PARALLEL and
        max_workers != 1
    )
    
    if should_use_parallel:
        with Config.PROGRESS_LOCK:
            logger.info(f"Using parallel processing with {max_workers or Config.MAX_WORKERS} workers")
            if kwargs.get('verbose'):
                print(f"Processing {total_files} files in parallel...")
        
        return process_files_parallel(
            files_list, ops, targeted_fields,
            max_workers=max_workers, 
            dynamic_op=kwargs.get('dynamic_op'),
            verify=verify,
            delete_backups=delete_backups,
            **kwargs
        )
    else:
        with Config.PROGRESS_LOCK:
            logger.info("Using sequential processing")
            if kwargs.get('verbose'):
                print(f"Processing {total_files} files sequentially...")
        
        results = []
        for i, file_path in enumerate(files_list, 1):
            if kwargs.get('verbose'):
                progress_msg = f"Progress: {i}/{total_files} ({i/total_files*100:.1f}%)"
                print(progress_msg, end='\r' if i < total_files else '\n')
            
            result = process_file(
                str(file_path), ops, targeted_fields,
                filters=kwargs.get('filters'),
                dry_run=kwargs.get('dry_run', False),
                backup_dir=kwargs.get('backup_dir'),
                delete_backups=delete_backups,
                force=kwargs.get('force', False),
                dynamic_op=kwargs.get('dynamic_op'),
                verify=verify
            )
            results.append(result)
            
            if kwargs.get('verbose') and result.get('error'):
                print(f"  ERROR: {result['error']}")
        
        return results

# ---------- File Validation ----------
def validate_file(path: Path) -> Tuple[bool, str]:
    """Comprehensive file validation."""
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
        if not os.access(path, os.W_OK):
            return False, "No write permission"
        
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXT:
            return False, f"Unsupported file extension: {ext}"
        
        return True, "Valid"
    except Exception as e:
        return False, f"Validation error: {e}"

def create_backup_path(original_path: Path, backup_dir: Path) -> Path:
    """Create a secure backup path with collision handling."""
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

def verify_written(path: Path, expected_fields: FieldValuesType) -> Dict[str, bool]:
    """Verify that fields were written correctly."""
    try:
        with SimpleMusic.managed(path) as sm:
            reloaded = sm.read_fields()
            results = {}
            
            for field, expected in expected_fields.items():
                expected_norm = FieldOperations.normalize_values(field, expected)
                got_norm = FieldOperations.normalize_values(field, reloaded.get(field, []))
                
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
def _validate_and_read_file(path: Path, read_mode: str = 'canonical') -> Tuple[bool, str, Optional[FieldValuesType]]:
    """Validate file and read original fields."""
    ext = path.suffix.lower()
    
    is_valid, validation_msg = validate_file(path)
    if not is_valid:
        return False, f'file validation failed: {validation_msg}', None
    
    try:
        with SimpleMusic.managed(path) as sm:
            orig = sm.read_fields(mode=read_mode)
        return True, "", orig
    except Exception as e:
        return False, f'file error: {e}', None

def _apply_filters(filters: List[FilterType], orig: FieldValuesType) -> bool:
    """Apply all filters to fields."""
    if not filters:
        return True
        
    for (field, pattern, regex_flag) in filters:
        if not apply_filter(field, pattern, regex_flag, orig):
            return False
    return True

def _create_backup(path: Path, backup_dir: Optional[Path]) -> Tuple[Optional[Path], Optional[str]]:
    """Create backup of file with retry on race condition."""
    if not backup_dir:
        return None, None
        
    try:
        backup_dir_path = Path(backup_dir)
        backup_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Retry loop to handle race conditions
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
    """Write new fields to file."""
    try:
        with SimpleMusic.managed(path) as sm_write:
            sm_write.write_fields(new_fields)
        with Config.PROGRESS_LOCK:
            logger.info(f"Successfully wrote metadata to: {path}")
        return True, None
    except Exception as e:
        return False, f'write failed: {e}'

def _restore_from_backup(path: Path, backup_path: Optional[Path]) -> bool:
    """Restore file from backup."""
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
    """Clean up backup file if appropriate."""
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
                ops: FieldOperationsType, 
                targeted_fields: List[str], 
                filters: Optional[List[FilterType]] = None,
                dry_run: bool = False, 
                backup_dir: Optional[str] = None, 
                delete_backups: bool = False,
                force: bool = False,
                dynamic_op: Optional[Callable[[str], Any]] = None,
                verify: bool = True) -> ProcessResultType:
    """Process a single file with comprehensive error handling."""
    file_path = Path(path)
    ext = file_path.suffix.lower()
    
    # Check extension (fast, no I/O)
    if ext not in SUPPORTED_EXT:
         return {
            'path': str(file_path), 
            'error': f"Unsupported file extension: {ext}", 
            'passed': False, 
            'ext': ext
        }
    
    try:
        # Use a single context manager to keep file open if possible (or at least centralize handling)
        with SimpleMusic.managed(file_path) as sm:
            # Step 1: Read original fields
            read_mode = 'extended' if dynamic_op else 'canonical'
            orig = sm.read_fields(mode=read_mode)
            
            # Step 2: Apply filters
            if not _apply_filters(filters or [], orig):
                return {
                    'path': str(file_path), 
                    'skipped': True, 
                    'reason': 'filter not match', 
                    'ext': ext
                }
            
            # Step 3: Compute new fields
            effective_ops = ops.copy()
            effective_targeted_fields = list(targeted_fields)
            
            if dynamic_op:
                for field in orig.keys():
                    if field not in effective_ops:
                        op = dynamic_op(field)
                        if op:
                            effective_ops[field] = op
                            effective_targeted_fields.append(field)
            
            new_fields, changed = compute_new_fields(orig, effective_ops, effective_targeted_fields)
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
                'exception': None
            }
            
            if not any_changed:
                return {**record, 'passed': True, 'note': 'no changes'}
            
            if dry_run:
                return {**record, 'passed': True, 'note': 'dry-run'}
            
            # Step 4: Create backup (requires separate handling since it deals with files on disk)
            # Standard mutagen is usually fine with copying the file while open for reading.
            if backup_dir:
                backup_path, backup_error = _create_backup(file_path, Path(backup_dir))
                if backup_error:
                    return {**record, 'error': backup_error, 'passed': False}
            else:
                backup_path = None
            
            # Step 5: Write new fields (using the SAME SimpleMusic instance)
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
            
            # Step 6: Verify (optional)
            if verify:
                try:
                    record['verified'] = verify_written(file_path, {k: new_fields[k] for k in effective_targeted_fields})
                    record['passed'] = all(record['verified'].values())
                    
                    if not record['passed']:
                        logger.warning(f"Verification failed for {file_path}: {record['verified']}")
                except Exception as e:
                    logger.error(f"Verification process error: {e}")
                    record['passed'] = False
            else:
                record['verified'] = {}
                record['passed'] = True
            
            # Step 7: Cleanup backup
            if record['passed']:
                 _cleanup_backup(backup_path, force, delete_backups)
            else:
                 # If failed, ALWAYS keep backup
                 if backup_path and backup_path.exists():
                     logger.debug(f"Keeping backup due to failure: {backup_path}")
            
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
    """Generator to collect files efficiently without loading all into memory."""
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