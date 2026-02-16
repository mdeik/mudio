import pytest
import shutil
from pathlib import Path
from mudio.core import SimpleMusic
from mudio.processor import process_file
from mudio.operations import write, append, find_replace, delete

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
        custom_key = "my_multi_tag"
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
            
            found_val = None
            found_key = None
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
            
            # Find key case-insensitively
            found_val = []
            for k, v in fields.items():
                if k.lower() == custom_key.lower():
                    found_val = v
                    break
            
            assert "Value A" in found_val, f"Value A not found in {fields}"
            assert "Value B" in found_val


# NEW TEST CLASS using mudio.operations
@pytest.mark.parametrize("audio_file", get_audio_files(), indirect=True)
class TestOperationsWrite:
    """Integration tests using the `write` operation from mudio.operations."""

    def test_write_operation_single_field(self, audio_file, tmp_path):
        """Test using the `write` operation to set a single field."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        # Use the write operation to set the album field
        result = process_file(
            str(audio_file),
            ops={'album': write('album', 'Test Album Value')},
            targeted_fields=['album'],
            backup_dir=str(backup_dir),
            verify=True
        )
        
        # Verify the operation succeeded
        assert result['passed'], f"Operation failed: {result.get('error')}"
        assert result['wrote'], "Write operation did not occur"
        assert result['verified'], "Verification failed"
        assert 'album' in result['changed'], "Album field was not changed"
        
        # Verify by reading back
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            assert 'album' in fields, "Album field not found"
            assert 'Test Album Value' in fields['album'], f"Expected 'Test Album Value' in {fields['album']}"

    def test_write_operation_multi_value_field(self, audio_file, tmp_path):
        """Test using the `write` operation with multi-value delimiter."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        # Write multiple genres using semicolon delimiter
        result = process_file(
            str(audio_file),
            ops={'genre': write('genre', 'Rock;Jazz;Electronic')},
            targeted_fields=['genre'],
            backup_dir=str(backup_dir),
            verify=True
        )
        
        assert result['passed'], f"Operation failed: {result.get('error')}"
        
        # Verify all values are present (format may store as list or joined string)
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            assert 'genre' in fields, "Genre field not found"
            
            # Check that all values are present (handling both list and joined formats)
            genre_values = " ".join(fields['genre']).lower()
            assert 'rock' in genre_values
            assert 'jazz' in genre_values
            assert 'electronic' in genre_values

    def test_write_operation_overwrite_existing(self, audio_file, tmp_path):
        """Test that write operation properly overwrites existing values."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        # First, set an initial value using SimpleMusic directly
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({'title': ['Original Title']})
        
        # Now overwrite using the write operation
        result = process_file(
            str(audio_file),
            ops={'title': write('title', 'New Title Value')},
            targeted_fields=['title'],
            backup_dir=str(backup_dir),
            verify=True
        )
        
        assert result['passed'], f"Operation failed: {result.get('error')}"
        
        # Verify the new value is present and old value is gone
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            assert 'title' in fields, "Title field not found"
            assert 'New Title Value' in fields['title'], f"Expected 'New Title Value' in {fields['title']}"
            assert 'Original Title' not in fields['title'], "Old title value should have been overwritten"

    def test_write_operation_with_backup_and_rollback(self, audio_file, tmp_path):
        """Test that write operation creates backups and handles rollback."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        # Set an initial value
        with SimpleMusic.managed(audio_file) as sm:
            original_fields = sm.read_fields(schema='extended')
            sm.write_fields({'artist': ['Original Artist']})
        
        # Perform write operation with backup
        result = process_file(
            str(audio_file),
            ops={'artist': write('artist', 'Modified Artist')},
            targeted_fields=['artist'],
            backup_dir=str(backup_dir),
            verify=True,
            delete_backups=False  # Keep backup for verification
        )
        
        assert result['passed'], f"Operation failed: {result.get('error')}"
        
        # Verify backup was created
        backup_files = list(backup_dir.glob("*"))
        assert len(backup_files) > 0, "Backup file was not created"
        
        # Verify the change was applied
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            assert 'artist' in fields
            assert 'Modified Artist' in fields['artist']


