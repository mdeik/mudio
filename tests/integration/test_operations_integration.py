
"""
Integration tests for operations module (sequencing, interactions).
"""
import pytest
from mudio.processor import process_file
from mudio.operations import write, append, find_replace, prefix, delete, clear
from mudio.core import SimpleMusic

class TestOperationsIntegration:
    """Test applying multiple operations in a single pass."""

    def test_multi_ops_same_field_sequential(self, audio_file):
        """Test multiple operations on the same field applied sequentially."""
        # 1. Write 'Hello'
        # 2. Append ' World'
        # 3. Prefix 'Says: '
        ops = [
            write('title', 'Hello'),
            append('title', ' World'),
            prefix('title', 'Says: ')
        ]
        
        result = process_file(str(audio_file), ops=ops)
        assert result['passed'] is True
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['title'] == ['Says: Hello World']

    def test_multi_ops_different_fields(self, audio_file):
        """Test operations on different fields in the same list."""
        ops = [
            write('artist', 'New Artist'),
            write('album', 'New Album'),
            append('comment', ' - Audited')
        ]
        
        # Setup initial comment
        with SimpleMusic.managed(audio_file) as sm:
            sm.write_fields({'comment': ['Original']})
            
        result = process_file(str(audio_file), ops=ops)
        assert result['passed'] is True
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['artist'] == ['New Artist']
            assert fields['album'] == ['New Album']
            assert fields['comment'] == ['Original - Audited']

    def test_multi_ops_order_dependence(self, audio_file):
        """Verify that operations are applied in the order specified in the list."""
        # Case A: Write then Replace
        ops_a = [
            write('title', 'Foo'),
            find_replace('title', 'Foo', 'Bar')
        ]
        
        process_file(str(audio_file), ops=ops_a)
        with SimpleMusic.managed(audio_file) as sm:
            assert sm.read_fields()['title'] == ['Bar']
            
        # Case B: Replace then Write
        ops_b = [
            find_replace('title', 'Bar', 'Baz'),
            write('title', 'Quux')
        ]
        
        process_file(str(audio_file), ops=ops_b)
        with SimpleMusic.managed(audio_file) as sm:
            assert sm.read_fields()['title'] == ['Quux']

    def test_multi_ops_interactions(self, audio_file):
        """Test complex interactions like clear then append."""
        ops = [
            write('title', 'Old Title'), # Setup
            clear('title'),              # -> ['']
            append('title', 'New Start') # -> ['New Start']
        ]
        
        result = process_file(str(audio_file), ops=ops)
        assert result['passed'] is True
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['title'] == ['New Start']

    def test_multi_ops_delete_then_write(self, audio_file):
        """Test deleting a field then writing it back."""
        ops = [
            write('genre', 'Rock'),
            delete('genre'),
            write('genre', 'Jazz')
        ]
        
        result = process_file(str(audio_file), ops=ops)
        
        with SimpleMusic.managed(audio_file) as sm:
            fields = sm.read_fields()
            assert fields['genre'] == ['Jazz']
