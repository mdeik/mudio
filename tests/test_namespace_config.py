
import os
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from mudio.core import SimpleMusic
from mudio.utils import Config
import mutagen.mp4 as mp4

class TestNamespaceConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="mudio_test_namespace_"))
        self.original_namespace = Config.DEFAULT_NAMESPACE
        
    def tearDown(self):
        Config.DEFAULT_NAMESPACE = self.original_namespace
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def test_custom_namespace_write_read(self):
        """Test writing and reading with a custom namespace."""
        
        # 1. Setup custom namespace in env
        custom_namespace = "org.mudio.custom"
        with patch.dict(os.environ, {"MUDIO_NAMESPACE": custom_namespace}):
            # Reload config to pick up env var
            Config.load_from_env()
            self.assertEqual(Config.DEFAULT_NAMESPACE, custom_namespace)
            
            # 2. Create a dummy MP4 file (copy from test data)
            test_file = self.test_dir / "test.m4a"
            src_file = Path("tests/audio/silence.m4a")
            if not src_file.exists():
                self.skipTest("tests/audio/silence.m4a not found")
                
            shutil.copy(src_file, test_file)
            
            # 3. Write a custom field
            sm = SimpleMusic(test_file)
            sm.write_fields({'my_custom_field': ['Test Value']})
            sm.close()
            
            # 4. Verify the raw tag has the custom namespace
            m = mp4.MP4(test_file)
            expected_key = f"----:{custom_namespace}:MY_CUSTOM_FIELD"
            self.assertIn(expected_key, m.tags)
            self.assertEqual(m.tags[expected_key], [b"Test Value"])
            
            # 5. Verify reading back
            sm = SimpleMusic(test_file)
            fields = sm.read_fields(schema='extended')
            self.assertIn('my_custom_field', fields)
            self.assertEqual(fields['my_custom_field'], ['Test Value'])
            sm.close()

if __name__ == "__main__":
    unittest.main()
