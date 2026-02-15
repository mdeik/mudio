"""Unit tests for mudio.core module."""

import unittest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, patch
from mudio import SimpleMusic

from mudio.core import FormatError

class TestSimpleMusic(unittest.TestCase):
    """Test cases for SimpleMusic class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="mudio_test_"))
        
    def tearDown(self):
        """Clean up test fixtures."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_parse_list_string(self):
        """Test parse_list_string method."""
        self.assertEqual(SimpleMusic.parse_list_string("a;b;c"), ["a", "b", "c"])
        self.assertEqual(SimpleMusic.parse_list_string("a; b ; c"), ["a", "b", "c"])
        self.assertEqual(SimpleMusic.parse_list_string(""), [])
        self.assertEqual(SimpleMusic.parse_list_string(None), [])
    
    def test_unique_preserve_order_case_insensitive(self):
        """Test unique_preserve_order_case_insensitive method."""
        input_list = ["Artist", "artist", "ARTIST", "New Artist"]
        result = SimpleMusic.unique_preserve_order_case_insensitive(input_list)
        self.assertEqual(result, ["Artist", "New Artist"])
    
    def test_safe_int(self):
        """Test safe_int method."""
        self.assertEqual(SimpleMusic.safe_int("123"), 123)
        self.assertEqual(SimpleMusic.safe_int(456), 456)
        self.assertIsNone(SimpleMusic.safe_int("invalid"))
        self.assertIsNone(SimpleMusic.safe_int(None))
    
    @patch('mutagen.File')
    def test_file_loading(self, mock_mutagen):
        """Test file loading with mutagen."""
        mock_file = Mock()
        mock_mutagen.return_value = mock_file
        
        test_file = self.test_dir / "test.mp3"
        test_file.write_bytes(b"fake content")
        
        sm = SimpleMusic(test_file)
        self.assertEqual(sm.path, test_file)
        self.assertEqual(sm.mfile, mock_file)
        
        # Simulate mutagen failing to load nonexistent file
        mock_mutagen.side_effect = IOError("File not found")
        with self.assertRaises(FormatError):
            SimpleMusic(self.test_dir / "nonexistent.mp3")
    
    def test_context_manager(self):
        """Test context manager functionality."""
        with patch('mutagen.File') as mock_mutagen:
            mock_file = Mock()
            mock_mutagen.return_value = mock_file
            
            test_file = self.test_dir / "test.mp3"
            test_file.write_bytes(b"fake content")
            
            with SimpleMusic(test_file) as sm:
                self.assertIsInstance(sm, SimpleMusic)
            
            mock_file.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()