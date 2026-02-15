"""
Field operations and transformation logic for mudio.
"""

import re
from typing import Dict, List, Tuple, Callable

from .core import SimpleMusic
from .utils import safe_regex_pattern

# ---------- Type Definitions ----------
FieldOperationsType = Dict[str, Callable[[List[str]], List[str]]]
FieldValuesType = Dict[str, List[str]]
FilterType = Tuple[str, str, bool]

# ---------- Field Operations ----------
class FieldOperations:
    """Unified field operations with consistent multi-value handling."""
    
    # Define which fields are multi-valued
    MULTI_VALUED_FIELDS = {'artist', 'genre', 'albumartist', 'performer', 'composer'}
    SINGLE_VALUED_FIELDS = {'title', 'album', 'date', 'track', 'totaltracks', 'disc', 'totaldiscs'}
    SPECIAL_MULTI_FIELDS = {'comment'}  # Comment can be multi-valued but has special handling
    
    @classmethod
    def is_multi_valued(cls, field_name: str) -> bool:
        return field_name in cls.MULTI_VALUED_FIELDS
    
    @classmethod
    def is_single_valued(cls, field_name: str) -> bool:
        return field_name in cls.SINGLE_VALUED_FIELDS
    
    @classmethod
    def normalize_values(cls, field_name: str, values: List[str]) -> List[str]:
        """Normalize field values based on field type."""
        if not values:
            return []
        
        if cls.is_multi_valued(field_name):
            normalized = SimpleMusic.unique_preserve_order_case_insensitive(
                [str(v).strip() for v in values if str(v).strip()]
            )
        elif field_name == 'comment':
            # Comment can have multiple values but we don't deduplicate
            normalized = [str(v).strip() for v in values if str(v).strip()]
        else:
            # Single-valued fields - take first non-empty value
            normalized = [str(v).strip() for v in values if str(v).strip()]
            if normalized:
                normalized = [normalized[0]]
        
        return normalized

def find_replace(field_name: str, find: str, replace: str, regex: bool = False, delimiter: str = ';') -> Callable[[List[str]], List[str]]:
    """
    Create a find/replace operation that substitutes text patterns in field values.
    
    Args:
        field_name: Name of the field being operated on
        find: Pattern to search for (literal string or regex)
        replace: Replacement text
        regex: If True, treat 'find' as a regular expression
        delimiter: Delimiter for splitting multi-valued fields after replacement
    
    Returns:
        Operation function that transforms List[str] -> List[str]
    
    Examples:
        Replace literal text:
        >>> op = find_replace('title', 'Demo', 'Final')
        >>> op(['Demo Track']) 
        ['Final Track']
        
        Regex replacement:
        >>> op = find_replace('title', r'\\d+', 'X', regex=True)
        >>> op(['Track 01'])
        ['Track X']
    """
    pattern = re.compile(safe_regex_pattern(find, regex))
    
    def op(values: List[str]) -> List[str]:
        out = []
        for v in values:
            new_val = pattern.sub(replace, str(v))
            
            if FieldOperations.is_multi_valued(field_name) and delimiter in new_val:
                # Split only for true multi-valued fields
                out.extend(SimpleMusic.parse_list_string(new_val, delimiter=delimiter))
            else:
                out.append(new_val)
        
        return FieldOperations.normalize_values(field_name, out)
    
    return op

def overwrite(field_name: str, value_str: str, delimiter: str = ';') -> Callable[[List[str]], List[str]]:
    """
    Create an overwrite operation that completely replaces field values.
    
    Args:
        field_name: Name of the field being operated on
        value_str: New value(s) to set (delimited for multi-valued fields)
        delimiter: Delimiter for parsing multi-valued fields
    
    Returns:
        Operation function that ignores current values and sets new ones
    
    Examples:
        Set single value:
        >>> op = overwrite('title', 'New Title')
        >>> op(['Old Title'])
        ['New Title']
        
        Set multiple artists:
        >>> op = overwrite('artist', 'Artist A;Artist B', delimiter=';')
        >>> op(['Old Artist'])
        ['Artist A', 'Artist B']
    """
    if FieldOperations.is_multi_valued(field_name) or field_name == 'comment':
        vals = SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter)
    else:
        vals = [str(value_str)] if value_str not in (None, "") else []
    
    def op(values: List[str]) -> List[str]:
        return FieldOperations.normalize_values(field_name, vals)
    
    return op

