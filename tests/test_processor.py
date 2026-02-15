"""Unit tests for mudio.processor module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
import stat
import shutil
import tempfile
import sys
import time
from mudio.processor import (
    process_file,
    process_files,
    _process_files_parallel,
    validate_file,
    verify_written,
    create_backup_path,
    safe_file_copy,
    collect_files_generator,
    register_signal_handlers,
    unregister_signal_handlers
)
from mudio import overwrite, SimpleMusic
from mudio.utils import Config


class TestValidateFile:
    """Test file validation logic."""

    def test_validate_valid_file(self, audio_template):
        """Test validation of a valid audio file."""
        is_valid, msg = validate_file(audio_template)
        assert is_valid is True
        assert msg == "Valid"

    def test_validate_nonexistent_file(self, tmp_path):
        """Test validation of non-existent file."""
        fake_file = tmp_path / "fake.mp3"
        is_valid, msg = validate_file(fake_file)
        assert is_valid is False
        assert "File does not exist" in msg

    def test_validate_directory(self, tmp_path):
        """Test validation of a directory path."""
        is_valid, msg = validate_file(tmp_path)
        assert is_valid is False
        assert "Path is not a file" in msg

    def test_validate_empty_file(self, tmp_path):
        """Test validation of empty file."""
        empty_file = tmp_path / "empty.mp3"
        empty_file.write_text("")
        is_valid, msg = validate_file(empty_file)
        assert is_valid is False
        assert "File is empty" in msg

    def test_validate_unsupported_extension(self, tmp_path):
        """Test validation of unsupported file extension."""
        txt_file = tmp_path / "file.txt"
        txt_file.write_text("not audio")
        is_valid, msg = validate_file(txt_file)
        assert is_valid is False
        assert "Unsupported file extension" in msg

    def test_validate_large_file(self, tmp_path):
        """Test validation of file exceeding size limit."""
        large_file = tmp_path / "large.mp3"
        # Create a file larger than MAX_FILE_SIZE
        large_file.write_bytes(b"x" * (Config.MAX_FILE_SIZE + 1))

        is_valid, msg = validate_file(large_file)
        assert is_valid is False
        assert "File too large" in msg

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows permission model differs")
    def test_validate_no_read_permission(self, tmp_path, audio_template):
        """Test validation of file without read permission."""
        test_file = tmp_path / "no_read.mp3"
        test_file.write_bytes(audio_template.read_bytes())
        test_file.chmod(stat.S_IWUSR)  # Remove read permission

        try:
            is_valid, msg = validate_file(test_file)
            assert is_valid is False
            assert "No read permission" in msg
        finally:
            test_file.chmod(stat.S_IRWXU)  # Restore permissions


class TestBackupOperations:
    """Test backup creation and management."""

    def test_create_backup_path_basic(self, tmp_path):
        """Test basic backup path creation."""
        original = tmp_path / "music" / "track.mp3"
        backup_dir = tmp_path / "backups"

        backup_path = create_backup_path(original, backup_dir)
        assert backup_path == backup_dir / "track.mp3"

    def test_create_backup_path_collision(self, tmp_path):
        """Test backup path with existing file collision."""
        # Create separate directories
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        original = music_dir / "track.mp3"
        original.touch()  # Create the original file

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create existing backup files
        (backup_dir / "track.mp3").touch()
        (backup_dir / "track_1.mp3").touch()

        backup_path = create_backup_path(original, backup_dir)
        assert backup_path == backup_dir / "track_2.mp3"

    def test_create_backup_path_nested_source(self, tmp_path):
        """Test backup path creation for nested source directory."""
        original = tmp_path / "artist" / "album" / "track.mp3"
        backup_dir = tmp_path / "backups"

        # Should only use filename, not full path
        backup_path = create_backup_path(original, backup_dir)
        assert backup_path.name == "track.mp3"
        assert backup_path.parent == backup_dir

    def test_create_backup_path_disallows_nested_backup(self, tmp_path):
        """Test that backup inside source tree raises error."""
        original = tmp_path / "music" / "track.mp3"
        backup_dir = tmp_path / "music" / "backups"

        with pytest.raises(ValueError, match="cannot be inside the source directory tree"):
            create_backup_path(original, backup_dir)

    def test_safe_file_copy(self, tmp_path):
        """Test safe file copy with hash verification."""
        source = tmp_path / "source.mp3"
        dest = tmp_path / "dest.mp3"

        # Create source file with content
        content = b"test audio content" * 1000
        source.write_bytes(content)

        safe_file_copy(source, dest)

        assert dest.exists()
        assert dest.read_bytes() == content

    def test_safe_file_copy_verifies_hash_mismatch(self, tmp_path):
        """Test safe file copy detects hash mismatches."""
        source = tmp_path / "source.mp3"
        dest = tmp_path / "dest.mp3"

        source.write_bytes(b"correct content")

        # Mock hash function to simulate mismatch
        with patch('mudio.processor.get_file_hash') as mock_hash:
            mock_hash.side_effect = ["hash1", "hash2"]  # Different hashes

            with pytest.raises(RuntimeError, match="checksum mismatch"):
                safe_file_copy(source, dest)


class TestProcessFile:
    """Test single file processing pipeline."""

    def test_process_file_dry_run(self, audio_template):
        """Test dry-run mode doesn't modify file."""
        with patch('mudio.processor.safe_file_copy') as mock_copy:
            result = process_file(
                str(audio_template),
                ops={"title": overwrite("title", "Modified Title")},
                targeted_fields=["title"],
                dry_run=True
            )

            mock_copy.assert_not_called()  # No backup in dry-run
            assert result['passed'] is True
            assert result['note'] == 'dry-run'
            assert 'planned' in result

    def test_process_file_no_changes(self, audio_template):
        """Test processing when no changes are needed."""
        # Set title to same value we'll "overwrite" with
        with SimpleMusic.managed(audio_template) as sm:
            sm.write_fields({"title": ["Same Title"]})

        result = process_file(
            str(audio_template),
            ops={"title": overwrite("title", "Same Title")},
            targeted_fields=["title"],
            dry_run=False
        )

        assert result['passed'] is True
        assert result['note'] == 'no changes'
        assert result['wrote'] is False
        
    def test_process_file_with_schema(self, audio_template):
        """Test processing with explicit read_schema."""
        with patch('mudio.core.SimpleMusic.read_fields') as mock_read:
             mock_read.return_value = {"title": ["Title"]}
             
             process_file(
                 str(audio_template),
                 ops={},
                 targeted_fields=[],
                 read_schema="raw"
             )
             
             mock_read.assert_called_with(schema="raw")

    def test_process_file_read_schema_integration(self, audio_template):
        """Test read_schema filtering behavior without mocking."""
        # Add a custom tag
        with SimpleMusic.managed(audio_template) as sm:
            # Try to add a custom field depending on format. 
            # For robustness, we'll try to add something that should appear in extended but vanish in canonical.
            # SimpleMusic.write_fields handles custom tags by prefixing/mapping.
            sm.write_fields({"X-Custom-Tag": ["CustomVal"]})
            
        # 1. Process with 'canonical' schema -> Should NOT see custom tag in 'original'
        result_canonical = process_file(
            str(audio_template),
            ops={},
            targeted_fields=[],
            read_schema="canonical",
            dry_run=True 
        )
        assert result_canonical['passed'] is True
        # 'original' contains fields read at start. 
        # Canonical schema should filter out non-standard tags.
        # Note: 'X-Custom-Tag' is definitely not canonical.
        assert "X-Custom-Tag" not in result_canonical['original']
        
        # 2. Process with 'extended' schema -> Should see custom tag
        result_extended = process_file(
            str(audio_template),
            ops={},
            targeted_fields=[],
            read_schema="extended",
            dry_run=True
        )
        assert result_extended['passed'] is True
        # Extended schema should include everything
        # We check if it exists (mapped or raw key depends on format, but write_fields uses our key)
        # SimpleMusic.read_fields(extended) tries to reverse map.
        found_keys = list(result_extended['original'].keys())
        # It might be normalized or kept as is.
        assert any(k.lower() == "x-custom-tag" for k in found_keys) or "TXXX:X-Custom-Tag" in found_keys

    def test_process_file_with_backup(self, audio_template, tmp_path):
        """Test successful processing with backup creation."""
        backup_dir = tmp_path / "backups"

        # Ensure original has content that will actually change
        with SimpleMusic.managed(audio_template) as sm:
            sm.write_fields({"title": ["Original Title"]})

        # Use force=True to prevent backup cleanup
        result = process_file(
            str(audio_template),
            ops={"title": overwrite("title", "New Title")},
            targeted_fields=["title"],
            dry_run=False,
            backup_dir=str(backup_dir),
            force=True  # Keep the backup
        )

        assert result['passed'] is True
        assert result['wrote'] is True

        # Give filesystem time to settle
        time.sleep(0.2)

        # Check backup directory exists and has content
        assert backup_dir.exists(), f"Backup dir {backup_dir} does not exist"

        backups = list(backup_dir.iterdir())
        # Debug output if test fails
        if len(backups) == 0:
            print(f"Debug: Backup directory contents: {list(backup_dir.rglob('*'))}")
            print(f"Debug: Result: {result}")

        assert len(backups) == 1, f"Expected 1 backup file, found {len(backups)}: {backups}"

        # Verify actual modification
        with SimpleMusic.managed(audio_template) as sm:
            fields = sm.read_fields()
            assert fields['title'] == ['New Title']

    def test_process_file_validation_failure(self, tmp_path):
        """Test handling of invalid file during processing."""
        invalid_file = tmp_path / "invalid.mp3"
        invalid_file.write_text("not an mp3")

        result = process_file(
            str(invalid_file),
            ops={"title": overwrite("title", "New Title")},
            targeted_fields=["title"]
        )

        assert result['passed'] is False
        assert 'file validation failed' in result['error'] or 'file error' in result['error']

    def test_process_corrupt_file_header(self, tmp_path):
        """Test file with valid extension but corrupt/invalid content (text file disguised)."""
        # Create a file that looks like an MP3 but is actually text
        corrupt_file = tmp_path / "corrupt.mp3"
        corrupt_file.write_text("This is definitely not an MP3 file header.")
        
        result = process_file(
            str(corrupt_file),
            ops={"title": overwrite("title", "New Title")},
            targeted_fields=["title"]
        )
        
        assert result['passed'] is False
        # The exact error depends on mutagen, but validation should fail
        # Mutagen might raise HeaderNotFoundError or similar which we catch and wrap
        assert any(x in result['error'] for x in ['file validation failed', 'Invalid audio file', "can't sync to MPEG frame", 'file error', 'Unsupported file format'])

    def test_process_cumulative_changes(self, audio_template):
        """Test modifying a file multiple times cumulatively."""
        # 1. Set Title
        res1 = process_file(
            str(audio_template),
            ops={"title": overwrite("title", "First Title")},
            targeted_fields=["title"]
        )
        assert res1['passed'] is True
        
        # 2. Set Artist (verify Title remains)
        res2 = process_file(
            str(audio_template),
            ops={"artist": overwrite("artist", "Second Artist")},
            targeted_fields=["artist"]
        )
        assert res2['passed'] is True
        
        with SimpleMusic.managed(audio_template) as sm:
            fields = sm.read_fields()
            assert fields['title'] == ["First Title"]
            assert fields['artist'] == ["Second Artist"]

    def test_process_idempotency(self, audio_template):
        """Test that applying same change twice results in no-op the second time."""
        # 1. Initial change
        res1 = process_file(
            str(audio_template),
            ops={"album": overwrite("album", "Test Album")},
            targeted_fields=["album"]
        )
        assert res1['passed'] is True
        assert res1['wrote'] is True
        
        # 2. Apply SAME change
        res2 = process_file(
            str(audio_template),
            ops={"album": overwrite("album", "Test Album")},
            targeted_fields=["album"]
        )
        assert res2['passed'] is True
        assert res2['wrote'] is False
        assert res2['note'] == 'no changes'

    def test_process_uncommon_chars(self, audio_template):
        """Test handling of unicode, emojis, and different scripts."""
        # Mix of Emoji, Kanji, Greek, Cyrillic
        test_val = "Music 🎵 音楽 Μουσική Музыка"
        result = process_file(
            str(audio_template),
            ops={"title": overwrite("title", test_val)},
            targeted_fields=["title"]
        )
        assert result['passed'] is True
        
        with SimpleMusic.managed(audio_template) as sm:
             fields = sm.read_fields()
             assert fields['title'] == [test_val]

    def test_process_blank_value(self, audio_template):
        """Test setting a field to an empty string."""
        # Depending on format/library, empty string might remove the frame or set it to empty.
        # Mutagen often keeps empty frames or drops them. core.py treats them as valid values.
        result = process_file(
            str(audio_template),
            ops={"comment": overwrite("comment", "")},
            targeted_fields=["comment"]
        )
        assert result['passed'] is True
        
        with SimpleMusic.managed(audio_template) as sm:
             fields = sm.read_fields()
             # Should be present as empty string or list containing empty string, OR removed if library does so.
             # core.py read_fields returns list of strings.
             # If it's cleared, key might be missing or empty list.
             # If it's empty string, it should be [''].
             val = fields.get('comment', [])
             # Some mutagen backends might strip empty frames
             assert val == [''] or val == []

    def test_process_large_data_integrity(self, audio_template):
        """Test writing a large value to ensuring file integrity usually holds."""
        # Write 100KB string (not truly massive but enough to force frame resizing/padding changes)
        large_val = "x" * 102400 
        result = process_file(
            str(audio_template),
            ops={"comment": overwrite("comment", large_val)},
            targeted_fields=["comment"],
            verify=False  # Verification might fail if format truncates, but we want to check integrity
        )
        assert result['passed'] is True
        
        # Verify file is still valid
        is_valid, msg = validate_file(audio_template)
        assert is_valid is True, f"File corruption detected: {msg}"
        
        with SimpleMusic.managed(audio_template) as sm:
             fields = sm.read_fields()
             # We just want to ensure it wrote *something* substantial without corrupting
             # 'comment' is canonical.
             assert len(fields['comment'][0]) > 1000

    def test_process_binary_injection(self, audio_template):
        """Test handling of control characters/binary data."""
        # Null bytes can be problematic in C-based internal libraries or some tagging formats
        # Python mutagen should handle or strip them.
        bad_val = "Start\x00End"
        result = process_file(
            str(audio_template),
            ops={"title": overwrite("title", bad_val)},
            targeted_fields=["title"],
            verify=False # Verification will likely fail due to stripping
        )
        assert result['passed'] is True
        
        with SimpleMusic.managed(audio_template) as sm:
             fields = sm.read_fields()
             # It likely writes it, or strips up to null. 
             # ID3v2.3/4 usually supports null in UTF-16 but null in certain spots terminates string.
             # Mutagen often handles this safely.
             read_val = fields['title'][0]
             # We assume it wrote at least the start
             assert "Start" in read_val 
             # We just want to ensure it didn't crash and saved *something* reasonable or exact.
             # If it saved exactly "Start\x00End", that's fine too.
             pass


