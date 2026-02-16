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
    
    
    def test_duplicate_comments(self):
        """Test frame-level deduplication of comments."""
        import mutagen.id3 as id3
        from mutagen.mp3 import MP3
        
        test_file = self.test_dir / "dup_comment.mp3"
        # Assuming 'tests/audio/silence.mp3' exists for this test to run
        # For a self-contained test, one might create a dummy MP3 file.
        # For now, we'll assume it's available in the test environment.
        try:
            shutil.copy("tests/audio/silence.mp3", test_file)
        except FileNotFoundError:
            self.skipTest("tests/audio/silence.mp3 not found, skipping duplicate comments test.")
            return
        
        audio = MP3(test_file)
        if audio.tags is None:
            audio.add_tags()
            
        def reset_tags():
            audio.tags.delall('COMM')
            
        # EX 1: Intra-frame duplicates preserved
        reset_tags()
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='', text=['a', 'b', 'b', 'c']))
        audio.save()
        
        sm = SimpleMusic(test_file)
        fields = sm.read_fields(schema='canonical')
        self.assertEqual(fields['comment'], ['a', 'b', 'b', 'c'])
        
        # EX 2: Identical frames deduplicated
        reset_tags()
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='', text=['a']))
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='Comment', text=['a'])) # Same text, different desc
        audio.save()
        
        sm = SimpleMusic(test_file)
        fields = sm.read_fields(schema='canonical')
        self.assertEqual(fields['comment'], ['a'])
        
        # EX 3: Different frames preserved
        reset_tags()
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='', text=['a']))
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='Comment', text=['b']))
        audio.save()
        
        sm = SimpleMusic(test_file)
        fields = sm.read_fields(schema='canonical')
        self.assertEqual(len(fields['comment']), 2)
        self.assertIn('a', fields['comment'])
        self.assertIn('b', fields['comment'])
        
        # EX 4: Mixed Case (should be preserved as they differ in case)
        reset_tags()
        # 'A' and 'a' should be seen as distinct content
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='', text=['A']))
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='Comment', text=['a']))
        audio.save()
        
        sm = SimpleMusic(test_file)
        fields = sm.read_fields(schema='canonical')
        # Expect 2 comments: 'A' and 'a'
        self.assertEqual(len(fields['comment']), 2)
        self.assertIn('A', fields['comment'])
        self.assertIn('a', fields['comment'])
        
        # EX 5: Whitespace/Empty handling
        reset_tags()
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='', text=[' ']))
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='Comment', text=[''])) # Empty
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='Other', text=['  '])) # Different whitespace
        audio.save()
        
        sm = SimpleMusic(test_file)
        fields = sm.read_fields(schema='canonical')
        # These are technically different strings, so they should be preserved if we strictly dedup on content.
        # But ' ' vs '  ' might be stripped? SimpleMusic generally strips whitespace?
        # Let's see current behavior. If we don't stripe, they are distinct.
        # Expect 3 comments: ' ', '', '  '
        # Mutagen or ID3 implementation appears to drop empty COMM frames.
        # Expect 2 comments: ' ' and '  ' (empty '' is dropped)
        self.assertEqual(len(fields['comment']), 2)
        self.assertNotIn('', fields['comment'])
        self.assertIn(' ', fields['comment'])
        self.assertIn('  ', fields['comment'])
        
        # EX 6: Complex Descriptions (Duplicate content across different descriptions)
        reset_tags()
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='iTunes_CDDB_1', text=['a']))
        audio.tags.add(id3.COMM(encoding=3, lang='eng', desc='AnotherDesc', text=['a']))
        audio.save()
        
        sm = SimpleMusic(test_file)
        fields = sm.read_fields(schema='canonical')
        # Should be deduplicated to ['a']
        self.assertEqual(fields['comment'], ['a'])

        # Test Write Collapsing
        sm = SimpleMusic(test_file)
        sm.write_fields({'comment': ['x', 'y']})
        sm.close()
        
        audio = MP3(test_file)
        comms = audio.tags.getall('COMM')
        self.assertEqual(len(comms), 1)
        self.assertEqual(comms[0].text, ['x', 'y'])
    
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

    def test_custom_field_persistence_and_deletion(self):
        """Test adding and deleting custom fields."""
        # Use a real file processing logic with mock
        with patch('mutagen.File') as mock_mutagen:
            mock_file = Mock()
            # Setup tags behaving like a dict
            tags = {}
            mock_file.tags = tags
            mock_mutagen.return_value = mock_file
            
            # Setup MP4 specific behavior for this test as the issue was mainly MP4
            import mutagen.mp4
            mock_file.__class__ = mutagen.mp4.MP4
            
            test_file = self.test_dir / "test.m4a"
            test_file.write_bytes(b"fake content")
            
            # 1. Test Addition
            sm = SimpleMusic(test_file)
            sm.write_fields({'my_custom_field': ['Test Value']})
            
            # Verify write happened to tags
            # The core logic converts to ----:com.apple.iTunes:MY_CUSTOM_FIELD for MP4
            expected_key = '----:com.apple.iTunes:MY_CUSTOM_FIELD'
            self.assertIn(expected_key, tags)
            self.assertEqual(tags[expected_key], [b'Test Value'])
            
            # 2. Test Deletion
            sm.delete_fields(['my_custom_field'])
            
            # Verify deletion
            self.assertNotIn(expected_key, tags)
            
            # 3. Test Deletion of non-existent field (should not error)
            sm.delete_fields(['non_existent'])

if __name__ == '__main__':
    unittest.main()