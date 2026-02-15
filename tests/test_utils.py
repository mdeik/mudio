
import pytest
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch
from mudio.utils import (
    safe_unicode_path,
    safe_regex_pattern,
    get_file_hash,
    Config,
    join_for_printing
)

class TestUtils:
    """Tests for utility functions."""

    def test_safe_unicode_path(self):
        # String remains string
        assert safe_unicode_path("test") == "test"
        # Bytes decoding
        assert safe_unicode_path(b"test") == "test"
        # Non-utf8 bytes (latin-1) fallback
        latin1_bytes = b"\xe9" # é in latin-1 (in utf-8 it's \xc3\xa9)
        # utf-8 decode of \xe9 fails, should fallback to latin-1
        assert safe_unicode_path(latin1_bytes) == "é"

    def test_safe_regex_pattern(self):
        # Non-regex escapes everything
        assert safe_regex_pattern("a.b", is_regex=False) == re.escape("a.b")
        
        # Valid regex passes through
        assert safe_regex_pattern(r"\d+", is_regex=True) == r"\d+"
        
        # Invalid regex raises ValueError
        with pytest.raises(ValueError):
            safe_regex_pattern("[", is_regex=True)
    def test_get_file_hash(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"content")
            tmp.close()
            path = Path(tmp.name)
            try:
                # sha256 of "content"
                expected = "ed7002b439e9ac845f22357d822bac1444730fbdb6016d3ec9432297b9ec9f73"
                assert get_file_hash(path) == expected
            finally:
                path.unlink()

    def test_join_for_printing(self):
        assert join_for_printing([]) == "(none)"
        assert join_for_printing(["A", "B"]) == "A; B"


class TestConfig:
    """Tests for Config class."""

    # Test removed as it was redundant with test_from_env_overrides and used old API


    def test_validate(self):
        # validation should pass on default
        try:
            Config.validate()
        except ValueError:
            pytest.fail("Config.validate() raised ValueError unexpectedly")

    def test_validate_custom_values(self):
        # We need to test behavior when values change.
        original = Config.MAX_WORKERS
        try:
            Config.MAX_WORKERS = -1
            with pytest.raises(ValueError, match="MAX_WORKERS must be positive"):
                Config.validate()
        finally:
            Config.MAX_WORKERS = original

    def test_from_env_overrides(self):
        env = {
            'MUDIO_MAX_FILE_SIZE': '999',
            'MUDIO_MAX_WORKERS': '5'
        }
        original_size = Config.MAX_FILE_SIZE
        original_workers = Config.MAX_WORKERS
        
        try:
            with patch.dict(os.environ, env):
                Config.load_from_env()
                assert Config.MAX_FILE_SIZE == 999
                assert Config.MAX_WORKERS == 5
        finally:
            Config.MAX_FILE_SIZE = original_size
            Config.MAX_WORKERS = original_workers