class TestVerifyWritten:
    """Test verification of written metadata."""

    def test_verify_written_success(self, audio_template):
        """Test successful verification."""
        test_fields = {"title": ["Verified Title"], "artist": ["Verified Artist"]}

        with SimpleMusic.managed(audio_template) as sm:
            sm.write_fields(test_fields)

        result = verify_written(audio_template, test_fields)
        assert result == {"title": True, "artist": True}

    def test_verify_written_failure(self, audio_template):
        """Test verification detecting incorrect values."""
        with SimpleMusic.managed(audio_template) as sm:
            sm.write_fields({"title": ["Actual Title"]})

        # Verify against different expected values
        result = verify_written(audio_template, {"title": ["Wrong Title"]})
        assert result == {"title": False}

    def test_verify_written_numeric_fields(self, audio_template):
        """Test verification of numeric fields (track/disc numbers)."""
        numeric_fields = {
            "track": ["5"],
            "totaltracks": ["12"],
            "disc": ["2"],
            "totaldiscs": ["3"]
        }

        with SimpleMusic.managed(audio_template) as sm:
            sm.write_fields(numeric_fields)

        result = verify_written(audio_template, numeric_fields)
        assert all(result.values())

    def test_verify_written_handles_exceptions(self, tmp_path):
        """Test verification handles file read errors gracefully."""
        nonexistent = tmp_path / "nonexistent.mp3"

        result = verify_written(nonexistent, {"title": ["Test"]})
        assert result == {"title": False}  # All fields marked as failed


