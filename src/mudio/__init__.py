"""mudio – music metadata made friendly."""

__version__ = "0.1.0"

from .core import SimpleMusic, CANONICAL_FIELDS, SUPPORTED_EXT, managed_simple_music
from .utils import Config
from .operations import (
    FieldOperations,
    write,
    find_replace,
    append,
    prefix,
    enlist,
    delist,
    clear,
    delete,
    compute_new_fields,
    apply_filter
)
from .processor import process_file, process_files, validate_file, verify_written, collect_files_generator, process_batch, write_fields

__all__ = [
    "SimpleMusic", 
    "CANONICAL_FIELDS", 
    "SUPPORTED_EXT", 
    "managed_simple_music",
    "Config",
    "FieldOperations",
    "write",
    "find_replace",
    "append",
    "prefix",
    "enlist",
    "delist",
    "clear",
    "delete",
    "compute_new_fields",
    "apply_filter",
    "process_file",
    "process_files",
    "validate_file",
    "verify_written",
    "collect_files_generator",
    "process_batch",
    "write_fields"
]