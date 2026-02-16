
import unittest
from unittest.mock import MagicMock, patch
import mutagen.asf as asf
import mutagen.mp4 as mp4
from mudio.core import SimpleMusic

class TestWMAMP4Fields(unittest.TestCase):
    def setUp(self):
        self.sm = SimpleMusic.__new__(SimpleMusic)
        self.sm.path = MagicMock()
        self.sm.mfile = MagicMock()

    def test_canon_key_preserves_case(self):
        # Test that canon_key preserves case for unknown keys
        from mudio.core import canon_key
        self.assertEqual(canon_key("NB_UUID"), "NB_UUID")
        self.assertEqual(canon_key("nb_uuid"), "nb_uuid")
        self.assertEqual(canon_key("Title"), "title") # Known key

    def test_write_mp4_custom_field_case(self):
        # Setup MP4 mock
        self.sm.mfile = MagicMock(spec=mp4.MP4)
        self.sm.mfile.tags = mp4.MP4Tags()
        
        # Write a custom field with mixed case
        # Write a custom field with mixed case
        fields = {"Nb_Uuid": ["1234"]}
        self.sm.write_fields(fields)
        
        # Check if it was written with uppercase key
        # Check if it was written with uppercase key
        # mudio adds ----:com.apple.iTunes: prefix for custom fields
        from mudio.utils import Config
        expected = f"----:{Config.DEFAULT_NAMESPACE}:NB_UUID"
        self.assertIn(expected, self.sm.mfile.tags)
        self.assertEqual(self.sm.mfile.tags[expected], [b"1234"])

    def test_write_wma_mapping(self):
        # Setup ASF mock
        self.sm.mfile = MagicMock(spec=asf.ASF)
        self.sm.mfile.tags = {} 
        
        # Mock saving
        self.sm.mfile.save = MagicMock()

        # Write canonical fields
        fields = {
            "title": ["My Title"],
            "artist": ["My Artist"],
            "track": ["1"],
            "NB_UUID": ["custom-uuid"]
        }
        
        # Helper to simulate write_fields logic which calls _write_asf_fields
        # We need to bind the method to the instance since we bypassed __init__
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
        # Setup ASF mock using a real-ish dict structure for tags
        self.sm.mfile = MagicMock(spec=asf.ASF)
        
        # Mock ASF attributes
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
        
        # Run read_fields
        # We need to ensure _read_asf_fields is callable
        fields = self.sm._read_asf_fields(self.sm.mfile.tags, schema='extended')
        
        self.assertEqual(fields["title"], ["Read Title"])
        self.assertEqual(fields["artist"], ["Read Artist"])
        self.assertEqual(fields["track"], ["5"])
        self.assertEqual(fields["NB_UUID"], ["read-uuid"])

    def test_wma_legacy_cleanup(self):
        # Setup ASF mock with both native and legacy tags
        self.sm.mfile = MagicMock(spec=asf.ASF)
        # Mock deletion
        self.sm.mfile.tags = {
            "Title": [], # Will be overwritten
            "title": [MagicMock(value="Legacy Title")], # Should be removed
            "Author": [],
            "artist": [MagicMock(value="Legacy Artist")] # Should be removed
        }
        
        # Mock saving
        self.sm.mfile.save = MagicMock()
        
        # Write new fields
        fields = {
            "title": ["New Title"],
            "artist": ["New Artist"]
        }
        
        self.sm._write_asf_fields(fields)
        
        tags = self.sm.mfile.tags
        
        # Check native fields set
        self.assertIn("Title", tags)
        self.assertEqual(str(tags["Title"][0]), "New Title")
        
        self.assertIn("Author", tags)
        self.assertEqual(str(tags["Author"][0]), "New Artist")
        
        # Check legacy fields removed
        self.assertNotIn("title", tags)
        self.assertNotIn("artist", tags)

if __name__ == "__main__":
    unittest.main()
