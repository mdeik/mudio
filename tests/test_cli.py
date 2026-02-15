
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

    def test_cli_overwrite(self, audio_file):
        """Test simple overwrite via CLI."""
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--mode", "set", "--fields", "title", "--value", "CLI Title"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['title'] == ['CLI Title']

    def test_cli_set_numeric(self, audio_file):
        """Test setting numeric fields (track, date)."""
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--mode", "set", "--track", "5", "--date", "2024"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['track'] == ['5']
            # Date format can vary, but should contain the year
            assert any('2024' in d for d in fields['date'])

    def test_cli_clear(self, audio_file):
        """Test clearing fields."""
        # Setup
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({"album": ["To Be Cleared"]})
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--mode", "clear", "--fields", "album"]):
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
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--mode", "find-replace", "--fields", "artist", "--find", "Old", "--replace", "New"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['artist'] == ['The New Artist']

    def test_cli_print_truncation(self, audio_file, capsys):
        """Test print mode with field truncation."""
        long_value = "A" * 200
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({"comment": [long_value]})
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--mode", "print"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        captured = capsys.readouterr()
        # Should contain truncated version (150 chars - 3 + ...)
        expected = "A" * 147 + "..."
        assert expected in captured.out
        # Should NOT contain full version
        assert long_value not in captured.out

    def test_cli_print_all_fields(self, audio_file, capsys):
        """Test print mode with --all-fields."""
        with SimpleMusic.managed(audio_file) as sm:
            # Ensure title is present for verification
            sm.write_fields({"title": ["TestTitle"]})
            
            # Add a custom/non-canonical field. 
            # Note: Not all formats support arbitrary custom tags easily via mutagen's simple API,
            # but our core.py logic tries to handle it.
            # For MP3/ID3 we use TXXX. for FLAC/Vorbis we use custom keys.
            if isinstance(sm.mfile.tags, id3.ID3):
                sm.mfile.tags.add(id3.TXXX(desc='CustomTag', text=['CustomValue']))
                sm.mfile.save()
            elif hasattr(sm.mfile, 'tags') and hasattr(sm.mfile.tags, '__setitem__'):
                try:
                    sm.mfile.tags['CustomTag'] = ['CustomValue']
                    sm.mfile.save()
                except Exception:
                    # Some formats might fail or not support this
                    pass
            
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--mode", "print", "--all-fields"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
        captured = capsys.readouterr()
        # Should see standard fields with nice names
        assert "    Title:" in captured.out
        
        # Should see custom tag if it was successfully written
        # usage depends on format, but if we wrote it, we should see it
        # We do a loose check because not all formats in the fixture might support it
        if "CustomTag" in str(SimpleMusic(audio_file).read_fields(mode='extended')):
             assert "CustomTag" in captured.out or "TXXX:customtag" in captured.out.lower()

    def test_cli_backup(self, audio_file, tmp_path):
        """Test backup generation."""
        backup_dir = tmp_path / "backups"
        
        # Use --force to ensure backup is not deleted after success
        # Need to include --force in the arguments list properly
        with patch.object(sys, 'argv', ["mudio", str(audio_file), "--mode", "set", "--fields", "title", "--value", "Changed", "--backup", str(backup_dir), "--force"]):
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
            # But with no mode, it prints "No operations defined" and exits(1).
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_find_replace_missing_args(self, tmp_path):
        test_file = tmp_path / "test.mp3"
        test_file.touch()
        with patch.object(sys, 'argv', ["mudio", str(test_file), "--mode", "find-replace", "--fields", "title"]):
            # Missing --find/--replace
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_invalid_filter(self, tmp_path):
        test_file = tmp_path / "test.mp3"
        test_file.touch()
        # Invalid filter syntax
        args = ["mudio", str(test_file), "--mode", "set", "--fields", "title", "--value", "X", "--filter", "badfilter"]
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_cli_print_invalid_file(self, tmp_path, capsys):
        """Test print mode on an invalid file."""
        bad_file = tmp_path / "bad.mp3"
        bad_file.write_text("This is not an audio file")
        
        with patch.object(sys, 'argv', ["mudio", str(bad_file), "--mode", "print"]):
            # Should not crash, but print error
            with pytest.raises(SystemExit):
                main()
                
        captured = capsys.readouterr()
        # Should indicate failure or error
        assert "Failed" in captured.out or "Error" in captured.out or "Could not read" in captured.out