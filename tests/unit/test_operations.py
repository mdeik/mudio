
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
        """Test normalization for fields previously considered single-valued."""
        # list -> single value treated as list always
        assert FieldOperations.normalize_values('title', ['A', 'B']) == ['A', 'B']
        # empty -> empty string item [""] (changed from [])
        assert FieldOperations.normalize_values('title', []) == []
        # empty strings -> dropped
        assert FieldOperations.normalize_values('title', ['']) == []
        # whitespace -> dropped
        assert FieldOperations.normalize_values('title', ['   ']) == []

    def test_normalize_values_multi_valued(self):
        """Test normalization for multi-valued fields."""
        # Deduplication and case insensitivity preservation
        assert FieldOperations.normalize_values('artist', ['A', 'a', 'B']) == ['A', 'B']
        # Order preservation
        assert FieldOperations.normalize_values('artist', ['B', 'A']) == ['B', 'A']

    def test_normalize_values_comment(self):
        """Test normalization for comment field."""
        # Comments ARE now deduplicated
        assert FieldOperations.normalize_values('comment', ['A', 'A']) == ['A']


class TestOperations:
    """Tests for operation functions."""

    def test_op_write(self):
        op = write('title', 'New')
        assert op(['Old']) == ['New']
        assert op([]) == ['New']
        
        # Test overwrite with empty value -> empty string item
        op_empty = write('title', '')
        assert op_empty(['Old']) == []

    def test_op_append(self):
        # Single item list: append to item
        op = append('title', ' Suffix')
        assert op(['Title']) == ['Title Suffix']
        
        # Multi item list: append to ALL items
        op_multi = append('artist', ' [Remix]')
        assert op_multi(['Old Artist']) == ['Old Artist [Remix]']
        assert op_multi(['A', 'B']) == ['A [Remix]', 'B [Remix]']
        
        # Comment: append to EACH
        op_comment = append('comment', ' [Live]')
        assert op_comment(['C1', 'C2']) == ['C1 [Live]', 'C2 [Live]']

    def test_op_enlist_genre_delimiter_variations(self):
        """Test that genre enlist handles delimiter variations correctly."""
        # All variations should produce the same result due to normalization
        initial = ['Pop', 'Rock']
        expected = ['Pop', 'Rock', 'R&B']
        
        # Plain value without delimiter
        op1 = enlist('genre', 'R&B')
        assert op1(initial) == expected
        
        # Leading delimiter (creates empty string that gets stripped)
        op2 = enlist('genre', ';R&B')
        assert op2(initial) == expected
        
        # Leading delimiter with space (whitespace gets stripped)
        op3 = enlist('genre', '; R&B')
        assert op3(initial) == expected
        
        # Leading and trailing delimiters (empty strings stripped)
        op4 = enlist('genre', '; R&B; ')
        assert op4(initial) == expected
        
        # Verify deduplication works (case-insensitive)
        op5 = enlist('genre', 'pop')
        assert op5(initial) == ['Pop', 'Rock']  # 'pop' not added (duplicate)
        
        # Edge case: multiple delimiters, spaces, and trailing whitespace
        op6 = enlist('genre', ';;; ; ;Alternative; Indie  ')
        assert op6(initial) == ['Pop', 'Rock', 'Alternative', 'Indie']

    def test_op_prefix(self):
        # Single item list: prepend to item
        op = prefix('title', 'Prefix ')
        assert op(['Title']) == ['Prefix Title']
        
        # Multi item list: prepend to ALL items
        op_multi = prefix('artist', 'The ')
        assert op_multi(['Beatles', 'Stones']) == ['The Beatles', 'The Stones']

    def test_op_enlist(self):
        # Enlist only if not exists (for multi-valued)
        op = enlist('artist', 'New')
        assert op(['Old']) == ['Old', 'New']
        assert op(['Old', 'New']) == ['Old', 'New'] # No dupe
        
        # For fields previously single-valued, now behaves like multi-valued (adds item)
        op_single = enlist('title', 'New')
        assert op_single(['Old']) == ['Old', 'New']

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

