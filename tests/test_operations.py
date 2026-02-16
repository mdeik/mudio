
import pytest
from mudio.operations import (
    FieldOperations,
    write,
    append,
    prefix,
    prefix,
    enlist,
    delist,
    find_replace,
    clear,
    delete,
    match_artists_bipartite,
    match_artist_single
)

class TestFieldOperations:
    """Tests for FieldOperations class."""

    def test_normalize_values_single_valued(self):
        """Test normalization for single-valued fields."""
        # list -> single value
        assert FieldOperations.normalize_values('title', ['A', 'B']) == ['A']
        # empty -> empty
        assert FieldOperations.normalize_values('title', []) == []
        # empty strings -> empty
        assert FieldOperations.normalize_values('title', ['', '   ']) == []

    def test_normalize_values_multi_valued(self):
        """Test normalization for multi-valued fields."""
        # Deduplication and case insensitivity preservation
        assert FieldOperations.normalize_values('artist', ['A', 'a', 'B']) == ['A', 'B']
        # Order preservation
        assert FieldOperations.normalize_values('artist', ['B', 'A']) == ['B', 'A']

    def test_normalize_values_comment(self):
        """Test normalization for comment field (special case)."""
        # Comments should NOT be deduplicated
        assert FieldOperations.normalize_values('comment', ['A', 'A']) == ['A', 'A']


class TestOperations:
    """Tests for operation functions."""

    def test_op_write(self):
        op = write('title', 'New')
        assert op(['Old']) == ['New']
        assert op([]) == ['New']
        
        # Test overwrite with empty value -> clear
        op_empty = write('title', '')
        assert op_empty(['Old']) == []

    def test_op_append(self):
        # Single valued: concatenate
        op = append('title', ' Suffix')
        assert op(['Title']) == ['Title Suffix']
        
        # Multi valued: add new item
        op_multi = append('artist', 'New Artist')
        assert op_multi(['Old Artist']) == ['Old Artist', 'New Artist']
        
        # Comment: append to EACH
        op_comment = append('comment', ' [Live]')
        assert op_comment(['C1', 'C2']) == ['C1 [Live]', 'C2 [Live]']

    def test_op_prefix(self):
        # Single valued: prepend
        op = prefix('title', 'Prefix ')
        assert op(['Title']) == ['Prefix Title']
        
        # Multi valued: prepend to ALL
        op_multi = prefix('artist', 'The ')
        assert op_multi(['Beatles', 'Stones']) == ['The Beatles', 'The Stones']

    def test_op_enlist(self):
        # Enlist only if not exists (for multi-valued)
        op = enlist('artist', 'New')
        assert op(['Old']) == ['Old', 'New']
        assert op(['Old', 'New']) == ['Old', 'New'] # No dupe
        
        # For single valued, behaves like append
        op_single = enlist('title', ' New')
        assert op_single(['Old']) == ['Old New']

    def test_op_delist(self):
        # Remove single value
        op = delist('artist', 'Old')
        assert op(['Old', 'New']) == ['New']
        
        # Remove multiple values
        op_multi = delist('genre', 'Rock;Pop', delimiter=';')
        assert op_multi(['Rock', 'Pop', 'Jazz']) == ['Jazz']
        
        # Case insensitive removal
        op_case = delist('artist', 'old')
        assert op_case(['Old', 'New']) == ['New']
        
        # Handle empty/non-existent
        op_none = delist('artist', 'Missing')
        assert op_none(['Old']) == ['Old']

    def test_op_find_replace_plain(self):
        op = find_replace('title', 'Old', 'New', regex=False)
        assert op(['Old Title']) == ['New Title']
        # Case sensitive check: 'Bold' contains 'old' but we search for 'Old'. 
        # Should NOT match.
        assert op(['Bold Title']) == ['Bold Title']

    def test_op_find_replace_regex(self):
        op = find_replace('title', r'\d+', '#', regex=True)
        assert op(['Track 01']) == ['Track #']

    def test_op_clear(self):
        op = clear('title')
        assert op(['Anything']) == [""]

    def test_op_delete(self):
        """Test delete operation removes field entirely."""
        op = delete('title')
        # delete returns [] to indicate field should be removed
        assert op(['Anything']) == []
        assert op(['Multiple', 'Values']) == []
        assert op([]) == []


class TestArtistMatching:
    """Tests for bipartite artist matching."""

    def test_match_artist_single(self):
        artists = ['Alice', 'Bob']
        assert match_artist_single('ali', artists, regex_flag=False) is True
        assert match_artist_single('z', artists, regex_flag=False) is False
        assert match_artist_single('^A', artists, regex_flag=True) is True

    def test_match_artists_bipartite(self):
        # 2 patterns, 2 artists -> exact match logic check
        # Patterns: "A", "B"
        # Artists: "Artist A", "Artist B"
        # Should match
        assert match_artists_bipartite(['A', 'B'], ['Artist A', 'Artist B'], regex_flag=False) is True
        
        # Patterns > Artists -> False
        assert match_artists_bipartite(['A', 'B', 'C'], ['A', 'B'], regex_flag=False) is False
        
        # Patterns < Artists -> True (subset match)
        assert match_artists_bipartite(['A'], ['Artist A', 'Artist B'], regex_flag=False) is True

