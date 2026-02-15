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
class TestCustomFieldsReal:
    """Integration tests for custom fields on real audio files."""

    def test_write_read_custom_field(self, audio_file):
        """Test writing and reading a custom field."""
        custom_key = "MY_CUSTOM_TAG"
        custom_val = "CustomValue123"
        
        # 1. Write
        with SimpleMusic.managed(audio_file) as sm:
            # We must use list for values
            sm.write_fields({custom_key: [custom_val]})
            
        # 2. Read back (extended mode)
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            
            # Check for the key
            # Note: casing might change depending on format (e.g. Vorbis is case-insensitive usually, but mapped to lower)
            # Our core.py tends to keep keys as is for extended, or specific mapping.
            
            # Helper to find key case-insensitively
            found_val = None
            found_key = None
            for k, v in fields.items():
                if k.upper() == custom_key.upper():
                    found_val = v
                    found_key = k
                    break
                # Special handling for MP4 freeform
                if k.upper().endswith(f":{custom_key.upper()}"):
                    found_val = v
                    found_key = k
                    break
                    
            assert found_val is not None, f"Custom field {custom_key} not found in {fields.keys()}"
            assert custom_val in found_val, f"Value {custom_val} not found in {found_val}"

    def test_write_read_custom_field_multi_value(self, audio_file):
        """Test writing and reading a multi-valued custom field."""
        # WMA/ASF and some others might struggle with true multi-value custom tags in some libs,
        # but let's test what works.
        
        # Skip formats known to have issues with multi-value custom tags if necessary
        # For now, try all.
        
        custom_key = "MY_MULTI_TAG"
        custom_vals = ["Value A", "Value B"]
        
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({custom_key: custom_vals})
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            
            found_val = []
            for k, v in fields.items():
                if k.upper() == custom_key.upper():
                    found_val = v
                    break
                if k.upper().endswith(f":{custom_key.upper()}"):
                    found_val = v
                    break
            
            # If the format supports it, we expect both. 
            # If not, we might get joined string or just first one field.
            # We accept either full success or joined string for pass, 
            # as long as data isn't lost.
            
            flat_vals = [str(x) for x in found_val]
            
            # Check if values are present
            # They might be separate: ['Value A', 'Value B']
            # Or joined: ['Value A; Value B'] or ['Value A/Value B']
            
            combined = " ".join(flat_vals)
            assert "Value A" in combined
            assert "Value B" in combined
