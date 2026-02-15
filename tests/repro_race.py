
import pytest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import time
import os
from mudio.processor import _create_backup

def test_backup_race_condition(tmp_path):
    """
    Simulate a race condition where multiple threads try to backup files with the same name
    into the same backup directory.
    """
    
    # Setup
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    
    # Create two different source files with the same name in different directories
    # This simulates "A/song.mp3" and "B/song.mp3"
    src_dir_1 = tmp_path / "A"
    src_dir_1.mkdir()
    src_1 = src_dir_1 / "song.mp3"
    src_1.write_text("content A")
    
    src_dir_2 = tmp_path / "B"
    src_dir_2.mkdir()
    src_2 = src_dir_2 / "song.mp3"
    src_2.write_text("content B")
    
    # Function to run in parallel
    def perform_backup(src_path):
        return _create_backup(src_path, backup_dir)

    # Run in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(perform_backup, src_1)
        f2 = executor.submit(perform_backup, src_2)
        
        res1 = f1.result()
        res2 = f2.result()
        
    # Analyze results
    path1, err1 = res1
    path2, err2 = res2
    
    assert err1 is None
    assert err2 is None
    
    assert path1 is not None
    assert path2 is not None
    
    # Must be different paths
    assert path1 != path2
    
    # Verify content
    assert path1.read_text() in ["content A", "content B"]
    assert path2.read_text() in ["content A", "content B"]
    assert path1.read_text() != path2.read_text()
