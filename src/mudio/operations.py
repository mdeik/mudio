"""
Field operations and transformation logic for mudio.
"""

import re
from typing import Dict, List, Tuple, Callable

from .core import SimpleMusic
from .utils import safe_regex_pattern

# ---------- Type Definitions ----------
# An operation takes a list of field values (e.g. ["Rock", "Pop"]) and returns a new list
FieldOperationsType = Callable[[List[str]], List[str]]
# Metadata is stored as field name -> list of values (e.g. {"artist": ["Beatles", "Stones"]})
FieldValuesType = Dict[str, List[str]]
# A filter is (field_name, search_pattern, is_regex)
FilterType = Tuple[str, str, bool]

# ---------- Field Operations ----------
class FieldOperations:
    """Unified field operations with consistent multi-value handling."""
    
    @classmethod
    def normalize_values(cls, field_name: str, values: List[str]) -> List[str]:
        """Normalize field values based on field type."""
        # Clean up: strip whitespace from each value and discard empty ones
        processed = []
        for v in values:
            s = str(v).strip()
            if s:
                processed.append(s)
        
        # Remove duplicates while preserving order (case-insensitive: "Rock" == "rock")
        processed = SimpleMusic.unique_preserve_order_case_insensitive(processed)
        return processed

def find_replace(field_name: str, find: str, replace: str, regex: bool = False, delimiter: str = ';', index: int = None) -> Callable[[List[str]], List[str]]:
    """
    Create a find/replace operation that substitutes text patterns in field values.
    Accepts optional index (0-based) to apply only to a specific item.
    """
    # Compile the search pattern once upfront for efficiency
    pattern = re.compile(safe_regex_pattern(find, regex))
    
    def op(values: List[str]) -> List[str]:
        """Apply find/replace to field values and return the updated list."""
        # If a specific index was given, only modify that one item
        if index is not None:
            if index < 0 or index >= len(values):
                raise IndexError(f"Index {index} out of bounds for field '{field_name}' with {len(values)} values")
            
            original_val = values[index]
            new_val = pattern.sub(replace, str(original_val))
            working_values = list(values)
            working_values[index] = new_val
                
            return FieldOperations.normalize_values(field_name, working_values)

        # No index given — apply find/replace to every item in the field
        out = []
        for v in values:
            new_val = pattern.sub(replace, str(v))
            
            # If the result contains a delimiter (e.g. ";"),
            # split it into separate items (e.g. "Rock;Pop" -> ["Rock", "Pop"])
            if delimiter in new_val:
                out.extend(SimpleMusic.parse_list_string(new_val, delimiter=delimiter))
            else:
                out.append(new_val)
        
        return FieldOperations.normalize_values(field_name, out)
    
    # Tag the operation with its target field so compute_new_fields knows which field to apply it to
    op.field_name = field_name
    return op

def write(field_name: str, value_str: str, delimiter: str = ';', index: int = None) -> Callable[[List[str]], List[str]]:
    """
    Create a write operation that creates or overwrites the field.
    If index is provided, overwrites only that specific item.
    If value contains delimiter, splits and inserts multiple items at that index.
    """
    # Pre-split the value for when we overwrite the entire field
    # e.g. "Rock;Pop" with delimiter ";" becomes ["Rock", "Pop"]
    full_overwrite_vals = SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter)

    # Pre-split the value for when we insert at a specific index
    if delimiter in str(value_str):
        insert_vals = SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter)
    else:
        insert_vals = [str(value_str)]

    def op(values: List[str]) -> List[str]:
        """Apply write operation and return the updated list."""
        # If a specific index was given, replace just that item (splicing in multiple if delimiter-split)
        if index is not None:
            if index < 0 or index >= len(values):
                raise IndexError(f"Index {index} out of bounds for field '{field_name}' with {len(values)} values")
            
            working_values = list(values)
            # Replace the item at index with the new value(s)
            # e.g. ["A", "B"], index=1, insert=["X", "Y"] -> ["A", "X", "Y"]
            working_values[index:index+1] = insert_vals
            
            return FieldOperations.normalize_values(field_name, working_values)
        
        # No index — overwrite the entire field
        return FieldOperations.normalize_values(field_name, full_overwrite_vals)
    
    op.field_name = field_name
    return op