@pytest.mark.parametrize("audio_file", get_audio_files(), indirect=True)
class TestOperationsDeleteCustomField:
    """Integration tests for deleting custom fields using mudio.operations."""

    def test_delete_custom_field(self, audio_file):
        """Test deleting a custom field (TXXX/Vorbis/etc) using the delete operation."""
        custom_field = "TEMP_TAG_FOR_DELETE"
        custom_value = "temporary-value"
        
        # First, ensure the custom field exists by writing it directly
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({custom_field: [custom_value]})
        
        # Verify the field was written
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema="extended")
            # Handle case variations and MP4 freeform naming
            found_key = None
            for k, v in fields.items():
                if k.upper() == custom_field.upper():
                    found_key = k
                    break
                if k.upper().endswith(f":{custom_field.upper()}"):
                    found_key = k
                    break
            
            assert found_key is not None, f"Setup failed: Custom field {custom_field} not found after writing"
        
        # Now delete the custom field using the operations interface
        result = process_file(
            str(audio_file),
            ops={custom_field: delete(custom_field)},
            targeted_fields=[custom_field],
            read_schema="extended"  # Read extended to verify custom tag deletion
        )
        
        # Verify the operation succeeded
        assert result['passed'], f"Delete operation failed: {result.get('error')}"
        assert result['wrote'], "Delete operation did not modify the file"
        assert custom_field in result['changed'] or any(
            k.upper() == custom_field.upper() or k.upper().endswith(f":{custom_field.upper()}")
            for k in result.get('changed', {}).keys()
        ), "Custom field was not reported as changed"
        
        # Verify the field was actually deleted by reading back
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema="extended")
            
            # Check that the custom field is no longer present
            found_key = None
            for k, v in fields.items():
                if k.upper() == custom_field.upper():
                    found_key = k
                    break
                if k.upper().endswith(f":{custom_field.upper()}"):
                    found_key = k
                    break
            
            assert found_key is None, f"Custom field {custom_field} still exists after deletion: {fields.get(found_key)}"

    def test_delete_nonexistent_custom_field(self, audio_file):
        """Test deleting a custom field that doesn't exist (should not fail)."""
        custom_field = "NONEXISTENT_TAG_XYZ"
        
        # Ensure the field doesn't exist initially
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema="extended")
            for k in fields.keys():
                if k.upper() == custom_field.upper() or k.upper().endswith(f":{custom_field.upper()}"):
                    # Field exists, write empty to clear it first
                    sm.write_fields({custom_field: []})
                    break
        
        # Attempt to delete the non-existent field
        result = process_file(
            str(audio_file),
            ops={custom_field: delete(custom_field)},
            targeted_fields=[custom_field],
            read_schema="extended"
        )
        
        # Operation should pass even if field didn't exist (idempotent behavior)
        assert result['passed'], f"Delete operation failed for non-existent field: {result.get('error')}"

    def test_delete_custom_field_with_backup(self, audio_file, tmp_path):
        """Test deleting a custom field with backup creation."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        custom_field = "TEMP_TAG_FOR_DELETE"
        custom_value = "temporary-value"
        
        # Write the custom field first
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({custom_field: [custom_value]})
        
        # Delete with backup enabled
        result = process_file(
            str(audio_file),
            ops={custom_field: delete(custom_field)},
            targeted_fields=[custom_field],
            backup_dir=str(backup_dir),
            verify=True,
            delete_backups=False  # Keep backup for verification
        )
        
        assert result['passed'], f"Delete operation failed: {result.get('error')}"
        assert result['verified'], "Verification failed after delete"
        
        # Verify backup was created
        backup_files = list(backup_dir.glob("*"))
        assert len(backup_files) > 0, "Backup file was not created"
        
        # Verify field is gone
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema="extended")
            for k in fields.keys():
                if k.upper() == custom_field.upper() or k.upper().endswith(f":{custom_field.upper()}"):
                    pytest.fail(f"Custom field {custom_field} still exists after deletion with backup")