def append(field_name: str, value_str: str, delimiter: str = ';') -> Callable[[List[str]], List[str]]:
    """
    Create an append operation that adds text to existing field values.
    
    Behavior varies by field type:
    - Single-valued: Appends to the first value
    - Multi-valued: Adds as new value if not present
    - Comment: Appends to each value
    
    Args:
        field_name: Name of the field being operated on
        value_str: Text to append (or values to add for multi-valued fields)
        delimiter: Delimiter for parsing multi-valued additions
    
    Returns:
        Operation function that appends/adds values
    
    Examples:
        Append to title:
        >>> op = append('title', ' (Remastered)')
        >>> op(['Original'])
        ['Original (Remastered)']
        
        Add genre:
        >>> op = append('genre', 'Electronic')
        >>> op(['Rock'])
        ['Rock', 'Electronic']
    """
    def op(values: List[str]) -> List[str]:
        if not values:
            return FieldOperations.normalize_values(field_name, [value_str])
        
        if FieldOperations.is_single_valued(field_name):
            # Single-valued: append to first value
            new_values = [values[0] + str(value_str)]
        elif field_name == 'comment':
            # Comment: append to each value
            new_values = [v + str(value_str) for v in values]
        else:
            # Multi-valued: add as new value if not present
            new_values = list(values)
            add_vals = SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter)
            for val in add_vals:
                if val.strip().lower() not in [v.strip().lower() for v in new_values]:
                    new_values.append(val)
        
        return FieldOperations.normalize_values(field_name, new_values)
    
    return op

def prefix(field_name: str, value_str: str) -> Callable[[List[str]], List[str]]:
    """
    Create a prefix operation that prepends text to field values.
    
    Behavior varies by field type:
    - Single-valued: Prepends to the first value
    - Multi-valued: Prepends to all values
    - Comment: Prepends to each value
    
    Args:
        field_name: Name of the field being operated on
        value_str: Text to prepend
    
    Returns:
        Operation function that prepends text to values
    
    Examples:
        Prefix title:
        >>> op = prefix('title', 'The ')
        >>> op(['Song'])
        ['The Song']
        
        Prefix all artists:
        >>> op = prefix('artist', 'DJ ')
        >>> op(['John', 'Jane'])
        ['DJ John', 'DJ Jane']
    """
    def op(values: List[str]) -> List[str]:
        if not values:
            return FieldOperations.normalize_values(field_name, [value_str])
        
        if FieldOperations.is_single_valued(field_name):
            # Single-valued: prefix to first value
            new_values = [str(value_str) + values[0]]
        elif field_name == 'comment':
            # Comment: prefix to each value
            new_values = [str(value_str) + v for v in values]
        else:
            # Multi-valued: prefix to all values
            new_values = [str(value_str) + v for v in values]
        
        return FieldOperations.normalize_values(field_name, new_values)
    
    return op

