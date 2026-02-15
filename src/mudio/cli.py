"""mudio CLI - Audio metadata tool for the command line."""
import os
import sys
import argparse
import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional, Callable

from .processor import register_signal_handlers, unregister_signal_handlers

# Core imports
from .core import CANONICAL_FIELDS,managed_simple_music
from .utils import (
    Config, 
    setup_logging, 
    join_for_printing, 
    print_progress_safe, 
    EXIT_CODE_SUCCESS, 
    EXIT_CODE_ERROR, 
    EXIT_CODE_USAGE, 
    EXIT_CODE_PERMISSION, 
    EXIT_CODE_INTERRUPTED,
    EXIT_CODE_NO_FILES,
    EXIT_CODE_DISK_FULL
)
from .operations import (
    FieldOperationsType, 
    FieldValuesType, 
    FilterType,
    op_overwrite,
    op_find_replace,
    op_append,
    op_prefix,
    op_prefix,
    op_enlist,
    op_delist,
    op_clear,
    op_delete
)
from .processor import (
    ProcessResultType,
    process_file,
    process_files,
    verify_written,
    collect_files_generator
)

logger = logging.getLogger(__name__)

# ---------- CLI & Main ----------
def validate_args(args: argparse.Namespace) -> None:
    """Validate command line arguments comprehensively."""
    errors = []
    
    # Validate mode and required parameters
    if args.mode in ('find-replace', 'append', 'prefix', 'enlist', 'set', 'clear', 'delete', 'delist', 'purge'):
        if args.mode == 'find-replace' and (args.find is None or args.replace is None):
            errors.append("find-replace mode requires --find and --replace")
        if args.mode in ('append', 'prefix', 'enlist', 'delist') and args.value is None:
            errors.append(f"{args.mode} mode requires --value")
        if args.mode == 'set':
            has_numeric_target = any([args.date, args.track, args.total_tracks, args.disc, args.total_discs])
            has_field_val_target = (args.fields or args.standard_fields or args.all_fields) and args.value
            if not (has_numeric_target or has_field_val_target):
                errors.append("set mode requires at least one field to set (--date, --track, etc.) or a target fields argument (--fields/--standard-fields/--all-fields) combined with --value")
        if args.mode in ('find-replace', 'append', 'prefix', 'enlist', 'delist', 'clear', 'delete') and not (args.fields or args.standard_fields or args.all_fields):
            errors.append(f"{args.mode} mode requires --fields, --standard-fields, or --all-fields")
    
    # Validate path
    if not os.path.exists(args.path):
        errors.append(f"Path does not exist: {args.path}")
    elif not os.access(args.path, os.R_OK):
        errors.append(f"No read permission for path: {args.path}")
    
    # Validate backup directory if provided
    if args.backup:
        backup_path = Path(args.backup)
        try:
            backup_path.mkdir(parents=True, exist_ok=True)
            if not os.access(args.backup, os.W_OK):
                errors.append(f"No write permission for backup directory: {args.backup}")
        except Exception as e:
            errors.append(f"Invalid backup directory: {e}")
    
    # Validate thread count
    if args.threads is not None and args.threads < 1:
        errors.append("--threads must be at least 1")
    
    if errors:
        raise ValueError("; ".join(errors))

