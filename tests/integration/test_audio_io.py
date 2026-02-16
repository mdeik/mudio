
"""
Integration tests for Audio I/O using real files.
"""
import pytest
from mudio.core import SimpleMusic, FormatError
from mudio.operations import delete

class TestAudioIO:
    """Tests using real audio files for Read/Write operations."""

    def test_load_file(self, audio_file):
        """Test that SimpleMusic can load the file without errors."""
        with SimpleMusic.managed(audio_file) as sm:
            assert sm.mfile is not None
            assert sm.path == audio_file

    def test_read_write_cycle(self, audio_file):
        """Test a full read-write cycle with standard fields."""
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
        
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(metadata)
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            
            assert fields["title"] == metadata["title"]
            assert fields["artist"] == metadata["artist"]
            assert fields["album"] == metadata["album"]
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
        initial_metadata = {
            "title": ["To Be Cleared"],
            "artist": ["To Be Cleared"],
        }
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(initial_metadata)
        
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
        
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(metadata)
            sm.write_fields(metadata)
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields["title"] == ["Idempotency Test"]

    def test_delete_field_entirely(self, audio_file):
        """Test that delete operation removes field key entirely from metadata."""
        from mudio.processor import process_file
        
        initial_metadata = {
            "title": ["To Be Deleted"],
            "artist": ["Should Remain"],
            "album": ["Also Remain"],
        }
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields(initial_metadata)
        
        # Use delete operation via process_file
        ops = [delete("title")]
        result = process_file(
            audio_file,
            ops=ops,
            backup_dir=None,
            dry_run=False,
            filters=[]
        )
        assert result['passed'] is True
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields.get("title", []) == []
            assert fields.get("artist") == ["Should Remain"]
            assert fields.get("album") == ["Also Remain"]

    def test_read_all_formats(self, all_format_files):
        """Test reading metadata from all supported formats (dummy files)."""
        for file_path in all_format_files:
            try:
                with SimpleMusic(file_path) as sm:
                    fields = sm.read_fields()
                    assert isinstance(fields, dict)
            except (RuntimeError, FormatError) as e:
                # Expected for dummy files - verify it's a user-friendly error
                assert "Unsupported file format" in str(e) or "No metadata" in str(e) or "Failed to load" in str(e)

    def test_format_coverage(self, all_format_files):
        """Verify we have all expected formats."""
        found_formats = {f.suffix.lower() for f in all_format_files}
        expected = {'.mp3', '.flac', '.m4a', '.wav', '.ogg', '.opus'}
        assert found_formats == expected
