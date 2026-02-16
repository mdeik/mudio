
import pytest
import shutil
from pathlib import Path
from mudio.core import SimpleMusic
import mutagen.mp4 as mp4
import mutagen.id3 as id3
from mutagen.mp3 import MP3

class TestCustomKeyCasing:
    
    @pytest.fixture
    def audio_file(self, tmp_path):
        """Create a temporary MP4 file for testing."""
        # Using MP4 as it's the primary case where we saw this issue, 
        # but the logic should hold for ID3 too.
        
        # Create a dummy MP4 file
        source = Path("tests/samples/test.m4a") 
        # Ideally we'd valid sample, but if not available we can mock or use existing fixture.
        # Check if tests/samples exists or if we need to generate one.
        # Looking at existing tests, they often use 'audio_template' fixture.
        # But here I'll try to use a mock-like approach or just rely on the fact 
        # that 'tests/samples/test.m4a' might exist if I look at project structure 
        # or just create a minimal valid atom manually?
        # Actually, let's look at how other tests create files.
        pass

    def test_overwrite_mixed_case_keys_mp4(self, tmp_path):
        # We need a valid MP4 file. Since I cannot easily create one from scratch without a binary,
        # I will rely on mocking the mutagen object structure if I can't find a sample,
        # OR I'll assume valid file creation is handled by fixtures in conftest.
        # checking conftest might be useful. 
        # For now, I'll use a Mock approach similar to reproduce scripts OR
        # better: use unittest.mock to simulate the file load and save behavior
        # ensuring the logic in SimpleMusic._write_mp4_fields is tested.
        
        # However, the request asks for a "test" which usually implies integration.
        # Let's try to verify with real logic if possible.
        
        from unittest.mock import MagicMock
        
        # Mocking SimpleMusic to avoid real file I/O dependencies for this logic test
        sm = SimpleMusic.__new__(SimpleMusic)
        sm.mfile = MagicMock(spec=mp4.MP4)
        
        # Scenario: 3 keys same name different case
        # MP4 tags: '----:com.apple.iTunes:MyKey', '----:com.apple.iTunes:mykey', '----:com.apple.iTunes:MYKEY'
        # 2 have same value, 1 unique
        
        tags = {
            '----:com.apple.iTunes:MyKey': [b'Value1'], # Same value
            '----:com.apple.iTunes:mykey': [b'Value1'], # Same value
            '----:com.apple.iTunes:MYKEY': [b'Unique'], # Unique value
            '\xa9nam': [b'Old Title']
        }
        sm.mfile.tags = tags
        
        # Action: Overwrite value by accessing key with [a-z0-9]
        # And change title
        new_fields = {
            'mykey': ['New Value'],
            'title': ['New Title']
        }
        
        # We need to invoke the write logic.
        # sm.write_fields calls _write_mp4_fields
        # But _write_mp4_fields writes to sm.mfile.tags.
        # We need to make sure sm.write_fields logic is executed.
        
        # Inject the methods we need
        # We can implement a partial mock or just call the method if available
        # I'll instantiate a real SimpleMusic with a dummy file path, but mock the internal mfile.
        
        sm.path = Path("dummy.m4a")
        # We specifically want to test logic covering "uppercase version is written, others dropped"
        
        # Emulate _write_mp4_fields execution
        # Since I can't easily rely on 'write_fields' without a real file or complex mocking of 'save',
        # I will test '_write_mp4_fields' directly, which is where the logic resides.
        
        sm._write_mp4_fields(new_fields)
        
        print(f"Tags after write: {tags.keys()}")
        
        # Expected behavior:
        # - uppercase version of custom key is written to (MYKEY)
        # - others cases are dropped (MyKey, mykey gone)
        
        # Canonical Title updated
        assert tags.get('\xa9nam') == ['New Title']
        
        # Custom Keys
        # The key should be sanitized/uppercased: MYKEY
        # In MP4: ----:com.apple.iTunes:MYKEY
        
        sanitized_key = '----:com.apple.iTunes:MYKEY'
        assert sanitized_key in tags
        assert tags[sanitized_key] == [b'New Value']
        
        # Check other variations are gone
        assert '----:com.apple.iTunes:MyKey' not in tags
        assert '----:com.apple.iTunes:mykey' not in tags

    def test_overwrite_mixed_case_keys_id3(self):
        from unittest.mock import MagicMock
        sm = SimpleMusic.__new__(SimpleMusic)
        sm.mfile = MagicMock()
        sm.mfile.tags = id3.ID3()
        
        # Inject mixed case TXXX frames
        # TXXX:MyKey, TXXX:mykey, TXXX:MYKEY
        sm.mfile.tags.add(id3.TXXX(encoding=3, desc='MyKey', text=['Value1']))
        sm.mfile.tags.add(id3.TXXX(encoding=3, desc='mykey', text=['Value1']))
        sm.mfile.tags.add(id3.TXXX(encoding=3, desc='MYKEY', text=['Unique']))
        sm.mfile.tags.add(id3.TIT2(encoding=3, text=['Old Title']))
        
        new_fields = {
            'mykey': ['New Value'],
            'title': ['New Title']
        }
        
        sm._write_id3_fields(new_fields)
        
        # Verify
        # Title updated
        assert sm.mfile.tags['TIT2'].text == ['New Title']
        
        # TXXX frames
        txxx = sm.mfile.tags.getall('TXXX')
        descriptions = [f.desc for f in txxx]
        print(f"TXXX descriptions: {descriptions}")
        
        # Should only have 'MYKEY' (uppercase)
        assert 'MYKEY' in descriptions
        assert 'MyKey' not in descriptions
        assert 'mykey' not in descriptions
        
        # Verify value
        for f in txxx:
            if f.desc == 'MYKEY':
                assert f.text == ['New Value']

if __name__ == "__main__":
    t = TestCustomKeyCasing()
    t.test_overwrite_mixed_case_keys_mp4(None)
    t.test_overwrite_mixed_case_keys_id3()
