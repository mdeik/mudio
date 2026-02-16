"""High-level Python API for batch processing files with mudio."""

from pathlib import Path
from typing import Dict, List, Optional, Callable, Union
import logging

from .core import CANONICAL_FIELDS
from .processor import collect_files_generator, process_files
from .operations import FieldOperationsType, FilterType

logger = logging.getLogger(__name__)

# Core batch processing logic
def process_batch(
    path: Union[str, Path],
    operations: List[FieldOperationsType],
    recursive: bool = False,
    extensions: Optional[List[str]] = None,
    filters: Optional[List[FilterType]] = None,
    dry_run: bool = False,
    backup_dir: Optional[Union[str, Path]] = None,
    force: bool = False,
    verbose: bool = False,
    max_workers: Optional[int] = None,
    verify: bool = True
) -> Dict[str, any]:
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
        force: If True, allow potentially destructive operations
        verbose: If True, show detailed progress
        max_workers: Number of parallel workers (None = auto)
        verify: If True, verify writes by reading back metadata
    
    Returns:
        Dict with keys: processed, successful, failed, skipped, results
    
    Examples:
        Basic usage - set all titles in a directory:
        >>> from mudio.batch import process_batch
        >>> from mudio.operations import write
        >>> ops = [write('title', 'New Title')]
        >>> result = process_batch('/music', ops)
        >>> print(f"Processed {result['successful']} files")
        
        Set multiple fields with backup:
        >>> ops = [
        ...     write('artist', 'Artist Name'),
        ...     write('album', 'Album Name')
        ... ]
        >>> result = process_batch(
        ...     '/music', 
        ...     ops, 
        ...     backup_dir='/backups',
        ...     recursive=True
        ... )
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
        force=force,
        verbose=verbose,
        verify=verify
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

# Convenience wrappers
def write_fields(
    path: Union[str, Path],
    fields: Dict[str, Union[str, List[str]]],
    **kwargs
) -> Dict[str, any]:
    """
    Convenience function to set multiple fields at once.
    """
    from .operations import write
    
    operations = []
    
    for field_name, value in fields.items():
        if field_name not in CANONICAL_FIELDS:
            raise ValueError(f"Invalid field: {field_name}")
        
        operations.append(write(field_name, value))
    
    return process_batch(path, operations, **kwargs)