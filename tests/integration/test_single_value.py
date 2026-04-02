import unittest
from pathlib import Path
import tempfile
import shutil
import os
from mudio.core import SimpleMusic
from mudio.processor import process_file
from mudio.operations import write, enlist, delist

class TestSingleValueFields(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="mudio_sv_test_"))
        
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def create_dummy_flac(self, name="test.flac"):
        src = Path("tests/audio/silence.flac")
        dst = self.test_dir / name
        shutil.copy(src, dst)
        return dst

    def test_semicolon_preservation_in_title(self):
        path = self.create_dummy_flac()
        
        # Write title with semicolon
        title_val = "Whatcha;Whatcha Doin'"
        result = process_file(str(path), [write('title', title_val)])
        
        self.assertTrue(result['passed'], f"Process failed: {result.get('error')}")
        
        # Verify read back
        with SimpleMusic.managed(path) as sm:
            fields = sm.read_fields()
            self.assertEqual(fields['title'], [title_val])
            
    def test_single_value_truncation(self):
        path = self.create_dummy_flac()
        
        # Manually create a multi-value list for title (in memory)
        # and verify only index 0 is written
        with SimpleMusic.managed(path) as sm:
            # write_fields will truncate
            sm.write_fields({'title': ['Title 1', 'Title 2']})
            
        # Verify read back
        with SimpleMusic.managed(path) as sm:
            fields = sm.read_fields()
            self.assertEqual(fields['title'], ['Title 1'])
            
    def test_enlist_on_single_value(self):
        path = self.create_dummy_flac()
        
        # Write initial title
        process_file(str(path), [write('title', 'Initial')])
        
        # Enlist another title (should work in memory but only first written)
        # Wait, the user said "enlist will function normally... but only index 0 written"
        process_file(str(path), [enlist('title', 'Second')], verify=False)
        
        with SimpleMusic.managed(path) as sm:
            fields = sm.read_fields()
            self.assertEqual(fields['title'], ['Initial'])

    def test_multi_value_fields_still_split(self):
        path = self.create_dummy_flac()
        
        # Write genre with semicolon (should SPLIT)
        process_file(str(path), [write('genre', 'Rock;Pop')])
        
        with SimpleMusic.managed(path) as sm:
            fields = sm.read_fields()
            self.assertEqual(sorted(fields['genre']), ['Pop', 'Rock'])

    def test_comment_is_multi_value(self):
        path = self.create_dummy_flac()
        
        # Write comment with semicolon (should SPLIT now)
        process_file(str(path), [write('comment', 'C1;C2')])
        
        with SimpleMusic.managed(path) as sm:
            fields = sm.read_fields()
            self.assertEqual(sorted(fields['comment']), ['C1', 'C2'])

    def test_custom_field_is_single_value(self):
        path = self.create_dummy_flac()
        
        # Write custom field with semicolon (should NOT split now)
        process_file(str(path), [write('my_custom', 'V1;V2')])
        
        with SimpleMusic.managed(path) as sm:
            fields = sm.read_fields()
            # Custom fields are single-valued by default
            self.assertEqual(fields['my_custom'], ['V1;V2'])

if __name__ == "__main__":
    unittest.main()
