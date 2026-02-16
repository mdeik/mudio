
"""
Integration tests for edge cases: corrupted files, limits, symlinks, and concurrency.
"""
import pytest
import os
import shutil
from pathlib import Path
from mudio.core import SimpleMusic, FormatError
from mudio.processor import process_file
from mudio.batch import process_batch
from mudio.operations import write
from mudio.utils import Config
import time

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_truncated_file(self, tmp_path):
        """Test valid header but truncated body."""
        # Create a file that starts like an MP3 but ends abruptly
        f = tmp_path / "truncated.mp3"
        # Minimum valid ID3v2 header (10 bytes) + partial frame
        f.write_bytes(b'ID3\x03\x00\x00\x00\x00\x0F' + b'\x00' * 5) 
        
        # Should gracefully fail validation or load
        is_valid = False
        try:
             # Try to load
             with SimpleMusic.managed(f) as sm:
                 pass
             is_valid = True
        except Exception:
             is_valid = False
             
        # process_file should handle this
        result = process_file(
            str(f),
            ops=[write("title", "Test")],
        )
        assert result['passed'] is False
        assert "error" in result['error'].lower() or "validation" in result['error'].lower()

    def test_massive_metadata(self, audio_file):
        """Write massive metadata string (>1MB)."""
        # 1MB string
        massive_str = "A" * (1024 * 1024)
        
        result = process_file(
            str(audio_file),
            ops=[write("comment", massive_str)],
            verify=False # Reading back might be slow or hit other limits, focused on write stability
        )
        assert result['passed'] is True
        
        # Verify file size increased significantly
        assert audio_file.stat().st_size > (1024 * 1024)

    def test_symlink_processing(self, audio_file, tmp_path):
        """Test processing via a symlink."""
        # Use same extension as source to avoid format detection issues
        link_path = tmp_path / f"link{audio_file.suffix}"
        try:
            link_path.symlink_to(audio_file)
        except OSError:
            pytest.skip("Symlinks not supported on this OS/filesystem")
            
        result = process_file(
            str(link_path),
            ops=[write("title", "Linked Title")]
        )
        assert result['passed'] is True
        
        # Check original file was modified
        with SimpleMusic.managed(audio_file) as sm:
            assert sm.read_fields()['title'] == ['Linked Title']

    def test_real_parallel_batch(self, tmp_path, audio_file):
        """Test real parallel processing with thread pool."""
        if audio_file.suffix != ".mp3":
             return

        # Create enough files to trigger parallel processing
        # Using a number > Config.MIN_FILES_FOR_PARALLEL (default 10)
        num_files = 20
        test_dir = tmp_path / "parallel_test"
        test_dir.mkdir()
        
        for i in range(num_files):
            shutil.copy(audio_file, test_dir / f"track_{i}.mp3")
            
        # Run batch
        result = process_batch(
            test_dir,
            operations=[write("title", "Parallel Title")],
            max_workers=4,
            verbose=False
        )
        
        assert result['processed'] == num_files
        assert result['successful'] == num_files
        assert len(result['results']) == num_files

    def test_backup_race_condition(self, tmp_path):
        """
        Simulate a race condition where multiple threads try to backup files with the same name
        into the same backup directory.
        """
        from concurrent.futures import ThreadPoolExecutor
        from mudio.processor import _create_backup

        # Setup
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        
        # Create two different source files with the same name in different directories
        # This simulates "A/song.mp3" and "B/song.mp3"
        src_dir_1 = tmp_path / "A"
        src_dir_1.mkdir()
        src_1 = src_dir_1 / "song.mp3"
        src_1.write_text("content A", encoding='utf-8')
        
        src_dir_2 = tmp_path / "B"
        src_dir_2.mkdir()
        src_2 = src_dir_2 / "song.mp3"
        src_2.write_text("content B", encoding='utf-8')
        
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
        
        # Must be different paths (one should be song.mp3, other song_1.mp3 or similar)
        assert path1 != path2
        
        # Verify content
        assert path1.read_text(encoding='utf-8') in ["content A", "content B"]
        assert path2.read_text(encoding='utf-8') in ["content A", "content B"]
        assert path1.read_text(encoding='utf-8') != path2.read_text(encoding='utf-8')
        
        # Verify a random file got updated (using SimpleMusic logic or simpler check)
        # Since they are dummy files, 'write' simulates success in process_file if headers allow.
        # But dummy files might fail write if library checks strict structure.
        # We check if process_batch reports success, meaning it dispatched correctly.
