
"""
Integration tests for the CLI.
"""
import pytest
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from mudio.cli import main, build_operations_from_args
from mudio.core import SimpleMusic
from mudio.utils import (
    EXIT_CODE_USAGE, 
    EXIT_CODE_PERMISSION, 
    EXIT_CODE_INTERRUPTED, 
    EXIT_CODE_ERROR, 
    EXIT_CODE_NO_FILES, 
    EXIT_CODE_DISK_FULL
)
from mutagen import id3
import os

class TestCLIIntegration:
    """End-to-end CLI integration tests using real audio files."""

    def test_cli_write(self, audio_file):
        """Test simple overwrite via CLI."""
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "title", "--value", "CLI Title"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['title'] == ['CLI Title']

    def test_cli_set_numeric(self, audio_file):
        """Test setting numeric fields (track)."""
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "track", "--value", "5"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['track'] == ['5']

    def test_cli_set_numeric_explicit(self, audio_file):
         """Test setting numeric field with explicit value as requested."""
         with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "track", "--value", "1"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
         with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['track'] == ['1']

    def test_cli_write_with_schema(self, audio_file):
        """Test modification operation with explicit schema."""
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "title", "--value", "Schema Title", "--schema", "canonical"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['title'] == ['Schema Title']

    def test_cli_clear(self, audio_file):
        """Test clearing fields."""
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({"album": ["To Be Cleared"]})
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "clear", "--fields", "album"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            if 'silence' in str(audio_file):
                 # Strict reading returns [""] for empty fields
                 assert fields.get('album') == [""]
            else:
                 assert fields.get('album') == [""]

    def test_cli_find_replace(self, audio_file):
        """Test find-replace."""
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({"artist": ["The Old Artist"]})
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "find-replace", "--fields", "artist", "--find", "Old", "--replace", "New"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['artist'] == ['The New Artist']

    def test_cli_print_truncation(self, audio_file, capsys):
        """Test print operation with field truncation."""
        long_value = "A" * 200
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({"comment": [long_value]})
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "print"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        captured = capsys.readouterr()
        expected = "A" * 147 + "..."
        assert expected in captured.out
        assert long_value not in captured.out

    def test_cli_print_defaults(self, audio_file, capsys):
        """Test print operation defaults to extended fields."""
        with SimpleMusic.managed(audio_file) as sm:
             if isinstance(sm.mfile.tags, id3.ID3):
                sm.mfile.tags.add(id3.TXXX(desc='MyCustomTag', text=['CustomVal']))
                sm.mfile.save()
             elif hasattr(sm.mfile, 'tags') and hasattr(sm.mfile.tags, '__setitem__'):
                try:
                    sm.mfile.tags['MyCustomTag'] = ['CustomVal']
                    sm.mfile.save()
                except Exception:
                    pass

        # 1. Default (extended)
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "print"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        
        assert "    Title:" in captured.out
        if "MyCustomTag" in str(SimpleMusic(audio_file).read_fields(schema='extended')):
             assert "MyCustomTag" in captured.out or "TXXX:mycustomtag" in captured.out.lower() or "Mycustomtag" in captured.out

        # 2. Canonical override
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "print", "--schema", "canonical"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured_canonical = capsys.readouterr()
        
        assert "    Title:" in captured_canonical.out
        assert "MyCustomTag" not in captured_canonical.out
        assert "TXXX:mycustomtag" not in captured_canonical.out.lower()
        
    def test_cli_explicit_extended_schema(self, audio_file, capsys):
        """Test explicit --schema extended."""
        with SimpleMusic.managed(audio_file) as sm:
             if isinstance(sm.mfile.tags, id3.ID3):
                sm.mfile.tags.add(id3.TXXX(desc='MyCustomTag', text=['CustomVal']))
                sm.mfile.save()
             elif hasattr(sm.mfile, 'tags') and hasattr(sm.mfile.tags, '__setitem__'):
                try:
                    sm.mfile.tags['MyCustomTag'] = ['CustomVal']
                    sm.mfile.save()
                except Exception:
                    pass

        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "print", "--schema", "extended"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        
        if "MyCustomTag" in str(SimpleMusic(audio_file).read_fields(schema='extended')):
             assert "MyCustomTag" in captured.out or "TXXX:mycustomtag" in captured.out.lower() or "Mycustomtag" in captured.out

    def test_cli_raw_schema_mp3(self, audio_file, capsys):
        """Test --schema raw specifically for MP3 files to see ID3 tags."""
        if audio_file.suffix.lower() != ".mp3":
            pytest.skip("Test specific to MP3 format")
            
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({"title": ["Raw Test"], "artist": ["Raw Artist"]})
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "print", "--schema", "raw"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        captured = capsys.readouterr()
        assert "TIT2" in captured.out
        assert "TPE1" in captured.out
        assert "Raw Test" in captured.out

    def test_cli_backup(self, audio_file, tmp_path):
        """Test backup generation."""
        backup_dir = tmp_path / "backups"
        
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "title", "--value", "Changed", "--backup", str(backup_dir), "--force"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        assert len(backups) == 1
        assert backups[0].name == audio_file.name

    def test_cli_operations_extended(self, audio_file):
        """Test append, prefix, enlist, delist operations."""
        # Ensure known starting state
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({'title': ['Test Title'], 'genre': ['Rock']})
            
        # 1. Append
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "append", "--fields", "title", "--value", " Appended"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            assert sm.read_fields()['title'] == ['Test Title Appended']

        # 2. Prefix
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "prefix", "--fields", "title", "--value", "Prefixed "]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            assert sm.read_fields()['title'] == ['Prefixed Test Title Appended']
            
        # 3. Enlist (multi-value)
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "enlist", "--fields", "genre", "--value", "Pop"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            genres = sm.read_fields()['genre']
            assert 'Rock' in genres and 'Pop' in genres
            
        # 4. Delist
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "delist", "--fields", "genre", "--value", "Rock"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
             genres = sm.read_fields()['genre']
             assert 'Rock' not in genres
             assert 'Pop' in genres

    def test_cli_delimiter(self, audio_file):
        """Test custom delimiter in write and append."""
        # Write with pipe delimiter
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "genre", "--value", "A|B|C", "--delimiter", "|"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            genres = sm.read_fields()['genre']
            assert len(genres) == 3
            assert 'A' in genres and 'B' in genres and 'C' in genres

    def test_cli_filter_logic(self, audio_file, tmp_path):
        """Test filtering logic with real files."""
        # Create two files with correct extension
        dir_ = tmp_path / "filter_test"
        dir_.mkdir()
        
        f1 = dir_ / f"f1{audio_file.suffix}"
        f2 = dir_ / f"f2{audio_file.suffix}"
        shutil.copy(audio_file, f1)
        shutil.copy(audio_file, f2)
        
        # Set distinct tags
        with SimpleMusic.managed(f1) as sm:
            sm.write_fields({'title': ['MatchMe']})
        with SimpleMusic.managed(f2) as sm:
            sm.write_fields({'title': ['IgnoreMe']})
            
        # Run CLI with filter
        with patch.object(sys, 'argv', [
            "mudio", str(dir_), 
            "--operation", "write", 
            "--fields", "artist", 
            "--value", "FilteredArtist", 
            "--filter", "title=MatchMe"
        ]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        # Verify
        with SimpleMusic.managed(f1) as sm:
            assert sm.read_fields()['artist'] == ['FilteredArtist']
            
        with SimpleMusic.managed(f2) as sm:
            # Should NOT have FilteredArtist. 
            # Note: The original file might have had 'Test Artist'.
            # We just verify it didn't change to 'FilteredArtist'.
            assert sm.read_fields().get('artist') != ['FilteredArtist']

    def test_cli_regex_filter(self, audio_file, tmp_path):
        """Test regex filter."""
        dir_ = tmp_path / "regex_test"
        dir_.mkdir()
        f1 = dir_ / f"f1{audio_file.suffix}"
        shutil.copy(audio_file, f1)
        
        with SimpleMusic.managed(f1) as sm:
            sm.write_fields({'title': ['Year 2025']})
            
        # Match digits (escaping backslash)
        with patch.object(sys, 'argv', [
            "mudio", str(dir_), 
            "--operation", "write", 
            "--fields", "comment", 
            "--value", "Matched", 
            "--filter", r"title=\d+", 
            "--filter-regex"
        ]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(f1) as sm:
            assert sm.read_fields()['comment'] == ['Matched']


class TestCLIValidation:
    """Test CLI argument validation and exit codes."""
    
    @pytest.fixture
    def dummy_file(self, tmp_path):
        p = tmp_path / "dummy.mp3"
        p.touch()
        return p

    def test_no_args_exits(self):
        with patch.object(sys, 'argv', ['mudio']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_USAGE

    def test_invalid_args_exit_code(self, dummy_file):
        """Test invalid arguments exit code."""
        # Find-replace without --find/--replace
        args = ['mudio', str(dummy_file), '--operation', 'find-replace', '--fields', 'title']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_USAGE

    def test_invalid_filter_exit_code(self, dummy_file):
        """Test invalid filter syntax exit code."""
        args = ['mudio', str(dummy_file), '--operation', 'print', '--filter', 'badfilter']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_USAGE
            
    def test_invalid_schema(self, dummy_file):
        """Test invalid --schema choice."""
        with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--operation", "print", "--schema", "invalid_choice"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    @patch('mudio.cli.run_processing_session')
    def test_interrupt_exit_code(self, mock_run, dummy_file):
        """Test KeyboardInterrupt handling."""
        mock_run.side_effect = KeyboardInterrupt
        args = ['mudio', str(dummy_file), '--operation', 'print']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_INTERRUPTED
            
    def test_permission_error_exit_code(self):
        """Test PermissionError during argument validation."""
        with patch('os.access', return_value=False):
            with patch('os.path.exists', return_value=True):
                args = ['mudio', '/protected/path', '--operation', 'print']
                with patch.object(sys, 'argv', args):
                    with pytest.raises(SystemExit) as exc:
                        main()
                    assert exc.value.code == EXIT_CODE_PERMISSION

    @patch('mudio.cli.run_processing_session')
    def test_generic_exception_exit_code(self, mock_run, dummy_file):
        """Test unhandled exception exit code."""
        mock_run.side_effect = Exception("Unexpected crash")
        args = ['mudio', str(dummy_file), '--operation', 'print']
        with patch.object(sys, 'argv', args):
             with pytest.raises(SystemExit) as exc:
                main()
             assert exc.value.code == EXIT_CODE_ERROR

    @patch('mudio.cli.collect_files_generator')
    def test_no_files_exit_code(self, mock_collect):
        """Test no files found exit code."""
        mock_collect.return_value = iter([])
        args = ['mudio', '.', '--operation', 'print']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_NO_FILES

    @patch('mudio.cli.run_processing_session')
    def test_disk_full_exception_exit_code(self, mock_run, dummy_file):
        """Test OSError(ENOSPC) caught in main."""
        import errno
        os_err = OSError(errno.ENOSPC, "No space left on device")
        mock_run.side_effect = os_err
        
        args = ['mudio', str(dummy_file), '--operation', 'write', '--fields', 'artist', '--value', 'New Artist']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_DISK_FULL

    @patch('mudio.cli.collect_files_generator')
    @patch('mudio.cli.process_files')
    def test_disk_full_result_exit_code(self, mock_process, mock_collect, dummy_file):
        """Test disk full error reported in process results."""
        import errno
        mock_collect.return_value = iter([dummy_file]) 
        
        os_err = OSError(errno.ENOSPC, "No space")
        mock_process.return_value = [{
            'path': str(dummy_file),
            'passed': False,
            'exception': os_err
        }]
        
        args = ['mudio', str(dummy_file), '--operation', 'print']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_DISK_FULL
            
    def test_fields_union(self):
        """Test --fields extraction."""
        args = MagicMock()
        args.fields = "mycustom"
        args.operation = "clear"
        args.delimiter = ";"
        args.schema = "canonical" 
        
        ops, targeted_fields = build_operations_from_args(args)
        
        assert "mycustom" in targeted_fields 
        assert "title" not in targeted_fields

    def test_case_insensitive_fields(self):
        """Test that field names are case insensitive in --fields."""
        args = MagicMock()
        args.fields = "TiTlE, ArTiSt"
        args.schema = None
        args.operation = "clear"
        args.delimiter = ";"
        
        ops, targeted_fields = build_operations_from_args(args)
        assert "title" in targeted_fields
        assert "artist" in targeted_fields

    def test_mode_missing_required_args(self, dummy_file):
        """Test validation for operations that require values."""
        modes = [
            ("append", []),
            ("prefix", []),
            ("find-replace", ["--find", "foo"]), # Missing replace
            ("find-replace", ["--replace", "bar"]), # Missing find
            ("add", []),
        ]
        
        for mode, extra_args in modes:
            cmd = ["mudio", str(dummy_file), "--operation", mode, "--fields", "title"] + extra_args
            with patch.object(sys, 'argv', cmd):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code != 0