def main() -> None:
    """Main CLI entry point."""
    register_signal_handlers()
    try:
        parser = argparse.ArgumentParser(description="mudio - Audio metadata multi-tool")
        
        # Core arguments
        parser.add_argument("path", nargs='?', default='.', help="Directory or file to process")
        parser.add_argument("--mode", choices=['find-replace','append','prefix','enlist','delist','set','clear','delete','purge','print'], 
                        required=False, help="Operation mode (use 'set' for metadata assignment, 'clear' to empty, 'delete' to remove)")
        
        # Threading and performance
        parser.add_argument(
            "--threads", 
            type=int, 
            default=None,
            help="Number of threads for parallel processing (default: auto)"
        )
        parser.add_argument(
            "--no-parallel", 
            action='store_true',
            help="Disable parallel processing (force sequential)"
        )
        
        # Field operations
        parser.add_argument("--fields", help="Comma-separated fields")
        parser.add_argument("--standard-fields", action='store_true', help="Target all standard fields")
        parser.add_argument("--all-fields", action='store_true', help="Target all available fields (including custom)")
        
        parser.add_argument("--find", help="Find string or pattern (for find-replace)")
        parser.add_argument("--replace", help="Replacement string (for find-replace)")
        parser.add_argument("--value", help="Value for set/append/prefix/add operations")
        parser.add_argument("--regex", action='store_true', help="Treat 'find' as regex")
        parser.add_argument("--delimiter", default=";", help="Delimiter for splitting multi-value fields (default: ';')")
        
        # File selection
        parser.add_argument("--recursive", action='store_true', help="Recurse into subdirectories")
        parser.add_argument("--ext", default=None, help="Comma-separated extensions to include")
        
        # Safety and output
        parser.add_argument("--dry-run", action='store_true', help="Do not write files")
        parser.add_argument("--backup", help="Backup directory for modified files")
        parser.add_argument("--json-report", help="Write JSON report to file")
        parser.add_argument("--force", action='store_true', help="Force operations (overwrite existing files)")
        parser.add_argument("--delete-backups", action='store_true', help="Remove backup files after successful operation (default: keep backups)")
        
        # Filtering
        parser.add_argument("--filter", action='append', help="Filter expression FIELD=PATTERN")
        parser.add_argument("--filter-regex", action='store_true', help="Use regex for filters")
        
        # Testing
        parser.add_argument("--run-tests", action='store_true', help="Run test suite")
        parser.add_argument("--test-dir", help="Test directory location")
        
        # Numeric fields
        parser.add_argument("--date", help="Set date field")
        parser.add_argument("--track", help="Set track number")
        parser.add_argument("--total-tracks", help="Set total tracks")
        parser.add_argument("--disc", help="Set disc number")
        parser.add_argument("--total-discs", help="Set total discs")
        
        # Logging
        parser.add_argument("--verbose", action='store_true', help="Enable verbose logging")
        
        # Print mode options
        # --all-fields is now general, but we keep the logic for print mode separate
        parser.add_argument("--raw-fields", action='store_true', help="Print raw tag keys")
        
        args = parser.parse_args()
        
        # Setup logging
        setup_logging(args.verbose)
        
        # Validate configuration
        try:
            Config.load_from_env()
            Config.validate()
        except ValueError as e:
            logger.error(f"Configuration validation failed: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(EXIT_CODE_USAGE)
        
        # Validate arguments
        try:
            validate_args(args)
        except ValueError as e:
            logger.error(f"Argument validation failed: {e}")
            print(f"Error: {e}", file=sys.stderr)
            if "permission" in str(e).lower():
                sys.exit(EXIT_CODE_PERMISSION)
            sys.exit(EXIT_CODE_USAGE)
        
        # Handle test mode
        if args.run_tests:
            # Import here to avoid circular dependencies if any, and because it's rarely used
            from .tests_integration import run_tests_on_dir, handle_test_mode_output
            handle_test_mode_output(args)
            return
        
        # Build operations from arguments
        ops, targeted_fields, dynamic_op = build_operations_from_args(args)
        if not ops and not dynamic_op and args.mode != 'print':
            print("No operations defined. Use --mode or --run-tests.", file=sys.stderr)
            sys.exit(EXIT_CODE_USAGE)
        
        # Parse filters
        filters = parse_filters(args)
        
        # Process files
        try:
            exit_code = run_processing_session(args, ops, targeted_fields, filters, dynamic_op)
            sys.exit(exit_code)
        except KeyboardInterrupt:
            sys.exit(EXIT_CODE_INTERRUPTED)
        except PermissionError as e:
            print(f"Permission denied: {e}", file=sys.stderr)
            sys.exit(EXIT_CODE_PERMISSION)
        except OSError as e:
            if e.errno == 28: # ENOSPC: No space left on device
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(EXIT_CODE_DISK_FULL)
            # Re-raise other OSErrors
            raise e
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            print(f"Unexpected error: {e}", file=sys.stderr)
            sys.exit(EXIT_CODE_ERROR)

    finally:
        # Ensure signal handlers are unregistered on exit
        unregister_signal_handlers()

def build_operations_from_args(args: argparse.Namespace) -> Tuple[FieldOperationsType, List[str], Optional[Callable[[str], Any]]]:
    """Build operations from command line arguments."""
    dynamic_op_factory = None
    targeted_fields = []
    ops = {}
    
    if args.mode == 'purge':
        targeted_fields = CANONICAL_FIELDS.copy()
        ops = {f: op_clear(f) for f in targeted_fields}
        return ops, targeted_fields, None
    
    if args.mode == 'print':
        # Print mode logic handled separately in main/print_file_result
        return {}, [], None
    
    # helper to get delimiter
    delimiter = getattr(args, 'delimiter', ';')
    
    # 1. Handle targeted specific fields (--fields)
    if args.fields:
        requested = parse_field_list(args.fields)
        targeted_fields.extend(requested)
    
    # 2. Handle standard fields (--standard-fields)
    if getattr(args, 'standard_fields', False):
        targeted_fields.extend(CANONICAL_FIELDS)
        
    targeted_fields = list(set(targeted_fields)) # Deduplicate
    
    # 3. Create operations for explicitly targeted fields
    if args.mode == 'set':
        # Numeric fields handling
        numeric_fields = {
            'date': args.date, 'track': args.track, 'totaltracks': args.total_tracks,
            'disc': args.disc, 'totaldiscs': args.total_discs
        }
        for field, value in numeric_fields.items():
            if value is not None:
                ops[field] = op_overwrite(field, value, delimiter=delimiter)
                if field not in targeted_fields:
                    targeted_fields.append(field)

        # Apply value to other targeted fields in set mode
        if args.value and targeted_fields:
             for field in targeted_fields:
                 if field not in ops: # Don't overwrite numeric args
                     ops[field] = op_overwrite(field, args.value, delimiter=delimiter)

    elif args.mode in ('find-replace', 'append', 'prefix', 'enlist', 'delist', 'clear', 'delete'):
        for field in targeted_fields:
            if args.mode == 'find-replace':
                ops[field] = op_find_replace(field, args.find, args.replace, regex=args.regex, delimiter=delimiter)
            # overwrite mode removed, functionality merged into set
            elif args.mode == 'append':
                ops[field] = op_append(field, args.value, delimiter=delimiter)
            elif args.mode == 'prefix':
                ops[field] = op_prefix(field, args.value)
            elif args.mode == 'enlist':
                ops[field] = op_enlist(field, args.value, delimiter=delimiter)
            elif args.mode == 'delist':
                ops[field] = op_delist(field, args.value, delimiter=delimiter)
            elif args.mode == 'clear':
                ops[field] = op_clear(field)
            elif args.mode == 'delete':
                ops[field] = op_delete(field)

    # 4. Handle dynamic operations (--all-fields)
    if getattr(args, 'all_fields', False):
        if args.mode == 'find-replace':
            dynamic_op_factory = lambda f: op_find_replace(f, args.find, args.replace, regex=args.regex, delimiter=delimiter)
        # overwrite mode removed
        elif args.mode in ('set', 'append') and args.value:
             dynamic_op_factory = lambda f: op_overwrite(f, args.value, delimiter=delimiter) if args.mode == 'set' else op_append(f, args.value, delimiter=delimiter)
        elif args.mode == 'append':
             dynamic_op_factory = lambda f: op_append(f, args.value, delimiter=delimiter)
        elif args.mode == 'prefix':
            dynamic_op_factory = lambda f: op_prefix(f, args.value)
        elif args.mode == 'enlist':
            dynamic_op_factory = lambda f: op_enlist(f, args.value, delimiter=delimiter)
        elif args.mode == 'delist':
            dynamic_op_factory = lambda f: op_delist(f, args.value, delimiter=delimiter)
        elif args.mode == 'clear':
            dynamic_op_factory = lambda f: op_clear(f)
        elif args.mode == 'delete':
            dynamic_op_factory = lambda f: op_delete(f)
            
    return ops, targeted_fields, dynamic_op_factory

def parse_field_list(fields_str: str) -> List[str]:
    """Parse comma-separated field list and normalize to canonical names."""
    # Mapping for kebab-case to snake_case/canonical
    normalization = {
        'album-artist': 'albumartist',
        'total-tracks': 'totaltracks',
        'total-discs': 'totaldiscs',
        'album_artist': 'albumartist',
        'total_tracks': 'totaltracks',
        'total_discs': 'totaldiscs'
    }
    
    fields = [f.strip().lower() for f in fields_str.split(',')]
    return [normalization.get(f, f) for f in fields]

def parse_filters(args: argparse.Namespace) -> List[FilterType]:
    """Parse filter expressions."""
    filters = []
    if args.filter:
        for filter_expr in args.filter:
            try:
                field, pattern = parse_filter_expression(filter_expr)
                filters.append((field, pattern, args.filter_regex))
            except ValueError as e:
                print(f"Invalid filter: {e}", file=sys.stderr)
                sys.exit(EXIT_CODE_USAGE)
    return filters

def parse_filter_expression(expr: str) -> Tuple[str, str]:
    """Parse a single filter expression."""
    if not expr or '=' not in expr:
        raise ValueError("filter must be FIELD=PATTERN and cannot be empty")
    
    parts = expr.split('=', 1)
    if len(parts) != 2:
        raise ValueError("filter must be FIELD=PATTERN with exactly one '='")
    
    field, pattern = parts
    field = field.strip().lower()
    pattern = pattern.strip()
    
    if not field:
        raise ValueError("filter field cannot be empty")
    if not pattern:
        raise ValueError("filter pattern cannot be empty")
    
    # Handle plural fields
    if field in ('artists', 'albumartists'):
        field = field[:-1]
    elif field.endswith('s') and field[:-1] in ('artist', 'albumartist'):
        field = field[:-1]
    
    valid_fields = ('title', 'artist', 'artists', 'album', 'albumartist', 
                   'albumartists', 'genre', 'comment', 'composer', 'performer')
    
    if field not in valid_fields:
        raise ValueError(f"invalid filter field: {field}. Must be one of: {', '.join(valid_fields)}")
    
    return field, pattern

def run_processing_session(args: argparse.Namespace, ops: FieldOperationsType, 
                          targeted_fields: List[str], filters: List[FilterType],
                          dynamic_op: Optional[Callable[[str], Any]] = None) -> int:
    """Process files using the parallel processor. Returns exit code."""
    # Build extension set
    ext_set = None
    if args.ext:
        ext_set = set(
            e.strip().lower() if e.strip().startswith('.') else '.' + e.strip().lower() 
            for e in args.ext.split(',')
        )
    
    # Collect files
    files = list(collect_files_generator(Path(args.path), recursive=args.recursive, ext_set=ext_set))
    
    if not files:
        print("No files found matching criteria.")
        return EXIT_CODE_NO_FILES
    
    print(f"Processing {len(files)} file(s)...", flush=True)
    
    # Process files using the parallel dispatcher
    results = process_files(
        files,
        ops,
        targeted_fields,
        max_workers=args.threads,
        use_parallel=not args.no_parallel,
        filters=filters,
        dry_run=args.dry_run,
        backup_dir=args.backup,
        delete_backups=args.delete_backups,
        force=args.force,
        verbose=args.verbose,
        dynamic_op=dynamic_op
    )
    
    per_ext = defaultdict(list)
    for rec in results:
        per_ext[rec.get('ext', '')].append(rec.get('passed', False))
        
        # Show details for small batches or verbose mode
        if len(files) <= 10 or args.verbose:
            print_file_result(rec, args)
    
    # Generate summary and return exit code
    return generate_summary(results, per_ext, args)

def print_file_result(rec: ProcessResultType, args: argparse.Namespace) -> None:
    """Print detailed result for a single file."""
    print(f"\nFile: {rec['path']}")
    
    if rec.get('skipped'):
        print(f"  SKIPPED: {rec.get('reason')}")
        return
        
    if rec.get('error'):
        print(f"  ERROR: {rec.get('error')}")
        return
    
    orig = rec.get('original', {})
    planned = rec.get('planned', {})
    
    # Reread if raw or all fields requested for print mode
    if args.mode == 'print':
        mode = 'canonical'
        if args.raw_fields:
            mode = 'raw'
        elif args.all_fields:
            mode = 'extended'
            
        if mode != 'canonical':
            try:
                with managed_simple_music(Path(rec['path'])) as sm:
                    orig = sm.read_fields(mode=mode)
            except Exception:
                pass # Fallback to cached original
            
    print("  Original:")
    print_metadata(orig, all_fields=args.all_fields, raw_fields=args.raw_fields)
    
    if args.dry_run:
        print("  Dry-run: planned result:")
        print_metadata(planned)
        return
        
    if rec.get('wrote'):
        verified = rec.get('verified', {})
        ok = all(verified.values()) if verified else False
        
        if ok:
            print("  Modification: SUCCESS (verified)")
        else:
            failed = [k for k, v in verified.items() if not v]
            print(f"  Modification: FAILED verification for: {', '.join(failed)}")
        
        # Show final metadata
        try:
            mode = 'canonical'
            if args.raw_fields:
                mode = 'raw'
            elif args.all_fields:
                mode = 'extended'
                
            with managed_simple_music(Path(rec['path'])) as sm:
                final_fields = sm.read_fields(mode=mode)
            print("  Final metadata:")
            print_metadata(final_fields, all_fields=args.all_fields, raw_fields=args.raw_fields)
        except Exception as e:
            print(f"  Could not read final metadata: {e}")
    else:
        print(f"  Note: {rec.get('note', 'NOT WRITTEN')}")

def print_metadata(metadata: FieldValuesType, max_len: int = 150, all_fields: bool = False, raw_fields: bool = False) -> None:
    """
    Print metadata in a consistent format with truncation.
    
    Args:
        metadata: Dictionary of field values.
        max_len: Maximum length for displayed values before truncation.
        all_fields: If True, print all fields in the metadata dict.
        raw_fields: If True, keys are printed as-is (implies all_fields behavior).
    """
    
    def format_val(val_list: List[str]) -> str:
        s = join_for_printing(val_list)
        if len(s) > max_len:
            return s[:max_len-3] + "..."
        return s

    if raw_fields or all_fields:
        # Map of key -> Display Name (from canonical list below)
        display_map = {
            'title': 'Title', 'artist': 'Artist', 'album': 'Album',
            'albumartist': 'Album Artist', 'genre': 'Genre', 'comment': 'Comment',
            'composer': 'Composer', 'performer': 'Performer', 'date': 'Date',
            'track': 'Track', 'totaltracks': 'Total Tracks',
            'disc': 'Disc', 'totaldiscs': 'Total Discs'
        }
        
        # Print all keys sorted
        for key in sorted(metadata.keys()):
            display_key = key
            # Only use nice names if NOT raw mode
            if not raw_fields and key in display_map:
                display_key = display_map[key]
            
            values = metadata[key]
            print(f"    {display_key}: {format_val(values)}")
        return

    fields = [
        ('Title', 'title'),
        ('Artists', 'artist'),
        ('Album', 'album'),
        ('AlbumArtists', 'albumartist'),
        ('Genres', 'genre'),
        ('Comment', 'comment'),
        ('Composer', 'composer'),
        ('Performer', 'performer'),
        ('Date', 'date')
    ]
    
    def format_val(val_list: List[str]) -> str:
        s = join_for_printing(val_list)
        if len(s) > max_len:
            return s[:max_len-3] + "..."
        return s
    
    for display_name, field_name in fields:
        values = metadata.get(field_name, [])
        print(f"    {display_name}: {format_val(values)}")
    
    # Track/Disc info usually short enough, but we format anyway
    track_info = f"{join_for_printing(metadata.get('track', []))}/{join_for_printing(metadata.get('totaltracks', []))}"
    disc_info = f"{join_for_printing(metadata.get('disc', []))}/{join_for_printing(metadata.get('totaldiscs', []))}"
    
    print(f"    Track/TotalTracks: {track_info}")
    print(f"    Disc/TotalDiscs: {disc_info}")

def generate_summary(results: List[ProcessResultType], per_ext: Dict[str, List[bool]], args: argparse.Namespace) -> int:
    """Generate and print processing summary. Returns exit code."""
    total_files = len(results)
    successful = sum(1 for r in results if r.get('passed', False))
    failed = total_files - successful
    
    print(f"\n--- SUMMARY ---")
    print(f"Total files processed: {total_files}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    # Per-extension summary
    if per_ext:
        print("\nPer extension results:")
        for ext, results_list in sorted(per_ext.items()):
            passed_count = sum(1 for r in results_list if r)
            total_count = len(results_list)
            status = "ALL PASSED" if passed_count == total_count else f"{passed_count}/{total_count} passed"
            print(f"  {ext or 'no ext'}: {status}")
    
    # Save JSON report
    if args.json_report:
        save_json_report(results, args.json_report)

    # Check for critical errors in results
    for r in results:
        exc = r.get('exception')
        if exc and isinstance(exc, OSError) and exc.errno == 28: # ENOSPC
            return EXIT_CODE_DISK_FULL
            
    return EXIT_CODE_SUCCESS

def save_json_report(data: Any, report_path: str) -> None:
    """Save data as JSON report."""
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        print(f"JSON report written to {report_path}")
    except Exception as e:
        print(f"Failed to write JSON report: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()