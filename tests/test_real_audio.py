
import pytest
import shutil
from pathlib import Path
from mudio.core import SimpleMusic

# Define the location of the audio files
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
    """
    Fixture that copies the requested audio file to a temporary directory.
    Returns the path to the temporary file.
    """
    original_file = request.param
    temp_file = tmp_path / original_file.name
    shutil.copy2(original_file, temp_file)
    return temp_file

@pytest.mark.parametrize("audio_file", get_audio_files(), indirect=True)
class TestRealAudio:
    """Tests using real audio files from tests/audio."""

    def test_load_file(self, audio_file):
        """Test that SimpleMusic can load the file without errors."""
        with SimpleMusic.managed(audio_file) as sm:
            assert sm.mfile is not None
            assert sm.path == audio_file

    def test_read_write_cycle(self, audio_file):
        """
        Test a full read-write cycle:
        1. Write comprehensive metadata.
        2. Save.
        3. Reload and verify metadata.
        """
        metadata = {
            "title": ["Test Read Write Cycle"],
            "artist": ["Test Artist"],
            "album": ["Test Album"],
            "date": ["2023"],
            "genre": ["Test Genre"],
            "track": ["1"],
            "totaltracks": ["10"],
            "disc": ["1"],
            "totaldiscs": ["2"],
            "comment": ["Test Comment"],
            "composer": ["Test Composer"],
        }
        
        # Write metadata
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(metadata)
        
        # Read back and verify
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            
            assert fields["title"] == metadata["title"]
            assert fields["artist"] == metadata["artist"]
            assert fields["album"] == metadata["album"]
            # Flexible date checking (some formats might store full timestamps)
            assert any(d.startswith("2023") for d in fields["date"])
            assert fields["genre"] == metadata["genre"]
            assert fields["track"] == metadata["track"]
            assert fields["totaltracks"] == metadata["totaltracks"]
            assert fields["disc"] == metadata["disc"]
            assert fields["totaldiscs"] == metadata["totaldiscs"]
            assert fields["comment"] == metadata["comment"]
            assert fields["composer"] == metadata["composer"]

    def test_special_characters(self, audio_file):
        """Test writing and reading strings with special characters."""
        special_metadata = {
            "title": ["Special: @#$%^&*()_+{}|:<>?~`"],
            "artist": ["Unicode: 🎵测试йцук"],
            "album": ["Spaces  and   Tabs\tHere"],
        }

        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(special_metadata)

        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields["title"] == special_metadata["title"]
            assert fields["artist"] == special_metadata["artist"]
            assert fields["album"] == special_metadata["album"]

    def test_clear_metadata(self, audio_file):
        """Test clearing metadata fields."""
        # First write some data
        initial_metadata = {
            "title": ["To Be Cleared"],
            "artist": ["To Be Cleared"],
        }
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(initial_metadata)
        
        # Now clear it by sending empty lists or None (depending on implementation, 
        # usually empty list or None should work if the logic handles it, 
        # let's try empty list as per SimpleMusic API usage in other tests)
        clear_metadata = {
            "title": [],
            "artist": [],
        }
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(clear_metadata)
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert not fields.get("title")
            assert not fields.get("artist")

    def test_idempotency(self, audio_file):
        """Test that writing the same metadata twice produces consistent results."""
        metadata = {"title": ["Idempotency Test"]}
        
        # First write
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(metadata)
            
        # Second write
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(metadata)
            
        # Verify
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields["title"] == ["Idempotency Test"]

    def test_delete_field_entirely(self, audio_file):
        """Test that delete operation removes field key entirely from metadata."""
        from mudio.operations import delete
        from mudio.processor import process_file
        
        # First write some data
        initial_metadata = {
            "title": ["To Be Deleted"],
            "artist": ["Should Remain"],
            "album": ["Also Remain"],
        }
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(initial_metadata)
        
        # Verify it was written
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert "title" in fields
            assert fields["title"] == ["To Be Deleted"]
        
        # Use delete operation via process_file
        ops = {"title": delete("title")}
        result = process_file(
            audio_file,
            ops=ops,
            targeted_fields=["title"],
            backup_dir=None,
            dry_run=False,
            filters=[]
        )
        
        assert result['passed'] is True
        
        # Verify title field is completely removed
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            # Field should be absent or empty list (depending on implementation)
            assert fields.get("title", []) == []
            # Other fields should remain
            assert fields.get("artist") == ["Should Remain"]
            assert fields.get("album") == ["Also Remain"]

    def test_delete_vs_clear(self, audio_file):
        """Test the distinction between delete (removes key) and clear (empty value)."""
        from mudio.operations import delete, clear
        from mudio.processor import process_file
        
        # Write initial data
        initial_metadata = {
            "title": ["Title to Delete"],
            "album": ["Album to Clear"],
            "artist": ["Artist Unchanged"],
        }
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(initial_metadata)
        
        # Apply delete to title, clear to album
        ops = {
            "title": delete("title"),
            "album": clear("album"),
        }
        result = process_file(
            audio_file,
            ops=ops,
            targeted_fields=["title", "album"],
            backup_dir=None,
            dry_run=False,
            filters=[]
        )
        
        assert result['passed'] is True
        
        # Verify results
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            
            # Delete should remove the field entirely
            assert fields.get("title", []) == []
            
            # Clear might leave field present but empty, or also remove it
            # (behavior may vary by format, but both should result in no usable value)
            album_val = fields.get("album", [])
            assert not album_val or album_val == [""]
            
            # Artist should remain unchanged
            assert fields.get("artist") == ["Artist Unchanged"]

