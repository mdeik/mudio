"""
SimpleMusic - Unified API for reading/writing music file metadata.
Handles MP3(ID3), M4A(MP4), FLAC/Vorbis, WAV (ID3), etc.
Now with automatic tag support for formats that support it.
"""

import mutagen
import mutagen.id3 as id3
import mutagen.mp4 as mp4
import mutagen.flac as flac
import mutagen.wave as wave
import mutagen.asf as asf
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Generator
import unittest
from unittest.mock import Mock, patch
import sys
import tempfile
from contextlib import contextmanager
import shutil
import logging
from .utils import Config

logger = logging.getLogger(__name__)

SUPPORTED_EXT = {'.mp3', '.flac', '.m4a', '.mp4', '.ogg', '.opus', '.wav'}

# Canonical mapping for case-insensitive normalization
# Order matters: this defines the order of CANONICAL_FIELDS
CANON = {
    "title": {"title", "tit2"},
    "artist": {"artist", "artists", "tpe1"},
    "album": {"album", "talb"},
    "albumartist": {"albumartist", "albumartists", "album_artist", "album artist", "album_artists", "album artists", "tpe2", "aart"},
    "genre": {"genre", "tcon"},
    "comment": {"comment", "comm"},
    "composer": {"composer", "tcom"},
    "performer": {"performer", "performers", "perf", "tpe3"},
    "date": {"date", "year", "originaldate", "tdrc", "tory", "tdat"},
    "track": {"track", "tracknumber", "track number", "track_number", "trck"},
    "totaltracks": {"totaltracks", "tracktotal", "track_total", "track total"},
    "disc": {"disc", "discnumber", "disc number", "disc_number", "tpos"},
    "totaldiscs": {"totaldiscs", "disctotal", "disc_total", "disc total"},
}

CANONICAL_FIELDS = list(CANON.keys())

# Pre-compute lookup table for O(1) access
_CANON_LOOKUP = {}
for canon, aliases in CANON.items():
    _CANON_LOOKUP[canon] = canon
    for alias in aliases:
        # Store alias as is
        _CANON_LOOKUP[alias] = canon
        # Store alias with hyphens/spaces replaced by underscores
        normalized_alias = alias.replace('-', '_').replace(' ', '_')
        _CANON_LOOKUP[normalized_alias] = canon

def canon_key(k: str) -> str:
    """
    Normalize key to canonical form if known, otherwise return lowercase string.
    Handles hyphens, underscores, and spaces interchangeably (e.g., 
    'album-artist', 'album_artist', and 'album artist' all map to 'albumartist').
    
    Args:
        k: Key to normalize
        
    Returns:
        Canonical key or lowered key
    """
    k_norm = k.strip().lower()
    
    # Try direct lookup first (this will handle original aliases and canonical keys)
    if k_norm in _CANON_LOOKUP:
        return _CANON_LOOKUP[k_norm]
    
    # If not found, try normalizing hyphens and spaces to underscores
    # This step is now redundant because _CANON_LOOKUP already stores these variations.
    # However, keeping it for robustness if _CANON_LOOKUP generation changes or for keys not in CANON.
    k_with_underscores = k_norm.replace('-', '_').replace(' ', '_')
    if k_with_underscores in _CANON_LOOKUP:
        return _CANON_LOOKUP[k_with_underscores]
    
    # Return original string (stripped) if no match to preserve case for custom keys
    return k.strip()

class MudioError(Exception):
    """Base exception for Mudio errors."""
    pass

class ValidationError(MudioError):
    """Raised when validation fails."""
    pass

class FormatError(MudioError):
    """Raised when file format is unsupported or corrupted."""
    pass

class PermissionError(MudioError):
    """Raised when permission issues occur."""
    pass

class VerificationError(MudioError):
    """Raised when verification fails after writing."""
    pass

