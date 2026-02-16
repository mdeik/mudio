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
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Generator
import unittest
from unittest.mock import Mock, patch
import sys
import tempfile
from contextlib import contextmanager
import shutil
import logging

logger = logging.getLogger(__name__)

SUPPORTED_EXT = {'.mp3', '.flac', '.m4a', '.mp4', '.ogg', '.opus', '.wav', '.wma', '.wv'}

CANONICAL_FIELDS = [
    'title', 'artist', 'album', 'albumartist', 'genre', 'comment',
    'composer', 'performer', 'date', 'track', 'totaltracks', 
    'disc', 'totaldiscs'
]

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
            return self._read_mp4_fields(self.mfile.tags, schema=schema)
        
        # ID3 (MP3/WAV with ID3v2 tags)
        if isinstance(self.mfile.tags, id3.ID3):
            return self._read_id3_fields(self.mfile.tags, schema=schema)
        
        # FLAC files
        if isinstance(self.mfile, flac.FLAC):
            return self._read_flac_fields(self.mfile.tags, schema=schema)
        
        # Other formats (Ogg, Opus, WMA, WV, etc.)
        return self._read_easy_tags(self.mfile.tags, schema=schema)
    
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

        out = {k: [] for k in CANONICAL_FIELDS}
        
        def get_vals(key: str) -> List[str]:
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
        
        out['title'] = get_vals('\xa9nam')
        out['artist'] = get_vals('\xa9ART')
        out['album'] = get_vals('\xa9alb')
        out['albumartist'] = get_vals('aART')
        out['genre'] = get_vals('\xa9gen')
        out['comment'] = get_vals('\xa9cmt')
        out['date'] = get_vals('\xa9day')
        out['composer'] = get_vals('\xa9wrt')
        
        # Performer handling for MP4
        perf_vals_list = []
        
        # 'perf' atom
        if 'perf' in tags:
            perf_vals_list.append(get_vals('perf'))
            
        # Try different performer tag variations
        for perf_key in ['\xa9prf', 'Â©prf', '----:com.apple.iTunes:PERFORMER']:
             if perf_key in tags:
                perf_vals_list.append(get_vals(perf_key))
                
        out['performer'] = self._deduplicate_frames(perf_vals_list)
        
        # Track/disk tuples
        trkn = tags.get('trkn')
        if trkn and isinstance(trkn, list) and len(trkn) > 0:
            try:
                tnum, ttot = trkn[0]
                if tnum is not None: 
                    out['track'] = [str(tnum)]
                if ttot is not None and ttot != 0: 
                    out['totaltracks'] = [str(ttot)]
            except Exception as e:
                logger.debug(f"Failed to parse MP4 track number: {e}")
                pass
        
        # Fallback: check for custom track/totaltracks fields if standard atom missed
        if not out['track']:
            for k in ['----:com.apple.iTunes:track', '----:com.apple.iTunes:TRACK']:
                val = get_vals(k)
                if val:
                    out['track'] = val
                    break
        
        if not out['totaltracks']:
            for k in ['----:com.apple.iTunes:totaltracks', '----:com.apple.iTunes:TOTALTRACKS']:
                val = get_vals(k)
                if val:
                    out['totaltracks'] = val
                    break

        disk = tags.get('disk')
        if disk and isinstance(disk, list) and len(disk) > 0:
            try:
                dnum, dtot = disk[0]
                if dnum is not None: 
                    out['disc'] = [str(dnum)]
                if dtot is not None and dtot != 0:
                    out['totaldiscs'] = [str(dtot)]
            except Exception as e:
                logger.debug(f"Failed to parse MP4 disc number: {e}")
                pass

        # Fallback: check for custom disc/totaldiscs fields if standard atom missed
        if not out['disc']:
            for k in ['----:com.apple.iTunes:disc', '----:com.apple.iTunes:DISC']:
                val = get_vals(k)
                if val:
                    out['disc'] = val
                    break
        
        if not out['totaldiscs']:
             for k in ['----:com.apple.iTunes:totaldiscs', '----:com.apple.iTunes:TOTALDISCS']:
                val = get_vals(k)
                if val:
                    out['totaldiscs'] = val
                    break
                
        if schema == 'extended':
            # Add other atoms
            # Mappped atom keys
            mapped = {'\xa9nam', '\xa9ART', '\xa9alb', 'aART', '\xa9gen', 
                      '\xa9cmt', '\xa9day', '\xa9wrt', 'perf', '\xa9prf', 
                      'trkn', 'disk', 'covr', 'cpil', 'pgap', 'tmpo'}
            
            for k, vals in tags.items():
                if k not in mapped and not k.startswith('----:com.apple.iTunes:PERFORMER'):
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
                    if k.startswith('----:com.apple.iTunes:'):
                        clean_key = k[len('----:com.apple.iTunes:'):]
                    elif k.startswith('----:'):
                        clean_key = k[len('----:'):]
                        
                    out[clean_key] = outvals
        
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

        out = {k: [] for k in CANONICAL_FIELDS}
        
        def get_frame(frame_name: str) -> List[str]:
            frame = tags.get(frame_name)
            if not frame:
                return []
            return [str(x) for x in getattr(frame, 'text', [])]
        
        out['title'] = get_frame('TIT2')
        out['artist'] = get_frame('TPE1')
        out['album'] = get_frame('TALB')
        out['albumartist'] = get_frame('TPE2')
        out['genre'] = get_frame('TCON')
        
        # Comments
        comms = tags.getall('COMM')
        if comms:
            comm_frames = []
            comm_frames = []
            for c in comms:
                if hasattr(c, 'text'):
                    comm_frames.append([str(x) for x in c.text])
            out['comment'] = self._deduplicate_frames(comm_frames)
        
        out['composer'] = get_frame('TCOM')
        
        # Performer: include TPE3 and TXXX:PERFORMER
        perf_frames = []
        tpe3 = get_frame('TPE3')
        if tpe3:
            perf_frames.append(tpe3)
            
        txxx_frames = tags.getall('TXXX')
        for tx in txxx_frames:
            try:
                desc = (getattr(tx, 'desc', '') or '').strip().lower()
                if desc in ('performer', 'performers', 'perf'):
                    if hasattr(tx, 'text'):
                        perf_frames.append([str(x) for x in getattr(tx, 'text', [])])
                
                # Extended schema: add TXXX frames that aren't performer
                if schema == 'extended' and desc not in ('performer', 'performers', 'perf'):
                     # Note: We aren't deduping extended TXXX here easily because we iterate them.
                     # But duplication of TXXX with same desc is rare/handled by list append usually.
                     # For now, just append.
                     if hasattr(tx, 'text'):
                        vals = [str(x) for x in getattr(tx, 'text', [])]
                        if desc in out:
                            out[desc].extend(vals)
                        else:
                            out[desc] = vals
            except Exception as e:
                logger.debug(f"Failed to parse ID3 TXXX frame: {e}")
                continue
        
        if perf_frames:
            out['performer'] = self._deduplicate_frames(perf_frames)
        
        out['date'] = get_frame('TDRC') or get_frame('TORY') or get_frame('TDAT')
        
        out['date'] = get_frame('TDRC') or get_frame('TORY') or get_frame('TDAT')
        
        # Track/position parsing
        tr = get_frame('TRCK')
        if tr:
            parts = str(tr[0]).split('/')
            if parts[0].strip(): 
                out['track'] = [parts[0].strip()]
            if len(parts) > 1 and parts[1].strip(): 
                out['totaltracks'] = [parts[1].strip()]
        
        tp = get_frame('TPOS')
        if tp:
            parts = str(tp[0]).split('/')
            if parts[0].strip(): 
                out['disc'] = [parts[0].strip()]
            if len(parts) > 1 and parts[1].strip(): 
                out['totaldiscs'] = [parts[1].strip()]
                
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
                    out[key] = vals
                    
        return out
    
    def _read_flac_fields(self, tags: Any, schema: str = 'canonical') -> Dict[str, List[str]]:
        """Read fields from FLAC files."""
        if schema == 'raw':
            # Vorbis comments are practically a dict already
            return {k: [str(v) for v in vals] for k, vals in tags.items()}

        out = {k: [] for k in CANONICAL_FIELDS}
        
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
        
        out['title'] = get_list('title')
        out['artist'] = get_list('artist')
        out['album'] = get_list('album')
        out['albumartist'] = get_list('albumartist', ['albumartist_sort'])
        out['genre'] = get_list('genre', ['genres'])
        out['comment'] = get_list('comment', ['comments'])
        out['composer'] = get_list('composer')
        out['performer'] = get_list('performer', ['performers'])
        out['date'] = get_list('date', ['originaldate', 'year'])
        
        # Track numbers
        tn = get_list('tracknumber', ['track'])
        if tn:
            p = tn[0].split('/')
            out['track'] = [p[0].strip()] if p[0].strip() else []
            if len(p) > 1 and p[1].strip(): 
                out['totaltracks'] = [p[1].strip()]
        
        tt = get_list('tracktotal', ['totaltracks'])
        if tt:
            out['totaltracks'] = [tt[0]]
        
        # Disc numbers
        dn = get_list('discnumber', ['disc'])
        if dn:
            p = dn[0].split('/')
            out['disc'] = [p[0].strip()] if p[0].strip() else []
            if len(p) > 1 and p[1].strip(): 
                out['totaldiscs'] = [p[1].strip()]
        
        dt = get_list('disctotal', ['totaldiscs'])
        if dt:
            out['totaldiscs'] = [dt[0]]
            
        if schema == 'extended':
            mapped_keys = {'title', 'artist', 'album', 'albumartist', 'albumartist_sort',
                          'genre', 'genres', 'comment', 'comments', 'composer', 
                          'performer', 'performers', 'date', 'originaldate', 'year',
                          'tracknumber', 'track', 'tracktotal', 'totaltracks',
                          'discnumber', 'disc', 'disctotal', 'totaldiscs'}
            
            for k, vals in tags.items():
                if k.lower() not in mapped_keys:
                    out[k] = [str(v) for v in vals if v is not None]
                    
        return out
    
    def _read_easy_tags(self, tags: Any, schema: str = 'canonical') -> Dict[str, List[str]]:
        """Read fields from other formats (Ogg, Opus, WMA, WV, etc.)."""
        if schema == 'raw':
            # Just dump what we have
            return {str(k): [str(v) for v in vals] if isinstance(vals, list) else [str(vals)] 
                    for k, vals in tags.items()}

        out = {k: [] for k in CANONICAL_FIELDS}
        
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
        
        out['title'] = get_list('title')
        out['artist'] = get_list('artist')
        out['album'] = get_list('album')
        out['albumartist'] = get_list('albumartist')
        out['genre'] = get_list('genre')
        out['comment'] = get_list('comment')
        out['composer'] = get_list('composer')
        out['performer'] = get_list('performer')
        out['date'] = get_list('date')
        
        # Track numbers
        tn = get_list('tracknumber', ['track'])
        if tn:
            if isinstance(tn[0], str):
                p = tn[0].split('/')
                out['track'] = [p[0].strip()] if p[0].strip() else []
                if len(p) > 1 and p[1].strip(): 
                    out['totaltracks'] = [p[1].strip()]
        
        tt = get_list('tracktotal', ['totaltracks'])
        if tt:
            out['totaltracks'] = [tt[0]]
        
        # Disc numbers
        dn = get_list('discnumber', ['disc'])
        if dn:
            if isinstance(dn[0], str):
                p = dn[0].split('/')
                out['disc'] = [p[0].strip()] if p[0].strip() else []
                if len(p) > 1 and p[1].strip(): 
                    out['totaldiscs'] = [p[1].strip()]
        
        dt = get_list('disctotal', ['totaldiscs'])
        if dt:
            out['totaldiscs'] = [dt[0]]
            
        if schema == 'extended':
             mapped_keys = {'title', 'artist', 'album', 'albumartist', 'genre', 'comment', 
                           'composer', 'performer', 'date', 'tracknumber', 'track', 'tracktotal', 
                           'totaltracks', 'discnumber', 'disc', 'disctotal', 'totaldiscs'}
             for k, vals in tags.items():
                if k.lower() not in mapped_keys:
                    if isinstance(vals, (list, tuple)):
                        out[k] = [str(v) for v in vals]
                    else:
                        out[k] = [str(vals)]
        
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
        
        # MP4/M4A
        if isinstance(self.mfile, mp4.MP4):
            self._write_mp4_fields(fields)
        # ID3 (MP3 / WAV with ID3)
        elif isinstance(self.mfile.tags, id3.ID3) or isinstance(self.mfile, wave.WAVE):
            self._write_id3_fields(fields)
        # FLAC
        elif isinstance(self.mfile, flac.FLAC):
            self._write_flac_fields(fields)
        # Other formats
        else:
            self._write_easy_tags(fields)
    
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
        performer_key = '----:com.apple.iTunes:PERFORMER'
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
                     atom_key = f"----:com.apple.iTunes:{key.upper()}"
                
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
                if search_key.upper().startswith('TXXX:'):
                    search_key = search_key[5:]
                
                # Remove any existing TXXX with this desc first
                current_txxx = tags.getall('TXXX')
                new_txxx = [tx for tx in current_txxx if (getattr(tx, 'desc', '') or '').strip().lower() != search_key.lower()]
                
                if len(new_txxx) != len(current_txxx):
                    tags.setall('TXXX', new_txxx)
                
                if vals:
                    try:
                        tags.add(id3.TXXX(encoding=3, desc=search_key, text=vals))
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
            if key not in known_fields and vals:
                # Vorbis comments are easy, just set the key
                # Mutagen handles list of strings automatically
                tags[key] = vals
                
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
            if key not in known_fields and vals:
                try:
                    tags[key] = vals
                except Exception as e:
                    logger.warning(f"Failed to write custom Vorbis field {key}: {e}")
                    pass
                    
        self.mfile.save()
            
    @staticmethod
    def _truncate(s: Any, max_len: int = 50) -> str:
        """Truncate string for display."""
        s = str(s) if s is not None else ""
        return s if len(s) <= max_len else s[:47] + "..."

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