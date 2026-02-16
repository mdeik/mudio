
import pytest
import sys
import shutil
from pathlib import Path
from unittest.mock import patch
from mudio.cli import main
from mudio.core import SimpleMusic
from mutagen import id3

# Define the location of the audio files (same as in test_real_audio.py)
AUDIO_DIR = Path(__file__).parent / "audio"

def get_audio_files():
    """Generator to yield all audio files from tests/audio."""
    if not AUDIO_DIR.exists():
        return []
    return [
        f for f in AUDIO_DIR.iterdir() 
        if f.is_file() and f.suffix.lower() in SimpleMusic.SUPPORTED_EXT
    ]

@pytest.fixture
def audio_file(request, tmp_path):
    """Fixture that copies the requested audio file to a temporary directory."""
    original_file = request.param
    # Create a source directory to avoid backup collision issues
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    temp_file = source_dir / original_file.name
    shutil.copy2(original_file, temp_file)
    return temp_file

@pytest.mark.parametrize("audio_file", get_audio_files(), indirect=True)
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
        # Note: can only set one value at a time with current CLI implementation
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "track", "--value", "5"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['track'] == ['5']

    def test_cli_set_numeric_explicit(self, audio_file):
         """Test setting numeric field with explicit value as requested."""
         # Specifically testing: --operation write --fields track --value "1"
         with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "track", "--value", "1"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
         with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['track'] == ['1']

    def test_cli_write_with_schema(self, audio_file):
        """Test modification operation with explicit schema."""
        # Using 'canonical' schema to modify a field. 
        # 'raw' schema failure on MP4 is expected because verification looks for 'title' but gets '©nam'.
        # 'canonical' schema ensures we get 'title' back, satisfying verification.
        
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "title", "--value", "Schema Title", "--schema", "canonical"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        with SimpleMusic.managed(audio_file) as sm:
            # Read back to verify
            fields = sm.read_fields()
            assert fields['title'] == ['Schema Title']

    def test_cli_clear(self, audio_file):
        """Test clearing fields."""
        # Setup
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({"album": ["To Be Cleared"]})
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "clear", "--fields", "album"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert not fields.get('album')

    def test_cli_find_replace(self, audio_file):
        """Test find-replace."""
        # Setup
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
        # Should contain truncated version (150 chars - 3 + ...)
        expected = "A" * 147 + "..."
        assert expected in captured.out
        # Should NOT contain full version
        assert long_value not in captured.out


    def test_cli_print_defaults(self, audio_file, capsys):
        """Test print operation defaults to extended fields."""
        # Setup: Add a custom tag which extended operation should find
        with SimpleMusic.managed(audio_file) as sm:
            # We try to add a custom field. This depends on format but core.py tries its best.
            # Using TXXX for ID3 or just key-value for others
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
        
        # Should verify it prints standard AND potentially custom fields if format supports
        assert "    Title:" in captured.out
        # If we successfully wrote a custom tag, it should appear in default output
        # We can't guarantee write success on all formats in this fixture without more complex logic,
        # but if it did write, it must appear.
        if "MyCustomTag" in str(SimpleMusic(audio_file).read_fields(schema='extended')):
             assert "MyCustomTag" in captured.out or "TXXX:mycustomtag" in captured.out.lower() or "Mycustomtag" in captured.out

        # 2. Canonical override
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "print", "--schema", "canonical"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured_canonical = capsys.readouterr()
        
        assert "    Title:" in captured_canonical.out
        # Custom tag should NOT appear in canonical operation
        assert "MyCustomTag" not in captured_canonical.out
        assert "TXXX:mycustomtag" not in captured_canonical.out.lower()
        assert "Mycustomtag" not in captured_canonical.out
        
    def test_cli_explicit_extended_schema(self, audio_file, capsys):
        """Test explicit --schema extended."""
        # Setup: Add a custom tag
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
        
        # Extended schema should show custom tag
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
        # ID3v2.3/4 standard frames
        # TIT2 = Title
        # TPE1 = Artist
        assert "TIT2" in captured.out
        assert "TPE1" in captured.out
        assert "Raw Test" in captured.out

    def test_cli_backup(self, audio_file, tmp_path):
        """Test backup generation."""
        backup_dir = tmp_path / "backups"
        
        # Use --force to ensure backup is not deleted after success
        # Need to include --force in the arguments list properly
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--operation", "write", "--fields", "title", "--value", "Changed", "--backup", str(backup_dir), "--force"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        # Verify backup was created
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        assert len(backups) == 1
        assert backups[0].name == audio_file.name


class TestCLIValidation:
    """Test CLI argument validation logic."""

    def test_no_args_exits(self):
        with patch.object(sys, 'argv', ["mudio"]):
            # argparse prints help and exits if no required args (if configured strictly) or processed path default '.'
            # Our main() defaults path='.', so it runs processing on CWD.
            # But with no operation, it prints "No operations defined" and exits(1).
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_find_replace_missing_args(self, tmp_path):
        test_file = tmp_path / "test.mp3"
        test_file.touch()
        with patch.object(sys, 'argv', ["mudio", str(test_file), "--operation", "find-replace", "--fields", "title"]):
            # Missing --find/--replace
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_invalid_filter(self, tmp_path):
        test_file = tmp_path / "test.mp3"
        test_file.touch()
        # Invalid filter syntax
        args = ["mudio", str(test_file), "--operation", "write", "--fields", "title", "--value", "X", "--filter", "badfilter"]
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_cli_print_invalid_file(self, tmp_path, capsys):
        """Test print operation on an invalid file."""
        bad_file = tmp_path / "bad.mp3"
        bad_file.write_text("This is not an audio file")
        
        with patch.object(sys, 'argv', ["mudio", str(bad_file), "--operation", "print"]):
            # Should not crash, but print error
            with pytest.raises(SystemExit):
                main()
                
        captured = capsys.readouterr()
        # Should indicate failure or error
        assert "Failed" in captured.out or "Error" in captured.out or "Could not read" in captured.out