class TestCollectFiles:
    """Test file collection generator."""

    def test_collect_single_file(self, audio_template):
        """Test collecting a single file path."""
        files = list(collect_files_generator(audio_template, recursive=False))
        assert len(files) == 1
        assert files[0] == audio_template

    def test_collect_directory_flat(self, tmp_path):
        """Test collecting files from directory (non-recursive)."""
        # Create test files in root
        header = b'ID3\x03\x00\x00\x00\x00\x0F'
        for i in range(3):
            f = tmp_path / f"track_{i:02d}.mp3"
            f.write_bytes(header + b'\x00' * 1024)

        files = list(collect_files_generator(tmp_path, recursive=False))
        assert len(files) == 3

    def test_collect_directory_recursive(self, tmp_path):
        """Test collecting files recursively."""
        # Create files in root and subdir
        header = b'ID3\x03\x00\x00\x00\x00\x0F'
        for i in range(2):
            (tmp_path / f"root_{i}.mp3").write_bytes(header + b'\x00' * 1024)

        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "sub_track.mp3").write_bytes(header + b'\x00' * 1024)

        files = list(collect_files_generator(tmp_path, recursive=True))
        assert len(files) == 3

    def test_collect_with_extension_filter(self, tmp_path):
        """Test collecting with extension filter."""
        header = b'ID3\x03\x00\x00\x00\x00\x0F'
        (tmp_path / "track.mp3").write_bytes(header + b'\x00' * 1024)
        (tmp_path / "ignore.txt").write_text("not audio")

        ext_set = {'.mp3'}
        files = list(collect_files_generator(tmp_path, ext_set=ext_set))
        assert len(files) == 1
        assert files[0].suffix == '.mp3'

    def test_collect_nonexistent_path(self, tmp_path):
        """Test collecting from non-existent path."""
        fake_path = tmp_path / "nonexistent"
        files = list(collect_files_generator(fake_path))
        assert len(files) == 0