class SimpleMusic:
    """
    Unified API for reading and writing music file metadata across formats.
    Automatically adds tag support when writing to compatible formats.
    """
    CANONICAL_FIELDS = CANONICAL_FIELDS
    SUPPORTED_EXT = SUPPORTED_EXT
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self.mfile = None
        self.load_file()
    
    def load_file(self) -> None:
        """Load the music file with mutagen and validate format."""
        try:
            # Load with mutagen - let it handle file I/O errors

            self.mfile = mutagen.File(self.path, easy=False)
            if self.mfile is None:
                raise FormatError("Unsupported file format or corrupted file")
                
        except mutagen.MutagenError as e:
            # When mutagen fails to parse, treat as unsupported format
            raise FormatError(f"Unsupported file format or corrupted file: {e}")
        except Exception as e:
            raise FormatError(f"Failed to load file {self.path}: {e}")
    
    def close(self) -> None:
        """Close the underlying file handle."""
        if hasattr(self.mfile, 'close'):
            try:
                self.mfile.close()
            except Exception as e:
                # Log but don't raise - close errors are usually non-critical
                logger.warning(f"Error closing music file {self.path}: {e}")
    
    def __enter__(self) -> 'SimpleMusic':
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
    
    @staticmethod
    def parse_list_string(s: Optional[str], delimiter: str = ';') -> List[str]:
        """
        Parse delimiter-separated string into list, stripping whitespace and empties.
        
        Args:
            s: String to parse (None returns empty list)
            delimiter: Separator character (default: ';')
        
        Returns:
            List of non-empty strings
        
        Examples:
            >>> SimpleMusic.parse_list_string('Rock; Pop ; Jazz')
            ['Rock', 'Pop', 'Jazz']
            >>> SimpleMusic.parse_list_string('')
            []
            >>> SimpleMusic.parse_list_string(None)
            []
        """
        if s is None: 
            return []
        parts = [p.strip() for p in str(s).split(delimiter)]
        return [p for p in parts if p != ""]
    
    @staticmethod
    def unique_preserve_order_case_insensitive(seq: List[str]) -> List[str]:
        """
        Remove duplicates while preserving order (case-insensitive comparison).
        
        Comparison is case-insensitive, but preserves original case of first occurrence.
        
        Args:
            seq: List of strings to deduplicate
        
        Returns:
            List with duplicates removed (order and case preserved)
        
        Examples:
            >>> SimpleMusic.unique_preserve_order_case_insensitive(['Rock', 'Pop', 'ROCK', 'Jazz'])
            ['Rock', 'Pop', 'Jazz']
            >>> SimpleMusic.unique_preserve_order_case_insensitive(['a', 'A', 'b', 'B', 'a'])
            ['a', 'b']
        """
        seen = set()
        out = []
        for x in seq:
            key = str(x).strip().lower()
            if key not in seen:
                seen.add(key)
                out.append(str(x).strip())
        return out
    
    @staticmethod
    def safe_int(x: Any) -> Optional[int]:
        """
        Safely convert value to integer, returning None on failure.
        
        Args:
            x: Value to convert
        
        Returns:
            Integer if convertible, None otherwise
        
        Examples:
            >>> SimpleMusic.safe_int('42')
            42
            >>> SimpleMusic.safe_int('not a number') is None
            True
            >>> SimpleMusic.safe_int(None) is None
            True
        """
        try:
            return int(str(x))
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _deduplicate_frames(frames_values: List[List[str]]) -> List[str]:
        """
        Deduplicate frame values.
        If two frames have EXACTLY the same list of values, keep only one.
        Otherwise keep both, maintaining order.
        
        Args:
            frames_values: List of lists, where each inner list is the content of a frame.
            
        Returns:
            Flattened list of values with frame-level duplicates removed.
        """
        seen = []
        out = []
        for val_list in frames_values:
            # Check if we've seen this exact sequence of values before (case-sensitive)
            key = tuple(str(s) for s in val_list)
            
            if key not in seen:
                seen.append(key)
                out.extend(val_list)
        return out
    
    
    def read_fields(self, schema: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Read all metadata fields from the file.
        
        Args:
            schema: 'canonical' - return only standardized fields.
                  'raw' - return all fields with native keys.
                  'extended' - return canonical fields plus any other fields found.
                  None (default) - use Config.DEFAULT_MODE.
        """
        if schema is None:
            # New config class might not be imported yet if circular import risk,
            # but standard import should work.
            from .utils import Config
            schema = Config.DEFAULT_SCHEMA

        if self.mfile is None or self.mfile.tags is None:
            return {k: [] for k in CANONICAL_FIELDS} if schema == 'canonical' else {}

        # MP4 / M4A
        if isinstance(self.mfile, mp4.MP4):
            fields = self._read_mp4_fields(self.mfile.tags, schema=schema)
        
        # ID3 (MP3/WAV with ID3v2 tags)
        elif isinstance(self.mfile.tags, id3.ID3):
            fields = self._read_id3_fields(self.mfile.tags, schema=schema)
        
        # FLAC files
        elif isinstance(self.mfile, flac.FLAC):
            fields = self._read_flac_fields(self.mfile.tags, schema=schema)
        
        # ASF/WMA
        elif isinstance(self.mfile, asf.ASF):
            fields = self._read_asf_fields(self.mfile.tags, schema=schema)
        
        # Other formats (Ogg, Opus, WMA, WV, etc.)
        else:
            fields = self._read_easy_tags(self.mfile.tags, schema=schema)
        
        # Apply sanitization if schema is canonical or extended
        if schema in ('canonical', 'extended'):
             sanitized_fields = {}
             for k, v in fields.items():
                 # Canonical fields are already safe (and should be preserved as-is to match CANONICAL_FIELDS)
                 if k in CANONICAL_FIELDS:
                     clean_k = k
                 else:
                     clean_k = self._sanitize_read_key(k)
                 
                 if clean_k not in sanitized_fields:
                     sanitized_fields[clean_k] = []
                 sanitized_fields[clean_k].extend(v)
             
             # Deduplicate values again after merge
             for k in sanitized_fields:
                 sanitized_fields[k] = self._deduplicate_frames([sanitized_fields[k]])
                 
             return sanitized_fields

        return fields
    
    def _read_mp4_fields(self, tags: Any, schema: str = 'canonical') -> Dict[str, List[str]]:
        """Read fields from MP4/M4A files."""
        if schema == 'raw':
            # Just dump what we have, but decode bytes if possible
            out = {}
            for k, vals in tags.items():
                val_list = vals if isinstance(vals, list) else [vals]
                out_vals = []
                for v in val_list:
                    if isinstance(v, bytes):
                        try:
                            out_vals.append(v.decode('utf-8', errors='replace'))
                        except Exception:
                            out_vals.append(str(v))
                    else:
                        out_vals.append(str(v))
                out[str(k)] = out_vals
            return out

        collected = {k: [] for k in CANONICAL_FIELDS}
        
        def add_frame(key: str, vals: List[str]) -> None:
             if vals:
                 if key not in collected:
                     collected[key] = []
                 collected[key].append(vals)
        
        def get_vals(key: str) -> List[str]:
            # Try to fetch by exact key
            vals = tags.get(key)
            if not vals: 
                return []
            outvals = []
            for v in vals:
                if isinstance(v, bytes):
                    try:
                        outvals.append(v.decode('utf-8', errors='replace'))
                    except Exception as e:
                        logger.debug(f"Failed to decode MP4 metadata value: {e}")
                        outvals.append(str(v))
                else:
                    outvals.append(str(v))
            return outvals
        
        add_frame('title', get_vals('\xa9nam'))
        add_frame('artist', get_vals('\xa9ART'))
        add_frame('album', get_vals('\xa9alb'))
        add_frame('albumartist', get_vals('aART'))
        add_frame('genre', get_vals('\xa9gen'))
        add_frame('comment', get_vals('\xa9cmt'))
        add_frame('date', get_vals('\xa9day'))
        add_frame('composer', get_vals('\xa9wrt'))
        
        # Performer handling for MP4
        # 'perf' atom
        if 'perf' in tags:
            add_frame('performer', get_vals('perf'))
            
        # Try different performer tag variations
        for perf_key in ['\xa9prf', 'Â©prf', '----:com.apple.iTunes:PERFORMER']:
             if perf_key in tags:
                add_frame('performer', get_vals(perf_key))
        
        # Track/disk tuples
        trkn = tags.get('trkn')
        if trkn and isinstance(trkn, list) and len(trkn) > 0:
            try:
                tnum, ttot = trkn[0]
                if tnum is not None: 
                    add_frame('track', [str(tnum)])
                if ttot is not None and ttot != 0: 
                    add_frame('totaltracks', [str(ttot)])
            except Exception as e:
                logger.debug(f"Failed to parse MP4 track number: {e}")
                pass
        
        # Fallback: check for custom track/totaltracks fields if standard atom missed
        if not collected['track']:
            for k in [f'----:{Config.DEFAULT_NAMESPACE}:track', f'----:{Config.DEFAULT_NAMESPACE}:TRACK']:
                val = get_vals(k)
                if val:
                    add_frame('track', val)
                    break
        
        if not collected['totaltracks']:
            for k in [f'----:{Config.DEFAULT_NAMESPACE}:totaltracks', f'----:{Config.DEFAULT_NAMESPACE}:TOTALTRACKS']:
                val = get_vals(k)
                if val:
                    add_frame('totaltracks', val)
                    break

        disk = tags.get('disk')
        if disk and isinstance(disk, list) and len(disk) > 0:
            try:
                dnum, dtot = disk[0]
                if dnum is not None: 
                    add_frame('disc', [str(dnum)])
                if dtot is not None and dtot != 0:
                    add_frame('totaldiscs', [str(dtot)])
            except Exception as e:
                logger.debug(f"Failed to parse MP4 disc number: {e}")
                pass

        # Fallback: check for custom disc/totaldiscs fields if standard atom missed
        if not collected['disc']:
            for k in [f'----:{Config.DEFAULT_NAMESPACE}:disc', f'----:{Config.DEFAULT_NAMESPACE}:DISC']:
                val = get_vals(k)
                if val:
                    add_frame('disc', val)
                    break
        
        if not collected['totaldiscs']:
             for k in [f'----:{Config.DEFAULT_NAMESPACE}:totaldiscs', f'----:{Config.DEFAULT_NAMESPACE}:TOTALDISCS']:
                val = get_vals(k)
                if val:
                    add_frame('totaldiscs', val)
                    break
                
        if schema == 'extended':
            # Add other atoms
            # Mappped atom keys
            mapped = {'\xa9nam', '\xa9ART', '\xa9alb', 'aART', '\xa9gen', 
                      '\xa9cmt', '\xa9day', '\xa9wrt', 'perf', '\xa9prf', 
                      'trkn', 'disk', 'covr', 'cpil', 'pgap', 'tmpo'}
            
            for k, vals in tags.items():
                if k not in mapped and not k.startswith(f'----:{Config.DEFAULT_NAMESPACE}:PERFORMER'):
                    # Handle parsing of unknown atoms similar to get_vals
                    outvals = []
                    if not vals: continue
                    for v in vals:
                        if isinstance(v, bytes):
                            try:
                                outvals.append(v.decode('utf-8', errors='replace'))
                            except Exception as e:
                                logger.debug(f"Failed to decode MP4 extended field {k}: {e}")
                                outvals.append(str(v))
                        else:
                            outvals.append(str(v))
                    
                    # Clean key
                    clean_key = k
                    if k.startswith(f'----:{Config.DEFAULT_NAMESPACE}:'):
                        clean_key = k[len(f'----:{Config.DEFAULT_NAMESPACE}:'):]
                    elif k.startswith('----:'):
                        clean_key = k[len('----:'):]
                        
                    # Normalize key
                    c_key = canon_key(clean_key)
                    if outvals:
                         add_frame(c_key, outvals)
        
        # Finalize: deduplicate frames
        out = {k: [] for k in CANONICAL_FIELDS}
        for k, frames in collected.items():
            out[k] = self._deduplicate_frames(frames)
            
        return out
    
    def _read_id3_fields(self, tags: id3.ID3, schema: str = 'canonical') -> Dict[str, List[str]]:
        """Read fields from ID3 files (MP3/WAV)."""
        if schema == 'raw':
            # Raw mode: dump all frames
            out = {}
            for key, frame in tags.items():
                vals = []
                if hasattr(frame, 'text'):
                    vals = [str(x) for x in frame.text]
                elif hasattr(frame, 'url'):
                    vals = [str(frame.url)]
                elif hasattr(frame, 'owner') and hasattr(frame, 'data'): 
                    vals = [str(frame)]
                else:
                    vals = [str(frame)]
                out[key] = vals
            return out

        collected = {k: [] for k in CANONICAL_FIELDS}
        
        def add_frame(key: str, vals: List[str]) -> None:
             if vals:
                 if key not in collected:
                     collected[key] = []
                 collected[key].append(vals)

        def get_frame(frame_name: str) -> List[str]:
            frame = tags.get(frame_name)
            if not frame:
                return []
            return [str(x) for x in getattr(frame, 'text', [])]
        
        add_frame('title', get_frame('TIT2'))
        add_frame('artist', get_frame('TPE1'))
        add_frame('album', get_frame('TALB'))
        add_frame('albumartist', get_frame('TPE2'))
        add_frame('genre', get_frame('TCON'))
        
        # Comments
        comms = tags.getall('COMM')
        if comms:
            for c in comms:
                if hasattr(c, 'text'):
                    add_frame('comment', [str(x) for x in c.text])
        
        add_frame('composer', get_frame('TCOM'))
        
        # Performer: include TPE3 and TXXX:PERFORMER
        tpe3 = get_frame('TPE3')
        if tpe3:
            add_frame('performer', tpe3)
            
        txxx_frames = tags.getall('TXXX')
        for tx in txxx_frames:
            try:
                desc = (getattr(tx, 'desc', '') or '').strip()
                if desc.lower() in ('performer', 'performers', 'perf'):
                    if hasattr(tx, 'text'):
                        add_frame('performer', [str(x) for x in getattr(tx, 'text', [])])
                
                # Extended schema: add TXXX frames that aren't performer
                if schema == 'extended' and desc.lower() not in ('performer', 'performers', 'perf'):
                     c_key = canon_key(desc)
                     if hasattr(tx, 'text'):
                        vals = [str(x) for x in getattr(tx, 'text', [])]
                        add_frame(c_key, vals)
            except Exception as e:
                logger.debug(f"Failed to parse ID3 TXXX frame: {e}")
                continue
        
        out_date = get_frame('TDRC') or get_frame('TORY') or get_frame('TDAT')
        if out_date:
            add_frame('date', out_date)
        
        # Track/position parsing
        tr = get_frame('TRCK')
        if tr:
            parts = str(tr[0]).split('/')
            if parts[0].strip(): 
                add_frame('track', [parts[0].strip()])
            if len(parts) > 1 and parts[1].strip(): 
                add_frame('totaltracks', [parts[1].strip()])
        
        tp = get_frame('TPOS')
        if tp:
            parts = str(tp[0]).split('/')
            if parts[0].strip(): 
                add_frame('disc', [parts[0].strip()])
            if len(parts) > 1 and parts[1].strip(): 
                add_frame('totaldiscs', [parts[1].strip()])
                
        if schema == 'extended':
            # Add other frames not covered by canonical
            known_frames = {'TIT2', 'TPE1', 'TALB', 'TPE2', 'TCON', 'COMM', 'TCOM', 
                           'TPE3', 'TXXX', 'TDRC', 'TORY', 'TDAT', 'TRCK', 'TPOS'}
            for key, frame in tags.items():
                # Skip if it's a known frame ID or starts with one (like COMM::eng)
                is_known = False
                for k in known_frames:
                    if key.startswith(k):
                        is_known = True
                        break
                
                if not is_known:
                    vals = []
                    if hasattr(frame, 'text'):
                        vals = [str(x) for x in frame.text]
                    elif hasattr(frame, 'url'):
                        vals = [str(frame.url)]
                    else:
                        vals = [str(frame)]
                    
                    c_key = canon_key(key)
                    if vals:
                        add_frame(c_key, vals)

        # Finalize
        out = {k: [] for k in CANONICAL_FIELDS}
        for k, frames in collected.items():
            out[k] = self._deduplicate_frames(frames)
                    
        return out
    
    def _read_flac_fields(self, tags: Any, schema: str = 'canonical') -> Dict[str, List[str]]:
        """Read fields from FLAC files."""
        if schema == 'raw':
            # Vorbis comments are practically a dict already
            return {k: [str(v) for v in vals] for k, vals in tags.items()}

        collected = {k: [] for k in CANONICAL_FIELDS}
        
        def add_frame(key: str, vals: List[str]) -> None:
             if vals:
                 if key not in collected:
                     collected[key] = []
                 collected[key].append(vals)
        
        def get_list(key: str, alt_keys: Optional[List[str]] = None) -> List[str]:
            keys_to_try = [key]
            if alt_keys:
                keys_to_try.extend(alt_keys)
                
            for k in keys_to_try:
                v = tags.get(k)
                if v is not None:
                    if isinstance(v, (list, tuple)):
                        return [str(x) for x in v if x is not None]
                    return [str(v)]
            return []
        
        add_frame('title', get_list('title'))
        add_frame('artist', get_list('artist'))
        add_frame('album', get_list('album'))
        add_frame('albumartist', get_list('albumartist', ['albumartist_sort']))
        add_frame('genre', get_list('genre', ['genres']))
        add_frame('comment', get_list('comment', ['comments']))
        add_frame('composer', get_list('composer'))
        add_frame('performer', get_list('performer', ['performers']))
        add_frame('date', get_list('date', ['originaldate', 'year']))
        
        # Track numbers
        tn = get_list('tracknumber', ['track'])
        if tn:
            p = tn[0].split('/')
            if p[0].strip():
                add_frame('track', [p[0].strip()])
            if len(p) > 1 and p[1].strip(): 
                add_frame('totaltracks', [p[1].strip()])
        
        tt = get_list('tracktotal', ['totaltracks'])
        if tt:
             add_frame('totaltracks', [tt[0]])
        
        # Disc numbers
        dn = get_list('discnumber', ['disc'])
        if dn:
            p = dn[0].split('/')
            if p[0].strip():
                 add_frame('disc', [p[0].strip()])
            if len(p) > 1 and p[1].strip(): 
                 add_frame('totaldiscs', [p[1].strip()])
        
        dt = get_list('disctotal', ['totaldiscs'])
        if dt:
             add_frame('totaldiscs', [dt[0]])
            
        if schema == 'extended':
            mapped_keys = {'title', 'artist', 'album', 'albumartist', 'albumartist_sort',
                          'genre', 'genres', 'comment', 'comments', 'composer', 
                          'performer', 'performers', 'date', 'originaldate', 'year',
                          'tracknumber', 'track', 'tracktotal', 'totaltracks',
                          'discnumber', 'disc', 'disctotal', 'totaldiscs'}
            
            for k, vals in tags.items():
                k_lower = k.lower()
                if k_lower not in mapped_keys:
                    c_key = canon_key(k)
                    new_vals = [str(v) for v in vals if v is not None]
                    
                    if new_vals:
                        add_frame(c_key, new_vals)
                    
        # Finalize
        out = {k: [] for k in CANONICAL_FIELDS}
        for k, frames in collected.items():
            out[k] = self._deduplicate_frames(frames)
                    
        return out
    
    def _read_easy_tags(self, tags: Any, schema: str = 'canonical') -> Dict[str, List[str]]:
        """Read fields from other formats (Ogg, Opus, WMA, WV, etc.)."""
        if schema == 'raw':
            # Just dump what we have
            return {str(k): [str(v) for v in vals] if isinstance(vals, list) else [str(vals)] 
                    for k, vals in tags.items()}

        collected = {k: [] for k in CANONICAL_FIELDS}
        
        def add_frame(key: str, vals: List[str]) -> None:
             if vals:
                 if key not in collected:
                     collected[key] = []
                 collected[key].append(vals)
        
        def get_list(key: str, alt_keys: Optional[List[str]] = None) -> List[str]:
            keys_to_try = [key]
            if alt_keys:
                keys_to_try.extend(alt_keys)
                
            for k in keys_to_try:
                v = tags.get(k)
                if v is not None:
                    if isinstance(v, (list, tuple)):
                        return [str(x) for x in v if x is not None]
                    return [str(v)]
            return []
        
        add_frame('title', get_list('title'))
        add_frame('artist', get_list('artist'))
        add_frame('album', get_list('album'))
        add_frame('albumartist', get_list('albumartist'))
        add_frame('genre', get_list('genre'))
        add_frame('comment', get_list('comment'))
        add_frame('composer', get_list('composer'))
        add_frame('performer', get_list('performer'))
        add_frame('date', get_list('date'))
        
        # Track numbers
        tn = get_list('tracknumber', ['track'])
        if tn:
            if isinstance(tn[0], str):
                p = tn[0].split('/')
                if p[0].strip():
                    add_frame('track', [p[0].strip()])
                if len(p) > 1 and p[1].strip(): 
                    add_frame('totaltracks', [p[1].strip()])
        
        tt = get_list('tracktotal', ['totaltracks'])
        if tt:
             add_frame('totaltracks', [tt[0]])
        
        # Disc numbers
        dn = get_list('discnumber', ['disc'])
        if dn:
            if isinstance(dn[0], str):
                p = dn[0].split('/')
                if p[0].strip():
                     add_frame('disc', [p[0].strip()])
                if len(p) > 1 and p[1].strip(): 
                    add_frame('totaldiscs', [p[1].strip()])
        
        dt = get_list('disctotal', ['totaldiscs'])
        if dt:
             add_frame('totaldiscs', [dt[0]])
            
        if schema == 'extended':
             mapped_keys = {'title', 'artist', 'album', 'albumartist', 'genre', 'comment', 
                           'composer', 'performer', 'date', 'tracknumber', 'track', 'tracktotal', 
                           'totaltracks', 'discnumber', 'disc', 'disctotal', 'totaldiscs'}
             for k, vals in tags.items():
                if k.lower() not in mapped_keys:
                    c_key = canon_key(k)
                    new_vals = []
                    if isinstance(vals, (list, tuple)):
                        new_vals = [str(v) for v in vals]
                    else:
                        new_vals = [str(vals)]
                        
                    if new_vals:
                        add_frame(c_key, new_vals)
        
        # Finalize
        out = {k: [] for k in CANONICAL_FIELDS}
        for k, frames in collected.items():
            out[k] = self._deduplicate_frames(frames)
            
        return out
    
    def _read_asf_fields(self, tags: Any, schema: str = 'canonical') -> Dict[str, List[str]]:
        """Read fields from ASF/WMA files."""
        if schema == 'raw':
             return {str(k): [str(v.value) if hasattr(v, 'value') else str(v) for v in vals] 
                     for k, vals in tags.items()}

        collected = {k: [] for k in CANONICAL_FIELDS}
        
        def add_frame(key: str, vals: List[str]) -> None:
             if vals:
                 if key not in collected:
                     collected[key] = []
                 collected[key].append(vals)
        
        def get_vals(key: str) -> List[str]:
            vals = tags.get(key)
            if not vals:
                return []
            return [str(v.value) if hasattr(v, 'value') else str(v) for v in vals]

        add_frame('title', get_vals('Title'))
        add_frame('artist', get_vals('Author'))
        add_frame('album', get_vals('WM/AlbumTitle'))
        add_frame('albumartist', get_vals('WM/AlbumArtist'))
        add_frame('genre', get_vals('WM/Genre'))
        add_frame('comment', get_vals('Description'))
        add_frame('composer', get_vals('WM/Composer'))
        add_frame('date', get_vals('WM/Year'))
        add_frame('track', get_vals('WM/TrackNumber'))
        add_frame('disc', get_vals('WM/PartOfSet'))
        add_frame('copyrighted', get_vals('Copyright'))
        add_frame('encodedby', get_vals('WM/EncodingSettings'))
        
        # Performer doesn't have a standard single frame in ASF, check both
        add_frame('performer', get_vals('Performer'))
        add_frame('performer', get_vals('WM/Performer'))
            
        if schema == 'extended':
             mapped_keys = {'Title', 'Author', 'WM/AlbumTitle', 'WM/AlbumArtist', 
                           'WM/Genre', 'Description', 'WM/Composer', 'WM/Year', 
                           'WM/TrackNumber', 'WM/PartOfSet', 'Copyright', 
                           'WM/EncodingSettings', 'Performer', 'WM/Performer'}
             
             for k, vals in tags.items():
                if k not in mapped_keys:
                    c_key = canon_key(k)
                    new_vals = [str(v.value) if hasattr(v, 'value') else str(v) for v in vals]
                    if new_vals:
                        add_frame(c_key, new_vals)
        
        # Finalize
        out = {k: [] for k in CANONICAL_FIELDS}
        for k, frames in collected.items():
            out[k] = self._deduplicate_frames(frames)
            
        return out
    
    def _ensure_tags_exist(self) -> None:
        """Ensure the file has a tags object, creating if necessary."""
        if hasattr(self.mfile, 'tags') and self.mfile.tags is not None:
            return
        
        # Try to add tags based on format
        try:
            # WAV files need ID3 tags added
            if isinstance(self.mfile, wave.WAVE):
                self.mfile.add_tags()
            # Check if format supports adding tags
            elif hasattr(self.mfile, 'add_tags'):
                self.mfile.add_tags()
            else:
                raise RuntimeError(f"Format {self.path.suffix} does not support adding tags")
        except Exception as e:
            raise RuntimeError(f"Cannot add metadata tags to {self.path.suffix} files: {e}")
    
    def write_fields(self, fields: Dict[str, List[str]]) -> None:
        """Write metadata fields to the file."""
        if self.mfile is None:
            raise RuntimeError("No file loaded")
        
        # NEW: Ensure tags exist before attempting to write
        self._ensure_tags_exist()
        
        # Normalize fields to canonical keys
        canonical_fields = {}
        for k, v in fields.items():
            c_key = canon_key(k)
            # Merge if multiple input keys map to same canonical key
            if c_key in canonical_fields:
                canonical_fields[c_key].extend(v)
            else:
                canonical_fields[c_key] = list(v) # Copy list
        
        # Dedupe values
        for k in canonical_fields:
            canonical_fields[k] = self.unique_preserve_order_case_insensitive(canonical_fields[k])
            
        # MP4/M4A
        if isinstance(self.mfile, mp4.MP4):
            self._write_mp4_fields(canonical_fields)
        # ID3 (MP3 / WAV with ID3)
        elif isinstance(self.mfile.tags, id3.ID3) or isinstance(self.mfile, wave.WAVE):
            self._write_id3_fields(canonical_fields)
        # FLAC
        elif isinstance(self.mfile, flac.FLAC):
            self._write_flac_fields(canonical_fields)
        # ASF/WMA
        elif isinstance(self.mfile, asf.ASF):
            self._write_asf_fields(canonical_fields)
        # Other formats
        else:
            self._write_easy_tags(canonical_fields)
    
    def _write_mp4_fields(self, fields: Dict[str, List[str]]) -> None:
        """Write fields to MP4/M4A files."""
        tags = self.mfile.tags
        if tags is None:
            self.mfile.tags = mp4.MP4Tags()
            tags = self.mfile.tags
        
        def set_atom(key: str, vals: List[str]) -> None:
            if not vals:
                try: 
                    del tags[key]
                except KeyError: 
                    pass
            else:
                tags[key] = [str(x) for x in vals]
        
        set_atom('\xa9nam', fields.get('title', []))
        set_atom('\xa9ART', fields.get('artist', []))
        set_atom('\xa9alb', fields.get('album', []))
        set_atom('aART', fields.get('albumartist', []))
        set_atom('\xa9gen', fields.get('genre', []))
        set_atom('\xa9cmt', fields.get('comment', []))
        set_atom('\xa9day', fields.get('date', []))
        set_atom('\xa9wrt', fields.get('composer', []))
        
        # Performer: use iTunes freeform atom
        performer_key = f'----:{Config.DEFAULT_NAMESPACE}:PERFORMER'
        if fields.get('performer'):
            try:
                raw_vals = [str(v).encode('utf-8') for v in fields['performer']]
                tags[performer_key] = raw_vals
            except Exception as e:
                logger.warning(f"Failed to write MP4 performer field: {e}")
                pass
        else:
            try:
                del tags[performer_key]
            except KeyError:
                pass
        
        # Track/disk tuples
        if fields.get('track') or fields.get('totaltracks'):
            tnum = self.safe_int(fields.get('track')[0]) if fields.get('track') else 0
            ttot = self.safe_int(fields.get('totaltracks')[0]) if fields.get('totaltracks') else 0
            tags['trkn'] = [(tnum or 0, ttot or 0)]
        else:
            try: 
                del tags['trkn']
            except KeyError: 
                pass
        
        if fields.get('disc') or fields.get('totaldiscs'):
            dnum = self.safe_int(fields.get('disc')[0]) if fields.get('disc') else 0
            dtot = self.safe_int(fields.get('totaldiscs')[0]) if fields.get('totaldiscs') else 0
            tags['disk'] = [(dnum or 0, dtot or 0)]
        else:
            try: 
                del tags['disk']
            except KeyError: 
                pass
        
        # Write custom/unknown fields as freeform atoms
        known_fields = {
            'title', 'artist', 'album', 'albumartist', 'genre', 'comment', 
            'date', 'composer', 'performer', 'track', 'totaltracks', 'disc', 'totaldiscs'
        }
        
        for key, vals in fields.items():
            if key not in known_fields:
                atom_key = key
                if not key.startswith('----:') and not key.startswith('©') and not key.startswith('covr'):
                     clean_key = self._sanitize_custom_key(key)
                     atom_key = f"----:{Config.DEFAULT_NAMESPACE}:{clean_key}"
                     
                     # Remove existing keys with same name but different case
                     # This ensures we overwrite mixed-case duplicates
                     keys_to_remove = [k for k in tags.keys() if k.lower() == atom_key.lower()]
                     for k in keys_to_remove:
                         del tags[k]
                
                if not vals:
                    # Handle deletion for custom fields
                    try:
                        del tags[atom_key]
                    except KeyError:
                        pass
                    continue

                if atom_key.startswith('----:'):
                    tags[atom_key] = [str(v).encode('utf-8') for v in vals]
                else:
                    # Try writing as-is for other atoms (might fail if not standard)
                    try:
                        tags[atom_key] = [str(v) for v in vals]
                    except Exception as e:
                        logger.warning(f"Failed to write custom MP4 atom {atom_key}: {e}")
                        pass

        self.mfile.save()

    def delete_fields(self, fields: List[str]) -> None:
        """
        Delete specified fields from the file.
        
        Args:
            fields: List of field names to delete.
        """
        updates = {field: [] for field in fields}
        self.write_fields(updates)
    
    def _write_id3_fields(self, fields: Dict[str, List[str]]) -> None:
        """Write fields to ID3 files (MP3/WAV)."""
        if not isinstance(self.mfile.tags, id3.ID3):
            self.mfile.tags = id3.ID3()
        
        tags = self.mfile.tags
        
        # Remove frames we manage (preserve TPE3 for performer)
        frames_to_remove = ['TIT2', 'TALB', 'TPE1', 'TPE2', 'TCON', 'COMM', 
                           'TDRC', 'TRCK', 'TPOS', 'TCOM']
        for frame in frames_to_remove:
            tags.delall(frame)
        
        # Remove TXXX PERFORMER frames
        for tx in list(tags.getall('TXXX')):
            try:
                desc = (getattr(tx, 'desc', '') or '').strip().lower()
                if desc in ('performer', 'performers', 'perf'):
                    tags.delall(tx.FrameID)
            except Exception as e:
                logger.debug(f"Failed to remove ID3 TXXX performer frame: {e}")
                continue
        
        # Add fields
        if fields.get('title'):
            tags.add(id3.TIT2(encoding=3, text=fields['title']))
        if fields.get('album'):
            tags.add(id3.TALB(encoding=3, text=fields['album']))
        if fields.get('artist'):
            tags.add(id3.TPE1(encoding=3, text=fields['artist']))
        if fields.get('albumartist'):
            tags.add(id3.TPE2(encoding=3, text=fields['albumartist']))
        if fields.get('genre'):
            tags.add(id3.TCON(encoding=3, text=fields['genre']))
        if fields.get('comment'):
            # Collapse multiple comments into a single frame as requested
            tags.add(id3.COMM(encoding=3, lang='eng', desc='', text=fields['comment']))
        if fields.get('composer'):
            tags.add(id3.TCOM(encoding=3, text=fields['composer']))
        
        # Performer: write as TXXX
        if fields.get('performer'):
            try:
                tags.add(id3.TXXX(encoding=3, desc='PERFORMER', text=fields['performer']))
            except Exception as e:
                logger.warning(f"Failed to write ID3 performer field: {e}")
                pass
        
        if fields.get('date'):
            tags.add(id3.TDRC(encoding=3, text=fields['date']))
        
        # TRCK / TPOS
        if fields.get('track') or fields.get('totaltracks'):
            tnum = fields.get('track')[0] if fields.get('track') else ''
            ttot = fields.get('totaltracks')[0] if fields.get('totaltracks') else ''
            trck_text = f"{tnum}/{ttot}" if ttot else str(tnum)
            tags.add(id3.TRCK(encoding=3, text=[trck_text]))
        
        if fields.get('disc') or fields.get('totaldiscs'):
            dnum = fields.get('disc')[0] if fields.get('disc') else ''
            dtot = fields.get('totaldiscs')[0] if fields.get('totaldiscs') else ''
            tpos_text = f"{dnum}/{dtot}" if dtot else str(dnum)
            tags.add(id3.TPOS(encoding=3, text=[tpos_text]))
            
        # Write custom/unknown fields as TXXX
        known_fields = {
            'title', 'artist', 'album', 'albumartist', 'genre', 'comment', 
            'composer', 'performer', 'date', 'track', 'totaltracks', 'disc', 'totaldiscs'
        }
        
        for key, vals in fields.items():
            if key not in known_fields:
                # Handle TXXX: prefix from extended read
                search_key = key
                if search_key.startswith('TXXX:'):
                    search_key = search_key[5:]
                
                # Remove any existing TXXX with this desc first
                current_txxx = tags.getall('TXXX')
                new_txxx = [tx for tx in current_txxx if (getattr(tx, 'desc', '') or '').strip().lower() != search_key.lower()]
                
                if len(new_txxx) != len(current_txxx):
                    tags.setall('TXXX', new_txxx)
                
                if vals:
                    try:
                        tags.add(id3.TXXX(encoding=3, desc=self._sanitize_custom_key(search_key), text=vals))
                    except Exception as e:
                        logger.warning(f"Failed to write custom ID3 field {search_key}: {e}")
                        pass
        
        self.mfile.save()
    
    def _write_flac_fields(self, fields: Dict[str, List[str]]) -> None:
        """Write fields to FLAC files."""
        if self.mfile.tags is None:
            self.mfile.add_tags()
        
        tags = self.mfile.tags
        
        def set_or_del(key: str, vals: List[str]) -> None:
            if not vals:
                try: 
                    del tags[key]
                except KeyError: 
                    pass
            else:
                tags[key] = vals
        
        set_or_del('title', fields.get('title', []))
        set_or_del('artist', fields.get('artist', []))
        set_or_del('album', fields.get('album', []))
        set_or_del('albumartist', fields.get('albumartist', []))
        set_or_del('genre', fields.get('genre', []))
        set_or_del('comment', fields.get('comment', []))
        set_or_del('composer', fields.get('composer', []))
        set_or_del('performer', fields.get('performer', []))
        set_or_del('date', fields.get('date', []))

        # Track numbers
        if fields.get('track') or fields.get('totaltracks'):
            tnum = fields.get('track')[0] if fields.get('track') else ''
            ttot = fields.get('totaltracks')[0] if fields.get('totaltracks') else ''
            
            if tnum:
                tags['tracknumber'] = str(tnum)
            else:
                try: 
                    del tags['tracknumber']
                except KeyError: 
                    pass
                    
            if ttot:
                tags['tracktotal'] = str(ttot)
                tags['totaltracks'] = str(ttot)
            else:
                try:
                    del tags['tracktotal']
                except KeyError: 
                    pass
                try:
                    del tags['totaltracks']
                except KeyError: 
                    pass

        # Disc numbers
        if fields.get('disc') or fields.get('totaldiscs'):
            dnum = fields.get('disc')[0] if fields.get('disc') else ''
            dtot = fields.get('totaldiscs')[0] if fields.get('totaldiscs') else ''
            
            if dnum:
                tags['discnumber'] = str(dnum)
            else:
                try: 
                    del tags['discnumber']
                except KeyError: 
                    pass
                    
            if dtot:
                tags['disctotal'] = str(dtot)
                tags['totaldiscs'] = str(dtot)
            else:
                try:
                    del tags['disctotal']
                except KeyError: 
                    pass
                try:
                    del tags['totaldiscs']
                except KeyError: 
                    pass

        self.mfile.save()
        
        # Write custom/unknown fields
        known_fields = {
            'title', 'artist', 'album', 'albumartist', 'genre', 'comment', 
            'composer', 'performer', 'date', 'track', 'totaltracks', 'disc', 'totaldiscs'
        }
        
        for key, vals in fields.items():
            if key not in known_fields:
                if not vals:
                    # Handle deletion for custom fields
                    try:
                        del tags[key]
                    except KeyError:
                        pass
                else:
                    # Mutagen handles list of strings automatically
                    tags[self._sanitize_custom_key(key)] = vals
                
        self.mfile.save()
    
    def _write_easy_tags(self, fields: Dict[str, List[str]]) -> None:
        """Write fields to other formats (Ogg, Opus, WMA, WV, etc.)."""
        if self.mfile.tags is None:
            self.mfile.add_tags()
        
        tags = self.mfile.tags
        
        def set_or_del(key: str, vals: List[str]) -> None:
            if not vals:
                try: 
                    del tags[key]
                except KeyError: 
                    pass
            else:
                tags[key] = vals
        
        set_or_del('title', fields.get('title', []))
        set_or_del('artist', fields.get('artist', []))
        set_or_del('album', fields.get('album', []))
        set_or_del('albumartist', fields.get('albumartist', []))
        set_or_del('genre', fields.get('genre', []))
        set_or_del('comment', fields.get('comment', []))
        set_or_del('composer', fields.get('composer', []))
        set_or_del('performer', fields.get('performer', []))
        set_or_del('date', fields.get('date', []))

        # Track numbers
        if fields.get('track') or fields.get('totaltracks'):
            tnum = fields.get('track')[0] if fields.get('track') else ''
            ttot = fields.get('totaltracks')[0] if fields.get('totaltracks') else ''
            
            if tnum and ttot:
                tags['tracknumber'] = f"{tnum}/{ttot}"
            elif tnum:
                tags['tracknumber'] = str(tnum)
            else:
                try: 
                    del tags['tracknumber']
                except KeyError: 
                    pass

        # Disc numbers
        if fields.get('disc') or fields.get('totaldiscs'):
            dnum = fields.get('disc')[0] if fields.get('disc') else ''
            dtot = fields.get('totaldiscs')[0] if fields.get('totaldiscs') else ''
            
            if dnum and dtot:
                tags['discnumber'] = f"{dnum}/{dtot}"
            elif dnum:
                tags['discnumber'] = str(dnum)
            else:
                try: 
                    del tags['discnumber']
                except KeyError: 
                    pass

        self.mfile.save()
        
        # Write custom/unknown fields
        known_fields = {
            'title', 'artist', 'album', 'albumartist', 'genre', 'comment', 
            'composer', 'performer', 'date', 'track', 'totaltracks', 'disc', 'totaldiscs'
        }
        
        for key, vals in fields.items():
            if key not in known_fields:
                if not vals:
                    try:
                        del tags[key]
                    except KeyError:
                        pass
                else:
                    try:
                        tags[self._sanitize_custom_key(key)] = vals
                    except Exception as e:
                        logger.warning(f"Failed to write custom Vorbis field {key}: {e}")
                        pass
                    
        self.mfile.save()
            
    def _write_asf_fields(self, fields: Dict[str, List[str]]) -> None:
        """Write fields to ASF/WMA files."""
        tags = self.mfile.tags
        if tags is None:
             # Typically ASF tags are always present or created on load, but just in case
             pass
        
        def set_val(asf_key: str, vals: List[str], type_hint=None) -> None:
            if not vals:
                try: 
                    del tags[asf_key]
                except KeyError: 
                    pass
            else:
                # Mutagen ASF uses specific attribute types
                # We'll let mutagen infer or convert to UnicodeAttribute
                # If we need specific types (like boolean or qword), we'd need asf.ASF*Attribute
                # For now, strings are UnicodeAttribute
                new_attrs = []
                for v in vals:
                    new_attrs.append(asf.ASFUnicodeAttribute(str(v)))
                tags[asf_key] = new_attrs

        # Helper to clean legacy/conflicting custom keys
        def clean_legacy(keys_to_clean: List[str]):
            for k in keys_to_clean:
                try: del tags[k]
                except KeyError: pass

        set_val('Title', fields.get('title', []))
        clean_legacy(['title']) # Clean lowercase 'title' if present

        set_val('Author', fields.get('artist', []))
        clean_legacy(['artist', 'author']) # Clean lowercase 'artist'/'author'

        set_val('WM/AlbumTitle', fields.get('album', []))
        clean_legacy(['album'])

        set_val('WM/AlbumArtist', fields.get('albumartist', []))
        clean_legacy(['albumartist', 'album_artist'])

        set_val('WM/Genre', fields.get('genre', []))
        clean_legacy(['genre'])

        set_val('Description', fields.get('comment', []))
        clean_legacy(['comment'])

        set_val('WM/Composer', fields.get('composer', []))
        clean_legacy(['composer'])

        set_val('WM/Year', fields.get('date', []))
        clean_legacy(['date', 'year'])
        
        # Performer
        if fields.get('performer'):
             set_val('WM/Performer', fields.get('performer', []))
             # Also write legacy 'Performer' if needed? sticking to WM/Performer is safer for Windows
        else:
             try: del tags['WM/Performer'] 
             except KeyError: pass
             try: del tags['Performer'] 
             except KeyError: pass

        # Track/Disc
        # WM/TrackNumber is typically string in WMA tags seen in wild
        # But specifically 0-based or 1-based? Usually 1-based.
        # We will write what we have.
        if fields.get('track'):
             set_val('WM/TrackNumber', fields.get('track'))
        else:
             try: del tags['WM/TrackNumber']
             except KeyError: pass
             
        if fields.get('disc'):
             set_val('WM/PartOfSet', fields.get('disc'))
        else:
             try: del tags['WM/PartOfSet']
             except KeyError: pass
        
        # Write totaltracks/totaldiscs if present?
        # No standard frame, maybe custom
        
        # Write custom fields defined in fields
        known_fields = {
            'title', 'artist', 'album', 'albumartist', 'genre', 'comment', 
            'composer', 'performer', 'date', 'track', 'disc',
            'copyrighted', 'encodedby'
        }
    
        for key, vals in fields.items():
            if key not in known_fields:
                 # Use key as is for custom field
                 set_val(self._sanitize_custom_key(key), vals)
        
        self.mfile.save()
            
    @staticmethod
    def _truncate(s: Any, max_len: int = 50) -> str:
        """Truncate string for display."""
        s = str(s) if s is not None else ""
        return s if len(s) <= max_len else s[:47] + "..."

    @staticmethod
    def _sanitize_custom_key(key: str) -> str:
        """
        Sanitize custom key to contain only [A-Z0-9_].
        Replaces non-alphanumeric characters with underscore and uppercases.
        """
        import re
        # Replace non-alphanumeric chars with underscore
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', key)
        return sanitized.upper()

    @staticmethod
    def _sanitize_read_key(key: str) -> str:
        """
        Sanitize key for reading to contain only [a-z0-9_].
        Lowercases and replaces non-alphanumeric characters with underscore.
        """
        import re
        key = key.lower()
        return re.sub(r'[^a-z0-9_]', '_', key)

    def __str__(self) -> str:
        """Return formatted metadata as a string."""
        return self._format_metadata()

    def _format_metadata(self) -> str:
        """Build the formatted metadata string."""
        lines = []
        lines.append(f"=== {self.path.name} ===")
        
        if self.mfile is None or self.mfile.tags is None:
            lines.append("No metadata found.")
            return "\n".join(lines)
        
        tags = self.mfile.tags
        
        # Format based on file type (similar to your print_fields logic)
        # MP4/M4A
        if isinstance(self.mfile, mp4.MP4):
            for key, values in sorted(tags.items()):
                if key == 'covr':
                    if isinstance(values, list) and len(values) > 0:
                        lines.append(f"{key:15}: <image: {len(values)} cover(s), first: {len(values[0])} bytes>")
                    else:
                        lines.append(f"{key:15}: <image present>")
                else:
                    val_str = "; ".join(self._truncate(v) for v in values)
                    lines.append(f"{key:15}: {val_str}")
        
        # ID3 (MP3/WAV)
        elif isinstance(tags, id3.ID3):
            for frame_id in sorted(tags.keys()):
                frames = tags.getall(frame_id)
                if frame_id.startswith('APIC'):
                    if len(frames) == 1:
                        frame = frames[0]
                        mime = getattr(frame, 'mime', 'unknown')
                        size = len(getattr(frame, 'data', b''))
                        lines.append(f"{frame_id:15}: <image: {mime}, {size} bytes>")
                    else:
                        lines.append(f"{frame_id:15}: <{len(frames)} images present>")
                else:
                    all_texts = []
                    for frame in frames:
                        if hasattr(frame, 'text'):
                            all_texts.extend(str(t) for t in frame.text)
                        else:
                            all_texts.append("<unsupported frame>")
                    
                    if all_texts:
                        val_str = "; ".join(self._truncate(t) for t in all_texts)
                        lines.append(f"{frame_id:15}: {val_str}")
        
        # FLAC
        elif isinstance(self.mfile, flac.FLAC):
            for key in sorted(tags.keys()):
                values = tags[key]
                if isinstance(values, list):
                    val_str = "; ".join(self._truncate(v) for v in values)
                else:
                    val_str = self._truncate(values)
                lines.append(f"{key:15}: {val_str}")
            
            # FLAC pictures
            if hasattr(self.mfile, 'pictures') and self.mfile.pictures:
                pics = self.mfile.pictures
                if len(pics) == 1:
                    pic = pics[0]
                    lines.append(f"{'picture':15}: <image: {pic.mime}, {len(pic.data)} bytes>")
                else:
                    lines.append(f"{'picture':15}: <{len(pics)} images present>")
        
        # Other formats
        else:
            for key in sorted(tags.keys()):
                values = tags[key]
                if isinstance(values, list):
                    val_str = "; ".join(self._truncate(v) for v in values)
                else:
                    val_str = self._truncate(values)
                lines.append(f"{key:15}: {val_str}")
        
        return "\n".join(lines)

    @staticmethod
    @contextmanager
    def managed(path: Union[str, Path]) -> Generator['SimpleMusic', None, None]:
        """Context manager for SimpleMusic with proper resource cleanup."""
        sm = None
        try:
            sm = SimpleMusic(path)
            yield sm
        except Exception as e:
            logger.error(f"Failed to load music file {path}: {e}")
            raise
        finally:
            if sm:
                try:
                    sm.close()
                except Exception as close_error:
                    logger.warning(f"Error during cleanup of {path}: {close_error}")

# Keep test class as before
class SimpleMusicTests(unittest.TestCase):
    """Unit tests for SimpleMusic class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="mudio_test_"))
        
    def tearDown(self):
        """Clean up test fixtures."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_parse_list_string(self):
        """Test parse_list_string method."""
        self.assertEqual(SimpleMusic.parse_list_string("a;b;c"), ["a", "b", "c"])
        self.assertEqual(SimpleMusic.parse_list_string("a; b ; c"), ["a", "b", "c"])
        self.assertEqual(SimpleMusic.parse_list_string(""), [])
        self.assertEqual(SimpleMusic.parse_list_string(None), [])
    
    def test_unique_preserve_order_case_insensitive(self):
        """Test unique_preserve_order_case_insensitive method."""
        input_list = ["Artist", "artist", "ARTIST", "New Artist"]
        result = SimpleMusic.unique_preserve_order_case_insensitive(input_list)
        self.assertEqual(result, ["Artist", "New Artist"])
    
    def test_safe_int(self):
        """Test safe_int method."""
        self.assertEqual(SimpleMusic.safe_int("123"), 123)
        self.assertEqual(SimpleMusic.safe_int(456), 456)
        self.assertIsNone(SimpleMusic.safe_int("invalid"))
        self.assertIsNone(SimpleMusic.safe_int(None))
    
    @patch('mutagen.File')
    def test_file_loading(self, mock_mutagen):
        """Test file loading with mutagen."""
        mock_file = Mock()
        mock_mutagen.return_value = mock_file
        
        test_file = self.test_dir / "test.mp3"
        test_file.write_bytes(b"fake content")
        
        sm = SimpleMusic(test_file)
        self.assertEqual(sm.path, test_file)
        self.assertEqual(sm.mfile, mock_file)
        
        with self.assertRaises(RuntimeError):
            SimpleMusic(self.test_dir / "nonexistent.mp3")
    
    def test_context_manager(self):
        """Test context manager functionality."""
        with patch('mutagen.File') as mock_mutagen:
            mock_file = Mock()
            mock_mutagen.return_value = mock_file
            
            test_file = self.test_dir / "test.mp3"
            test_file.write_bytes(b"fake content")
            
            with SimpleMusic(test_file) as sm:
                self.assertIsInstance(sm, SimpleMusic)
            
            mock_file.close.assert_called_once()

    @staticmethod
    def run_tests() -> Dict[str, Any]:
        """Run all SimpleMusic unit tests."""
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(SimpleMusicTests)
        
        runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
        result = runner.run(suite)
        
        return {
            'tests_run': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'successful': result.testsRun - len(result.failures) - len(result.errors)
        }

managed_simple_music = SimpleMusic.managed

if __name__ == '__main__':
    # Run tests if executed directly
    results = SimpleMusicTests.run_tests()
    print(f"SimpleMusic Tests: {results['successful']}/{results['tests_run']} passed")