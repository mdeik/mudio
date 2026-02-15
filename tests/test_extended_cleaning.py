
import pytest
import shutil
from pathlib import Path
from mudio.core import SimpleMusic

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
    # Create a source directory to avoid backup collision issues
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    temp_file = source_dir / original_file.name
    shutil.copy2(original_file, temp_file)
    return temp_file

@pytest.mark.parametrize("audio_file", get_audio_files(), indirect=True)
class TestExtendedCleaning:
    """Integration tests to verify extended mode returns clean keys."""

    def test_clean_keys(self, audio_file):
        """Test that keys are cleaned in extended mode."""
        custom_key = "CLEAN_TAG"
        custom_val = "CleanValue"
        
        # 1. Write custom tag
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({custom_key: [custom_val]})
            
        # 2. Read back in extended mode
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            
            # Check for the CLEAN key
            found_key = None
            for k in fields.keys():
                if k.upper() == custom_key:
                    found_key = k
                    break
            
            assert found_key is not None, f"Clean key {custom_key} not found in {fields.keys()}"
            assert custom_val in fields[found_key], f"Value {custom_val} not found in {fields[found_key]}"
            
            # Ensure NO dirty key exists
            dirty_keys = [k for k in fields.keys() if "TXXX:" in k.upper() or "----:" in k]
            # Note: Some existing tags might be TXXX but not ours. 
            # We specifically check for OUR key with prefix.
            
            specific_dirty_keys = [
                k for k in fields.keys() 
                if (f"TXXX:{custom_key}" == k.upper()) or 
                   (f"----:com.apple.iTunes:{custom_key}" == k) or
                   (f"----:{custom_key}" == k)
            ]
            
            assert not specific_dirty_keys, f"Found dirty keys: {specific_dirty_keys}"