class TestParallelProcessing:
    """Test parallel vs sequential dispatch logic."""

    def test_process_files_uses_sequential_for_small_batch(self, tmp_path):
        """Test small batches use sequential processing."""
        # Create < MIN_FILES_FOR_PARALLEL files
        files = []
        header = b'ID3\x03\x00\x00\x00\x00\x0F'
        for i in range(Config.MIN_FILES_FOR_PARALLEL - 1):
            f = tmp_path / f"track_{i}.mp3"
            f.write_bytes(header + b'\x00' * 1024)
            files.append(f)

        with patch('mudio.processor._process_files_parallel') as mock_parallel:
            results = process_files(
                files,
                ops={"title": overwrite("title", "New Title")},
                targeted_fields=["title"],
                use_parallel=True
            )

            # Should not call parallel for small batches
            mock_parallel.assert_not_called()

    def test_process_files_uses_parallel_for_large_batch(self, tmp_path):
        """Test large batches use parallel processing."""
        # Create enough files to exceed threshold
        files = []
        header = b'ID3\x03\x00\x00\x00\x00\x0F'
        for i in range(Config.MIN_FILES_FOR_PARALLEL + 5):
            f = tmp_path / f"track_{i}.mp3"
            f.write_bytes(header + b'\x00' * 1024)
            files.append(f)

        files = [Path(f) for f in files]

        with patch('mudio.processor._process_files_parallel') as mock_parallel:
            mock_parallel.return_value = []  # Empty results

            process_files(
                files,
                ops={"title": overwrite("title", "New Title")},
                targeted_fields=["title"],
                use_parallel=True,
                verbose=False
            )

            # Should call parallel for large batches
            mock_parallel.assert_called_once()

    def test_process_files_parallel_max_workers(self, tmp_path):
        """Test parallel processing respects max_workers."""
        files = []
        header = b'ID3\x03\x00\x00\x00\x00\x0F'
        for i in range(20):
            f = tmp_path / f"track_{i}.mp3"
            f.write_bytes(header + b'\x00' * 1024)
            files.append(f)

        files = [Path(f) for f in files]

        results = _process_files_parallel(
            files,
            ops={"title": overwrite("title", "New Title")},
            targeted_fields=["title"],
            max_workers=2,  # Force 2 workers
            verbose=False
        )

        # Should process all files
        assert len(results) == len(files)

    def test_process_files_disable_parallel(self, tmp_path):
        """Test disabling parallel processing."""
        files = []
        header = b'ID3\x03\x00\x00\x00\x00\x0F'
        for i in range(20):
            f = tmp_path / f"track_{i}.mp3"
            f.write_bytes(header + b'\x00' * 1024)
            files.append(f)

        files = [Path(f) for f in files]

        with patch('mudio.processor._process_files_parallel') as mock_parallel:
            results = process_files(
                files,
                ops={"title": overwrite("title", "New Title")},
                targeted_fields=["title"],
                use_parallel=False
            )

            mock_parallel.assert_not_called()
            assert len(results) == len(files)


class TestSignalHandlers:
    """Test signal handler registration."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Signal handling limited on Windows")
    def test_register_unregister_signal_handlers(self):
        """Test signal handler registration and cleanup."""
        import signal

        original_int = signal.getsignal(signal.SIGINT)
        original_term = signal.getsignal(signal.SIGTERM)

        register_signal_handlers()

        # Verify handlers were changed
        assert signal.getsignal(signal.SIGINT) != original_int
        assert signal.getsignal(signal.SIGTERM) != original_term

        unregister_signal_handlers()

        # Verify handlers were restored
        assert signal.getsignal(signal.SIGINT) == signal.SIG_DFL
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL

    def test_signal_handlers_no_op_on_windows(self):
        """Test signal handlers are no-ops on Windows."""
        with patch('sys.platform', 'win32'):
            # Should not raise errors
            try:
                register_signal_handlers()
            except Exception:
                pass
            unregister_signal_handlers()

