import pytest
from unittest.mock import MagicMock
from mudio.core import SimpleMusic
import mutagen.mp4 as mp4
import mutagen.id3 as id3
import mutagen.flac as flac

class TestDisplayLogic:
    """Test the _format_metadata logic in SimpleMusic."""

    @pytest.fixture
    def sm(self):
        sm = SimpleMusic.__new__(SimpleMusic)
        sm.path = MagicMock()
        sm.path.name = "test_audio.mp3"
        return sm

    def test_format_metadata_no_tags(self, sm):
        """Test formatting when no tags are found."""
        sm.mfile = MagicMock()
        sm.mfile.tags = None
        
        output = sm._format_metadata()
        assert "=== test_audio.mp3 ===" in output
        assert "No metadata found." in output

    def test_format_metadata_mp4(self, sm):
        """Test MP4 metadata formatting."""
        sm.mfile = MagicMock(spec=mp4.MP4)
        sm.mfile.tags = {
            "\xa9nam": ["Test Title"],
            "\xa9ART": ["Test Artist"],
            "covr": [b"binary_image_data"]
        }
        
        output = sm._format_metadata()
        assert "nam" in output and "Test Title" in output
        assert "ART" in output and "Test Artist" in output
        assert "covr" in output and "cover(s)" in output

    def test_format_metadata_id3(self, sm):
        """Test ID3 metadata formatting."""
        sm.mfile = MagicMock()
        tags = id3.ID3()
        tags.add(id3.TIT2(encoding=3, text=["ID3 Title"]))
        tags.add(id3.TPE1(encoding=3, text=["ID3 Artist"]))
        
        # Mock APIC frame
        apic = id3.APIC(encoding=3, mime="image/jpeg", type=3, desc="front cover", data=b"fake_jpg")
        tags.add(apic)
        
        sm.mfile.tags = tags
        
        output = sm._format_metadata()
        # id3 tags usually use frame IDs in the output
        assert "TIT2" in output and "ID3 Title" in output
        assert "TPE1" in output and "ID3 Artist" in output
        assert "APIC" in output and "image/jpeg" in output and "8 bytes" in output

    def test_format_metadata_flac(self, sm):
        """Test FLAC metadata formatting."""
        sm.mfile = MagicMock(spec=flac.FLAC)
        sm.mfile.tags = {
            "title": ["FLAC Title"],
            "artist": ["FLAC Artist"]
        }
        
        # Test picture handling
        pic = MagicMock()
        pic.mime = "image/png"
        pic.data = b"fake_png_data"
        sm.mfile.pictures = [pic]
        
        output = sm._format_metadata()
        assert "title          : FLAC Title" in output
        assert "artist         : FLAC Artist" in output
        assert "picture        : <image: image/png, 13 bytes>" in output

    def test_format_metadata_truncate(self, sm):
        """Test truncation of long values in display."""
        sm.mfile = MagicMock(spec=flac.FLAC)
        long_val = "A" * 100
        sm.mfile.tags = {"comment": [long_val]}
        
        output = sm._format_metadata()
        # Truncation limit is 50 by default in _truncate
        expected = "A" * 47 + "..."
        assert expected in output
        assert long_val not in output
