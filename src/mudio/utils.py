"""
Utility functions and configuration for mudio.
"""

import os
import sys
import re
import logging
import hashlib
from pathlib import Path
from typing import List, Any
from logging.handlers import RotatingFileHandler
from threading import Lock

# ---------- Constants ----------
EXIT_CODE_SUCCESS = 0
EXIT_CODE_ERROR = 1
EXIT_CODE_USAGE = 2
EXIT_CODE_NO_FILES = 3
EXIT_CODE_PERMISSION = 4
EXIT_CODE_DISK_FULL = 5
EXIT_CODE_INTERRUPTED = 130

# ---------- Configuration ----------
class Config:
    """Configuration management with validation."""
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    BACKUP_RETRY_LIMIT = 10
    DEFAULT_ENCODING = 'utf-8'
    CHUNK_SIZE = 64 * 1024  # 64KB for file operations
    
    # Multithreading configuration
    # Default: CPU count + 4, max 32 to safely handle IO-bound and CPU-bound mix
    MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4)
    MIN_FILES_FOR_PARALLEL = 10
    PROGRESS_LOCK = Lock()

    DEFAULT_SCHEMA = 'extended'
    DEFAULT_NAMESPACE = 'com.apple.iTunes'
    
    @classmethod
    def validate(cls) -> None:
        """Validate configuration values."""
        if cls.MAX_FILE_SIZE <= 0:
            raise ValueError("MAX_FILE_SIZE must be positive")
        if cls.BACKUP_RETRY_LIMIT <= 0:
            raise ValueError("BACKUP_RETRY_LIMIT must be positive")
        if cls.CHUNK_SIZE <= 0:
            raise ValueError("CHUNK_SIZE must be positive")
        if cls.MAX_WORKERS <= 0:
            raise ValueError("MAX_WORKERS must be positive")
        if cls.MIN_FILES_FOR_PARALLEL <= 0:
            raise ValueError("MIN_FILES_FOR_PARALLEL must be positive")
        if cls.DEFAULT_SCHEMA not in ('canonical', 'extended', 'raw'):
            raise ValueError(f"Invalid DEFAULT_SCHEMA: {cls.DEFAULT_SCHEMA}")
        if not cls.DEFAULT_NAMESPACE:
            raise ValueError("DEFAULT_NAMESPACE cannot be empty")
    
    @classmethod
    def load_from_env(cls) -> None:
        """Load configuration from environment variables, updating class attributes."""
        if os.getenv('MUDIO_MAX_FILE_SIZE'):
            cls.MAX_FILE_SIZE = int(os.getenv('MUDIO_MAX_FILE_SIZE'))
        if os.getenv('MUDIO_BACKUP_RETRY_LIMIT'):
            cls.BACKUP_RETRY_LIMIT = int(os.getenv('MUDIO_BACKUP_RETRY_LIMIT'))
        if os.getenv('MUDIO_MAX_WORKERS'):
            cls.MAX_WORKERS = int(os.getenv('MUDIO_MAX_WORKERS'))
        if os.getenv('MUDIO_MIN_PARALLEL'):
            cls.MIN_FILES_FOR_PARALLEL = int(os.getenv('MUDIO_MIN_PARALLEL'))
        if os.getenv('MUDIO_SCHEMA'):
            cls.DEFAULT_SCHEMA = os.getenv('MUDIO_SCHEMA')
        if os.getenv('MUDIO_NAMESPACE'):
            cls.DEFAULT_NAMESPACE = os.getenv('MUDIO_NAMESPACE')
        cls.validate()

# Thread-safe output helpers
def print_progress_safe(message: str, **kwargs) -> None:
    """Thread-safe print function for progress updates."""
    with Config.PROGRESS_LOCK:
        print(message, **kwargs)

# ---------- Logging Setup ----------
def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rotation and proper formatting."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create logs directory if it doesn't exist
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Use rotating file handler
    file_handler = RotatingFileHandler(
        log_dir / 'mudio.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            file_handler
        ]
    )

# ---------- Small Helpers ----------
def join_for_printing(lst: List[str]) -> str:
    """Join list for display, showing '(none)' for empty lists."""
    return '(none)' if not lst else '; '.join(lst)

def safe_unicode_path(path: Any) -> str:
    """Convert path to unicode, handling encoding issues."""
    if isinstance(path, bytes):
        try:
            return path.decode(Config.DEFAULT_ENCODING)
        except UnicodeDecodeError:
            try:
                return path.decode('latin-1')
            except UnicodeDecodeError:
                return path.decode('utf-8', errors='replace')
    return str(path)

def safe_regex_pattern(pattern: str, is_regex: bool = False) -> str:
    """Safely compile regex pattern with proper error handling."""
    if not is_regex:
        return re.escape(pattern)
    
    try:
        # Test if pattern compiles
        re.compile(pattern)
        return pattern
    except re.error as e:
        # Use repr() to sanitize the pattern in error message (prevents terminal escape injection)
        raise ValueError(f"Invalid regex pattern {repr(pattern)}: {e}")

def get_file_hash(file_path: Path) -> str:
    """Calculate file hash for verification."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(Config.CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
