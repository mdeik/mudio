
"""
Integration tests for specific audio features: Custom fields, Canonicalization, etc.
"""
import pytest
import shutil
from pathlib import Path
from mudio.core import SimpleMusic
from mudio.processor import process_file
from mudio.operations import write, append, find_replace, delete
import mutagen.id3 as id3
from mutagen.mp3 import MP3

class TestAudioFeatures:
    """Integration tests for custom fields, canonicalization, and advanced features."""

    # --- Custom Fields Tests ---

    def test_write_read_custom_field(self, audio_file):
        """Test writing and reading a custom field."""
        custom_key = "my_multi_tag"
        custom_val = "CustomValue123"
        
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({custom_key: [custom_val]})
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            
            found_val = None
            for k, v in fields.items():
                if k.upper() == custom_key.upper():
                    found_val = v
                    break
                if k.upper().endswith(f":{custom_key.upper()}"):
                    found_val = v
                    break
                    
            assert found_val is not None, f"Custom field {custom_key} not found"
            assert custom_val in found_val

    def test_delete_custom_field(self, audio_file):
        """Test deleting a custom field using the delete operation."""
        custom_field = "TEMP_TAG_FOR_DELETE"
        custom_value = "temporary-value"
        
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({custom_field: [custom_value]})
        
        result = process_file(
            str(audio_file),
            ops=[delete(custom_field)],
            read_schema="extended"
        )
        assert result['passed']
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema="extended")
            found_key = None
            for k in fields.keys():
                if k.upper() == custom_field.upper() or k.upper().endswith(f":{custom_field.upper()}"):
                    found_key = k
                    break
            assert found_key is None

    def test_clean_keys_extended(self, audio_file):
        """Test that keys are cleaned in extended mode."""
        custom_key = "CLEAN_TAG"
        custom_val = "CleanValue"
        
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({custom_key: [custom_val]})
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            
            found = any(k.upper() == custom_key for k in fields.keys())
            assert found, f"Clean key {custom_key} not found"
            
            # Ensure NO dirty key exists
            specific_dirty_keys = [
                k for k in fields.keys() 
                if (f"TXXX:{custom_key}" == k.upper()) or 
                   (f"----:com.apple.iTunes:{custom_key}" == k) or
                   (f"----:{custom_key}" == k)
            ]
            assert not specific_dirty_keys

    # --- Canonicalization Tests ---

    def test_canonical_write_read(self, audio_file):
        """Test that mixed-case canonical keys are normalized on write."""
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({
                'Title': ['Canonical Title'],
                'ARTIST': ['Canonical Artist'],
                'MyField': ['Custom Value']
            })

        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            
            assert fields['title'] == ['Canonical Title']
            assert 'Title' not in fields
            assert fields['artist'] == ['Canonical Artist']
            
            # Custom field preserved (sanitized to lower on read)
            assert fields['myfield'] == ['Custom Value']

    def test_case_insensitive_merge_on_read(self, audio_file):
        """Test that pre-existing mixed-case tags are merged on read."""
        if audio_file.suffix.lower() != ".mp3":
             return

        audio = MP3(audio_file)
        if audio.tags is None: audio.add_tags()
        audio.tags.delall('TCON')
        
        audio.tags.add(id3.TCON(encoding=3, text=['Rock']))
        audio.tags.add(id3.TXXX(encoding=3, desc='GENRE', text=['Pop']))
        audio.tags.add(id3.TXXX(encoding=3, desc='genre', text=['Jazz']))
        audio.save()
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            assert 'genre' in fields
            assert 'Rock' in fields['genre']
            assert 'Pop' in fields['genre']
            assert 'Jazz' in fields['genre']

    def test_frame_level_dedupe(self, audio_file):
        """Two frames with identical value lists within same audio file."""
        if audio_file.suffix.lower() != ".mp3": return

        audio = MP3(audio_file)
        if audio.tags is None: audio.add_tags()
        
        # 1. Identical value lists but different keys (case) -> merged
        audio.tags.add(id3.TXXX(encoding=3, desc='MyTag', text=['a', 'b']))
        audio.tags.add(id3.TXXX(encoding=3, desc='mytag', text=['a', 'b'])) 
        audio.save()
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            assert 'mytag' in fields
            # Merged content
            assert sorted(fields['mytag']) == sorted(['a', 'b'])


    def test_unknown_keys_passthrough(self, audio_file):
        """MyField persists as myfield; no extra variants written."""
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({'MyField': ['Value']})
            
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields(schema='extended')
            assert 'myfield' in fields
            assert 'MYFIELD' not in fields
