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
    operations: FieldOperationsType,
    fields: List[str],
    *,
    recursive: bool = False,
    extensions: Optional[List[str]] = None,
    filters: Optional[List[FilterType]] = None,
    dry_run: bool = False,
    backup_dir: Optional[Union[str, Path]] = None,
    force: bool = False,
    verbose: bool = False,
    max_workers: Optional[int] = None,
    use_parallel: bool = True,
    verify: bool = True
) -> Dict[str, any]:
    """
    Process multiple audio files with a clean Python API.
    
    Supports parallel processing for large batches, automatically using multiple 
    threads when beneficial unless disabled.
    
    Args:
        path: Directory or file path to process
        operations: Dict mapping field names to operation functions
        fields: List of field names to target
        recursive: If True, search subdirectories
        extensions: List of file extensions to include (e.g. ['.mp3', '.flac'])
        filters: List of (field, pattern, is_regex) tuples to filter files
        dry_run: If True, show changes without writing
        backup_dir: Directory to store backups before modifying files
        force: If True, allow potentially destructive operations
        verbose: If True, show detailed progress
        max_workers: Number of parallel workers (None = auto)
        use_parallel: If False, disable parallel processing
        verify: If True, verify writes by reading back metadata
    
    Returns:
        Dict with keys: processed, successful, failed, skipped, results
    
    Examples:
        Basic usage - set all titles in a directory:
        >>> from mudio.batch import process_batch
        >>> from mudio.operations import overwrite
        >>> ops = {'title': overwrite('title', 'New Title')}
        >>> result = process_batch('/music', ops, ['title'])
        >>> print(f"Processed {result['successful']} files")
        
        Set multiple fields with backup:
        >>> ops = {
        ...     'artist': overwrite('artist', 'Artist Name'),
        ...     'album': overwrite('album', 'Album Name')
        ... }
        >>> result = process_batch(
        ...     '/music', 
        ...     ops, 
        ...     ['artist', 'album'],
        ...     backup_dir='/backups',
        ...     recursive=True
        ... )
        
        Filter and process only specific files:
        >>> from mudio.operations import append
        >>> ops = {'genre': append('genre', 'Rock', delimiter=';')}
        >>> filters = [('artist', 'Beatles', False)]
        >>> result = process_batch(
        ...     '/music',
        ...     ops,
        ...     ['genre'],
        ...     filters=filters,
        ...     extensions=['.mp3', '.flac']
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
        fields,
        max_workers=max_workers or 0,
        use_parallel=use_parallel,
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
def set_fields(
    path: Union[str, Path],
    fields: Dict[str, Union[str, List[str]]],
    **kwargs
) -> Dict[str, any]:
    """
    Convenience function to set multiple fields at once.
    
    This function provides a simpler interface than process_batch for the common
    case of overwriting metadata fields. It automatically creates the necessary
    operations internally.
    
    Args:
        path: Directory or file path to process
        fields: Dict mapping field names to values (str or List[str])
        **kwargs: Additional arguments passed to process_batch (e.g., recursive, dry_run)
    
    Returns:
        Dict with keys: processed, successful, failed, skipped, results
    
    Examples:
        Set basic metadata for all files in a directory:
        >>> from mudio.batch import set_fields
        >>> result = set_fields(
        ...     '/music',
        ...     fields={
        ...         'artist': 'The Beatles',
        ...         'album': 'Abbey Road',
        ...         'date': '1969'
        ...     }
        ... )
        
        Set multiple values for a field:
        >>> result = set_fields(
        ...     '/music/song.mp3',
        ...     fields={'genre': ['Rock', 'Classic Rock']}
        ... )
        
        Recursive processing with dry-run:
        >>> result = set_fields(
        ...     '/music',
        ...     fields={'albumartist': 'Various Artists'},
        ...     recursive=True,
        ...     dry_run=True
        ... )
        >>> print(f"Would modify {result['processed']} files")
    """
    from .operations import overwrite
    
    operations = {}
    field_list = []
    
    for field_name, value in fields.items():
        if field_name not in CANONICAL_FIELDS:
            raise ValueError(f"Invalid field: {field_name}")
        
        operations[field_name] = overwrite(field_name, value)
        field_list.append(field_name)
    
    return process_batch(path, operations, field_list, **kwargs)