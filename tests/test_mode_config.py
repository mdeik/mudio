
import pytest
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from mudio.core import SimpleMusic
from mudio.utils import Config

# Define the location of the audio files
AUDIO_DIR = Path(__file__).parent / "audio"

def get_audio_files():
    """Generator to yield all audio files from tests/audio."""
    if not AUDIO_DIR.exists():
        return []
    return [
        f for f in AUDIO_DIR.iterdir() 
        if f.is_file() and f.suffix.lower() in SimpleMusic.SUPPORTED_EXT
    ]

@pytest.fixture
def audio_file(request, tmp_path):
    """Fixture that copies the requested audio file to a temporary directory."""
    original_file = request.param
    # Create a source directory
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    temp_file = source_dir / original_file.name
    shutil.copy2(original_file, temp_file)
    return temp_file

class TestModeConfig:
    """Tests for mode configuration."""
    
    def setup_method(self):
        """Reset config before each test."""
        self.original_mode = Config.DEFAULT_SCHEMA
        
    def teardown_method(self):
        """Restore config after each test."""
        Config.DEFAULT_SCHEMA = self.original_mode
        if 'MUDIO_SCHEMA' in os.environ:
            del os.environ['MUDIO_SCHEMA']

    @pytest.mark.parametrize("audio_file", get_audio_files(), indirect=True)
    def test_default_is_extended(self, audio_file):
        """Test that default read_fields() uses extended mode (default)."""
        # Ensure default is extended
        Config.DEFAULT_SCHEMA = 'extended'
        
        custom_key = "DEFAULT_TEST"
        custom_val = "123"
        
        # Write generic custom tag
        with SimpleMusic.managed(audio_file) as sm:
             sm.write_fields({custom_key: [custom_val]})
             
        # Read with default (no mode arg)
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            
            # Should find custom key if extended
            found = any(k.upper() == custom_key for k in fields.keys())
            assert found, "Default mode should be extended and find custom keys"

    @pytest.mark.parametrize("audio_file", get_audio_files(), indirect=True)
    def test_env_var_canonical(self, audio_file):
        """Test setting mode via environment variable to canonical."""
        os.environ['MUDIO_SCHEMA'] = 'canonical'
        Config.load_from_env()
        assert Config.DEFAULT_SCHEMA == 'canonical'
        
        custom_key = "ENV_TEST"
        custom_val = "456"
        
        with SimpleMusic.managed(audio_file) as sm:
             sm.write_fields({custom_key: [custom_val]})
             
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            
            # Should NOT find custom key if canonical
            found = any(k.upper() == custom_key for k in fields.keys())
            assert not found, "Canonical mode should not find custom keys"
            
    def test_invalid_mode(self):
        """Test that invalid mode raises ValueError."""
        os.environ['MUDIO_SCHEMA'] = 'invalid_mode'
        with pytest.raises(ValueError, match="Invalid DEFAULT_SCHEMA"):
            Config.load_from_env()