def enlist(field_name: str, value_str: str, delimiter: str = ';') -> Callable[[List[str]], List[str]]:
    """
    Create an enlist operation for multi-valued fields (warns/converts for single-valued).
    
    Similar to append but specifically designed for multi-valued fields like artist, genre.
    For single-valued fields, behaves like append.
    
    Args:
        field_name: Name of the field being operated on
        value_str: Value(s) to enlist (delimited for multiple)
        delimiter: Delimiter for parsing multiple values
    
    Returns:
        Operation function that adds unique values to multi-valued fields
    
    Examples:
        Enlist artists (no duplicates):
        >>> op = enlist('artist', 'New Artist')
        >>> op(['Existing Artist', 'Another'])
        ['Existing Artist', 'Another', 'New Artist']
        
        Enlist multiple genres:
        >>> op = enlist('genre', 'Rock;Metal', delimiter=';')
        >>> op(['Electronic'])
        ['Electronic', 'Rock', 'Metal']
    """
    def op(values: List[str]) -> List[str]:
        if not FieldOperations.is_multi_valued(field_name):
            return append(field_name, value_str, delimiter=delimiter)(values)
        
        new_values = list(values)
        add_vals = SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter)
        
        for val in add_vals:
            val_stripped = val.strip()
            if val_stripped and val_stripped.lower() not in [v.strip().lower() for v in new_values]:
                new_values.append(val_stripped)
        
        return FieldOperations.normalize_values(field_name, new_values)
    
    return op

def clear(field_name: str) -> Callable[[List[str]], List[str]]:
    """
    Create a clear operation that sets field to empty string.
    
    Different from delete - clear leaves the field present but empty,
    while delete removes the field entirely.
    
    Returns:
        Operation function that returns [''] (empty but present)
    
    Example:
        >>> op = clear('comment')
        >>> op(['Old comment'])
        ['']
    """
    def op(values: List[str]) -> List[str]:
        return [""]
    return op

def delete(field_name: str) -> Callable[[List[str]], List[str]]:
    """
    Create a delete operation that removes the field entirely.
    
    Different from clear - delete removes the field from metadata,
    while clear leaves it present but empty.
    
    Returns:
        Operation function that returns [] (field removed)
    
    Example:
        >>> op = delete('comment')
        >>> op(['Any value'])
        []
    """
    def op(values: List[str]) -> List[str]:
        return []
    return op

def delist(field_name: str, value_str: str, delimiter: str = ';') -> Callable[[List[str]], List[str]]:
    """
    Create a delist operation that removes specific values from multi-valued fields.
    
    Args:
        field_name: Name of the field being operated on
        value_str: Value(s) to remove (delimited for multiple)
        delimiter: Delimiter for parsing multiple values
    
    Returns:
        Operation function that removes specified values
    
    Examples:
        Remove an artist:
        >>> op = delist('artist', 'Artist A')
        >>> op(['Artist A', 'Artist B'])
        ['Artist B']
    """
    def op(values: List[str]) -> List[str]:
        if not values:
            return []
            
        remove_vals = set(v.strip().lower() for v in SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter))
        
        new_values = []
        for v in values:
            if str(v).strip().lower() not in remove_vals:
                new_values.append(v)
                
        return FieldOperations.normalize_values(field_name, new_values)
    
    return op

# ---------- Compute & Verify ----------
def compute_new_fields(orig_fields: FieldValuesType, 
                      field_ops: FieldOperationsType, 
                      targeted_fields: List[str]) -> Tuple[FieldValuesType, Dict[str, bool]]:
    """
    Compute new field values with change tracking.
    
    Applies operations to fields and tracks which fields actually changed.
    
    Args:
        orig_fields: Original field values (field_name -> List[str])
        field_ops: Operations to apply (field_name -> operation function)
        targeted_fields: Fields to process
    
    Returns:
        Tuple of (new_fields, changed_dict) where:
        - new_fields: Updated field values
        - changed_dict: Maps field_name -> bool indicating if it changed
    
    Example:
        >>> orig = {'title': ['Old'], 'artist': ['John']}
        >>> ops = {'title': overwrite('title', 'New')}
        >>> new, changed = compute_new_fields(orig, ops, ['title', 'artist'])
        >>> changed
        {'title': True, 'artist': False}
    """
    new = orig_fields.copy()
    changed = {}
    
    for field in targeted_fields:
        op = field_ops.get(field)
        if not op:
            changed[field] = False
            continue
            
        before = FieldOperations.normalize_values(field, orig_fields.get(field, []))
        after = FieldOperations.normalize_values(field, op(before))
        
        new[field] = after
        changed[field] = (before != after)
    
    return new, changed

