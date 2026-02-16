
"""
Unit tests for format-specific field logic and custom key casing.
"""
import unittest
from unittest.mock import MagicMock, patch
import pytest
from mudio.core import SimpleMusic, canon_key
from mudio.utils import Config
import mutagen.asf as asf
import mutagen.mp4 as mp4
import mutagen.id3 as id3

class TestFormatLogic(unittest.TestCase):
    """Test format-specific logic (MP4, WMA, etc)."""
    
    def setUp(self):
        self.sm = SimpleMusic.__new__(SimpleMusic)
        self.sm.path = MagicMock()
        self.sm.mfile = MagicMock()

    # --- WMA/ASF Tests ---

    def test_canon_key_preserves_case(self):
        # Test that canon_key preserves case for unknown keys
        self.assertEqual(canon_key("NB_UUID"), "NB_UUID")
        self.assertEqual(canon_key("nb_uuid"), "nb_uuid")
        self.assertEqual(canon_key("Title"), "title") # Known key

    def test_write_wma_mapping(self):
        # Setup ASF mock
        self.sm.mfile = MagicMock(spec=asf.ASF)
        self.sm.mfile.tags = {} 
        self.sm.mfile.save = MagicMock()

        # Write canonical fields
        fields = {
            "title": ["My Title"],
            "artist": ["My Artist"],
            "track": ["1"],
            "NB_UUID": ["custom-uuid"]
        }
        
        # Helper to simulate write_fields logic 
        self.sm._write_asf_fields(fields)
        
        tags = self.sm.mfile.tags
        
        # Check mappings
        self.assertIn("Title", tags)
        self.assertEqual(str(tags["Title"][0]), "My Title")
        self.assertIn("Author", tags)
        self.assertEqual(str(tags["Author"][0]), "My Artist")
        self.assertIn("WM/TrackNumber", tags)
        self.assertEqual(str(tags["WM/TrackNumber"][0]), "1")
        # Check custom field preserved
        self.assertIn("NB_UUID", tags)
        self.assertEqual(str(tags["NB_UUID"][0]), "custom-uuid")

    def test_read_wma_mapping(self):
        # Setup ASF mock
        self.sm.mfile = MagicMock(spec=asf.ASF)
        
        def make_attr(val):
            m = MagicMock()
            m.value = val
            return m
            
        self.sm.mfile.tags = {
            "Title": [make_attr("Read Title")],
            "Author": [make_attr("Read Artist")],
            "WM/TrackNumber": [make_attr("5")],
            "NB_UUID": [make_attr("read-uuid")]
        }
        
        fields = self.sm._read_asf_fields(self.sm.mfile.tags, schema='extended')
        
        self.assertEqual(fields["title"], ["Read Title"])
        self.assertEqual(fields["artist"], ["Read Artist"])
        self.assertEqual(fields["track"], ["5"])
        self.assertEqual(fields["NB_UUID"], ["read-uuid"])

    def test_wma_legacy_cleanup(self):
        # Setup ASF mock
        self.sm.mfile = MagicMock(spec=asf.ASF)
        self.sm.mfile.tags = {
            "Title": [], 
            "title": [MagicMock(value="Legacy Title")], 
            "Author": [],
            "artist": [MagicMock(value="Legacy Artist")]
        }
        self.sm.mfile.save = MagicMock()
        
        fields = {"title": ["New Title"], "artist": ["New Artist"]}
        self.sm._write_asf_fields(fields)
        
        tags = self.sm.mfile.tags
        self.assertIn("Title", tags)
        self.assertEqual(str(tags["Title"][0]), "New Title")
        self.assertNotIn("title", tags) # Legacy removed

    # --- MP4 Custom Field Casing Tests ---

    def test_write_mp4_custom_field_case(self):
        # Setup MP4 mock
        self.sm.mfile = MagicMock(spec=mp4.MP4)
        self.sm.mfile.tags = mp4.MP4Tags()
        
        # Write a custom field with mixed case
        fields = {"Nb_Uuid": ["1234"]}
        self.sm._write_mp4_fields(fields)
        
        # Check if it was written with uppercase key (sanitized)
        # mudio adds ----:com.apple.iTunes: prefix for custom fields
        expected = f"----:{Config.DEFAULT_NAMESPACE}:NB_UUID"
        self.assertIn(expected, self.sm.mfile.tags)
        self.assertEqual(self.sm.mfile.tags[expected], [b"1234"])

    def test_overwrite_mixed_case_keys_mp4(self):
        """Test overwriting mixed case keys in MP4 tags."""
        self.sm.mfile = MagicMock(spec=mp4.MP4)
        
        # Tags with mixed case duplicates (simulated)
        tags = {
            '----:com.apple.iTunes:MyKey': [b'Value1'], 
            '----:com.apple.iTunes:mykey': [b'Value1'], 
            '----:com.apple.iTunes:MYKEY': [b'Unique'], 
            '\xa9nam': [b'Old Title']
        }
        self.sm.mfile.tags = tags
        
        new_fields = {
            'mykey': ['New Value'],
            'title': ['New Title']
        }
        
        self.sm._write_mp4_fields(new_fields)
        
        # Canonical Title updated
        assert tags.get('\xa9nam') == ['New Title']
        
        # Custom Keys: Should be sanitized/uppercased to MYKEY
        sanitized_key = '----:com.apple.iTunes:MYKEY'
        assert sanitized_key in tags
        assert tags[sanitized_key] == [b'New Value']
        
        # Check other variations are gone
        assert '----:com.apple.iTunes:MyKey' not in tags
        assert '----:com.apple.iTunes:mykey' not in tags

    def test_overwrite_mixed_case_keys_id3(self):
        """Test overwriting mixed case TXXX frames in ID3."""
        self.sm.mfile = MagicMock()
        self.sm.mfile.tags = id3.ID3()
        
        # Inject mixed case TXXX frames
        self.sm.mfile.tags.add(id3.TXXX(encoding=3, desc='MyKey', text=['Value1']))
        self.sm.mfile.tags.add(id3.TXXX(encoding=3, desc='mykey', text=['Value1']))
        self.sm.mfile.tags.add(id3.TXXX(encoding=3, desc='MYKEY', text=['Unique']))
        self.sm.mfile.tags.add(id3.TIT2(encoding=3, text=['Old Title']))
        
        new_fields = {
            'mykey': ['New Value'],
            'title': ['New Title']
        }
        
        self.sm._write_id3_fields(new_fields)
        
        # Verify Title updated
        assert self.sm.mfile.tags['TIT2'].text == ['New Title']
        
        # TXXX frames - should only have 'MYKEY'
        txxx = self.sm.mfile.tags.getall('TXXX')
        descriptions = [f.desc for f in txxx]
        
        self.assertIn('MYKEY', descriptions)
        self.assertNotIn('MyKey', descriptions)
        self.assertNotIn('mykey', descriptions)
        
        # Verify value
        for f in txxx:
            if f.desc == 'MYKEY':
                assert f.text == ['New Value']

if __name__ == "__main__":
    unittest.main()
