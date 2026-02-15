"""Test graceful handling of filesystem permission issues."""

import pytest
import stat
import shutil
from pathlib import Path
from mudio import process_file, overwrite

def test_readonly_file_handling(tmp_path, audio_template):
    """Test that read-only files fail gracefully."""
    test_file = tmp_path / "readonly.mp3"
    
    # Copy the generated template
    test_file.write_bytes(audio_template.read_bytes())
    test_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # Remove write
    
    try:
        result = process_file(
            str(test_file),
            ops={"title": overwrite("title", "New Title")},
            targeted_fields=["title"],
            dry_run=False,
            backup_dir=None
        )
        
        assert result['passed'] is False
        assert 'error' in result
        assert any(word in result['error'].lower() 
                  for word in ['permission', 'read-only', 'write', 'access'])
        
    finally:
        # Restore permissions for cleanup
        test_file.chmod(stat.S_IRWXU)

def test_readonly_backup_dir_handling(tmp_path, audio_template):
    """Test that read-only backup directory fails gracefully."""
    test_file = tmp_path / "test.mp3"
    
    # Copy the generated template
    test_file.write_bytes(audio_template.read_bytes())
    
    # Create read-only backup dir
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # No write permission
    
    try:
        result = process_file(
            str(test_file),
            ops={"title": overwrite("title", "New Title")},
            targeted_fields=["title"],
            dry_run=False,
            backup_dir=str(backup_dir)
        )
        
        assert result['passed'] is False
        assert 'error' in result
        
        error_lower = result['error'].lower()
        assert any(keyword in error_lower for keyword in [
            'backup', 'permission', 'write', 'create', 'directory', 
            'failed', 'error', 'access'
        ]), f"Error didn't match expected keywords: {result['error']}"
        
    finally:
        # Restore permissions for cleanup
        backup_dir.chmod(stat.S_IRWXU)
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)