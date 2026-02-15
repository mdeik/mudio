"""Integration tests with real (dummy) audio files."""

import pytest
from pathlib import Path
from mudio import SimpleMusic, overwrite
from mudio.core import CANONICAL_FIELDS

from mudio.core import FormatError

def test_read_all_formats(all_format_files):
    """Test reading metadata from all supported formats."""
    for file_path in all_format_files:
        print(f"Testing read: {file_path.name} ({file_path.suffix})")
        # These are dummy files, so we expect them to fail gracefully
        # The test verifies the pipeline doesn't crash
        try:
            with SimpleMusic(file_path) as sm:
                fields = sm.read_fields()
                assert isinstance(fields, dict)
        except (RuntimeError, FormatError) as e:
            # Expected for dummy files - verify it's a user-friendly error
            assert "Unsupported file format" in str(e) or "No metadata" in str(e) or "Failed to load" in str(e)

def test_format_coverage(all_format_files):
    """Verify we have all expected formats."""
    found_formats = {f.suffix.lower() for f in all_format_files}
    expected = {'.mp3', '.flac', '.m4a', '.wav', '.ogg', '.opus', '.wma', '.wv'}
    assert found_formats == expected