# ---------- Artist/AlbumArtist Matching ----------
def artist_plain_match(pattern: str, artist: str) -> bool:
    return pattern.strip().lower() in artist.lower()

def artist_regex_match(pattern: str, artist: str) -> bool:
    return bool(re.search(pattern, artist, flags=re.IGNORECASE))

def match_artist_single(pattern: str, artists: List[str], regex_flag: bool) -> bool:
    for artist in artists:
        if regex_flag:
            if artist_regex_match(pattern, artist):
                return True
        else:
            if artist_plain_match(pattern, artist):
                return True
    return False

def match_artists_bipartite(patterns: List[str], artists: List[str], regex_flag: bool) -> bool:
    """Match patterns to artists using bipartite matching."""
    pat_list = [p.strip() for p in patterns if p.strip()]
    artist_list = list(artists)
    
    n = len(pat_list)
    m = len(artist_list)
    
    if n == 0:
        return True
    if n > m:
        return False
    
    # Build adjacency list
    adj = [[] for _ in range(n)]
    for i, pattern in enumerate(pat_list):
        for j, artist in enumerate(artist_list):
            if regex_flag:
                matched = artist_regex_match(pattern, artist)
            else:
                matched = artist_plain_match(pattern, artist)
            if matched:
                adj[i].append(j)
    
    # Bipartite matching
    matchR = [-1] * m
    
    def dfs(u: int, seen: List[bool]) -> bool:
        for v in adj[u]:
            if not seen[v]:
                seen[v] = True
                if matchR[v] == -1 or dfs(matchR[v], seen):
                    matchR[v] = u
                    return True
        return False
    
    for u in range(n):
        seen = [False] * m
        if not dfs(u, seen):
            return False
    return True

def apply_filter(field: str, pattern: str, regex_flag: bool, orig_fields: FieldValuesType) -> bool:
    """
    Apply a single filter to fields to determine if file matches.
    
    Supports special filter types:
    - 'artist': Match any single artist
    - 'artists': Match all patterns to artists (bipartite matching)
    - 'albumartist'/'albumartists': Same as artist but for albumartist field
    - Other fields: Simple substring/regex match
    
    Args:
        field: Field name to filter on (or special filter type)
        pattern: Pattern to match (semicolon-delimited for 'artists'/'albumartists')
        regex_flag: If True, use regex matching
        orig_fields: Field values to filter against
    
    Returns:
        True if file passes the filter, False otherwise
    
    Examples:
        Simple substring match:
        >>> apply_filter('title', 'love', False, {'title': ['Love Song']})
        True
        
        Multiple artist matching:
        >>> apply_filter('artists', 'John;Paul', False, 
        ...              {'artist': ['John Doe', 'Paul Smith', 'George']})
        True
    """
    if field == 'artist':
        return match_artist_single(pattern, orig_fields.get('artist', []), regex_flag)
    elif field == 'artists':
        patterns = [p for p in (x.strip() for x in pattern.split(';')) if p != ""]
        return match_artists_bipartite(patterns, orig_fields.get('artist', []), regex_flag)
    elif field == 'albumartist':
        return match_artist_single(pattern, orig_fields.get('albumartist', []), regex_flag)
    elif field == 'albumartists':
        patterns = [p for p in (x.strip() for x in pattern.split(';')) if p != ""]
        return match_artists_bipartite(patterns, orig_fields.get('albumartist', []), regex_flag)
    else:
        vals = orig_fields.get(field, [])
        haystack = ';'.join(vals).lower()
        if regex_flag:
            return bool(re.search(pattern, haystack, flags=re.IGNORECASE))
        else:
            return pattern.lower() in haystack