def append(field_name: str, value_str: str, delimiter: str = ';', index: int = None) -> Callable[[List[str]], List[str]]:
    """
    Create an append operation that adds text to existing field values.
    If index is provided, appends only to that item.
    """
    def op(values: List[str]) -> List[str]:
        """Append text to field values and return the updated list."""
        # If the field is empty, create it with the appended value
        if not values:
             if index is not None:
                 raise IndexError(f"Index {index} out of bounds for empty field '{field_name}'")
             return FieldOperations.normalize_values(field_name, [value_str])
        
        if index is not None:
            if index < 0 or index >= len(values):
                raise IndexError(f"Index {index} out of bounds for field '{field_name}' with {len(values)} values")
            
            working_values = list(values)
            working_values[index] = working_values[index] + str(value_str)
            return FieldOperations.normalize_values(field_name, working_values)

        # Append text to all items (use enlist to add new items instead)
        new_values = [v + str(value_str) for v in values]
        return FieldOperations.normalize_values(field_name, new_values)
    
    op.field_name = field_name
    return op

def prefix(field_name: str, value_str: str, index: int = None) -> Callable[[List[str]], List[str]]:
    """
    Create a prefix operation that prepends text to field values.
    If index is provided, prepends only to that item.
    """
    def op(values: List[str]) -> List[str]:
        """Prepend text to field values and return the updated list."""
        if not values:
             if index is not None:
                 raise IndexError(f"Index {index} out of bounds for empty field '{field_name}'")
             return FieldOperations.normalize_values(field_name, [value_str])
        
        if index is not None:
            if index < 0 or index >= len(values):
                raise IndexError(f"Index {index} out of bounds for field '{field_name}' with {len(values)} values")
            
            working_values = list(values)
            working_values[index] = str(value_str) + working_values[index]
            return FieldOperations.normalize_values(field_name, working_values)
            
        new_values = [str(value_str) + v for v in values]
        return FieldOperations.normalize_values(field_name, new_values)
    
    op.field_name = field_name
    return op

def enlist(field_name: str, value_str: str, delimiter: str = ';') -> Callable[[List[str]], List[str]]:
    """
    Create an enlist operation that adds new items to a list field.
    Unlike append (which adds text to existing items), enlist adds entirely new items.
    """
    def op(values: List[str]) -> List[str]:
        """Add new items, deduplicating case-insensitively."""
        new_values = list(values)
        add_vals = SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter)
        
        # Only add items that don't already exist (case-insensitive comparison)
        for val in add_vals:
            val_stripped = val.strip()
            if val_stripped and val_stripped.lower() not in [v.strip().lower() for v in new_values]:
                new_values.append(val_stripped)
        
        return FieldOperations.normalize_values(field_name, new_values)
    
    op.field_name = field_name
    return op

def clear(field_name: str) -> Callable[[List[str]], List[str]]:
    """
    Create a clear operation that sets field to empty string.
    The field still exists in metadata but has no meaningful value.
    """
    def op(values: List[str]) -> List[str]:
        """Return an empty-string list to clear the field."""
        return [""]
    
    op.field_name = field_name
    return op

def delete(field_name: str) -> Callable[[List[str]], List[str]]:
    """
    Create a delete operation that removes the field entirely.
    Unlike clear (which leaves an empty field), delete removes the tag completely.
    """
    def op(values: List[str]) -> List[str]:
        """Return an empty list to delete the field entirely."""
        return []
    
    op.field_name = field_name
    return op

def delist(field_name: str, value_str: str, delimiter: str = ';') -> Callable[[List[str]], List[str]]:
    """
    Create a delist operation that removes specific values from multi-valued fields.
    """
    def op(values: List[str]) -> List[str]:
        """Remove matching items from the field's value list."""
        if not values:
            return []
        
        # Build a set of values to remove (case-insensitive)
        remove_vals = set(v.strip().lower() for v in SimpleMusic.parse_list_string(str(value_str), delimiter=delimiter))
        
        # Keep only items that aren't in the removal set
        new_values = []
        for v in values:
            if str(v).strip().lower() not in remove_vals:
                new_values.append(v)
                
        return FieldOperations.normalize_values(field_name, new_values)
    
    op.field_name = field_name
    return op

# ---------- Compute & Verify ----------
def compute_new_fields(orig_fields: FieldValuesType, 
                      ops: List[FieldOperationsType]) -> Tuple[FieldValuesType, Dict[str, bool]]:
    """
    Compute new field values by applying a list of operations sequentially.
    
    Args:
        orig_fields: Original field values (field_name -> List[str])
        ops: List of operation functions to apply. Each op must have a .field_name attribute.
    
    Returns:
        Tuple of (new_fields, changed_dict) where:
        - new_fields: Updated field values
        - changed_dict: Maps field_name -> bool indicating if it changed
    """
    # Start with a copy of the original metadata so we can modify it
    new_fields = orig_fields.copy()
    changed = {}  # Tracks which fields actually changed (field_name -> True/False)
    
    # Map lowercase field names to their original casing for case-insensitive lookup
    # e.g. {"artist": "artist", "albumartist": "albumartist"}
    orig_keys_lower = {k.lower(): k for k in orig_fields.keys()}
    
    # Apply each operation in order — later ops see changes from earlier ones
    for op in ops:
        target_field = getattr(op, 'field_name', None)
        if not target_field:
            continue
            
        # Resolve field name: exact match > case-insensitive match > new field
        if target_field in new_fields:
            actual_field = target_field
        elif target_field.lower() in orig_keys_lower:
            actual_field = orig_keys_lower[target_field.lower()]
        else:
            actual_field = target_field
            orig_keys_lower[actual_field.lower()] = actual_field
        
        # Run the operation: get current values, transform them, store the result
        before = FieldOperations.normalize_values(actual_field, new_fields.get(actual_field, []))
        after = FieldOperations.normalize_values(actual_field, op(before))

        new_fields[actual_field] = after
        
        # Track changes cumulatively across multiple ops on the same field
        if actual_field not in changed:
             changed[actual_field] = (before != after)
        else:
             changed[actual_field] = changed[actual_field] or (before != after)
             
    return new_fields, changed

# ---------- Artist/AlbumArtist Matching ----------
def artist_plain_match(pattern: str, artist: str) -> bool:
    """Return True if pattern is a case-insensitive substring of artist."""
    return pattern.strip().lower() in artist.lower()

def artist_regex_match(pattern: str, artist: str) -> bool:
    """Return True if pattern matches artist as a case-insensitive regex."""
    return bool(re.search(pattern, artist, flags=re.IGNORECASE))

def match_artist_single(pattern: str, artists: List[str], regex_flag: bool) -> bool:
    """Return True if pattern matches any single artist in the list."""
    for artist in artists:
        if regex_flag:
            if artist_regex_match(pattern, artist):
                return True
        else:
            if artist_plain_match(pattern, artist):
                return True
    return False

def match_artists_bipartite(patterns: List[str], artists: List[str], regex_flag: bool) -> bool:
    """
    Check that every search pattern can be matched to a distinct artist.
    Uses bipartite matching so that "John;Paul" matches ["John Doe", "Paul Smith"]
    but "John;John" would need two different Johns to match.
    """
    pat_list = [p.strip() for p in patterns if p.strip()]
    artist_list = list(artists)
    
    n = len(pat_list)   # Number of patterns to match
    m = len(artist_list) # Number of available artists
    
    if n == 0:
        return True     # No patterns to match = always passes
    if n > m:
        return False    # More patterns than artists = can't possibly match all
    
    # For each pattern, find which artists it could match
    adj = [[] for _ in range(n)]
    for i, pattern in enumerate(pat_list):
        for j, artist in enumerate(artist_list):
            if regex_flag:
                matched = artist_regex_match(pattern, artist)
            else:
                matched = artist_plain_match(pattern, artist)
            if matched:
                adj[i].append(j)
    
    # Use the Hungarian algorithm (augmenting paths) to find a matching
    # where each pattern pairs with a unique artist
    matchR = [-1] * m  # matchR[j] = which pattern is matched to artist j (-1 = unmatched)
    
    def dfs(u: int, seen: List[bool]) -> bool:
        """Try to find an augmenting path from pattern u to an unmatched artist."""
        for v in adj[u]:
            if not seen[v]:
                seen[v] = True
                # If artist v is free, or the pattern currently matched to v can find another artist
                if matchR[v] == -1 or dfs(matchR[v], seen):
                    matchR[v] = u
                    return True
        return False
    
    # Try to match every pattern to a unique artist
    for u in range(n):
        seen = [False] * m
        if not dfs(u, seen):
            return False  # This pattern couldn't find a match
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
    # 'artist' filter: does the pattern match ANY single artist?
    if field == 'artist':
        return match_artist_single(pattern, orig_fields.get('artist', []), regex_flag)
    # 'artists' filter: do ALL semicolon-separated patterns match distinct artists?
    elif field == 'artists':
        patterns = [p for p in (x.strip() for x in pattern.split(';')) if p != ""]
        return match_artists_bipartite(patterns, orig_fields.get('artist', []), regex_flag)
    elif field == 'albumartist':
        return match_artist_single(pattern, orig_fields.get('albumartist', []), regex_flag)
    elif field == 'albumartists':
        patterns = [p for p in (x.strip() for x in pattern.split(';')) if p != ""]
        return match_artists_bipartite(patterns, orig_fields.get('albumartist', []), regex_flag)
    else:
        # Generic filter: join all values and search the combined string
        vals = orig_fields.get(field, [])
        haystack = ';'.join(vals).lower()
        if regex_flag:
            return bool(re.search(pattern, haystack, flags=re.IGNORECASE))
        else:
            return pattern.lower() in haystack
