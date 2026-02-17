"""mudio CLI - Audio metadata tool for the command line."""
import os
import sys
import argparse
import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

from .processor import register_signal_handlers, unregister_signal_handlers

# Core imports
from .core import CANONICAL_FIELDS,managed_simple_music
from .utils import (
    Config, 
    setup_logging, 
    join_for_printing, 
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
    write,
    find_replace,
    append,
    prefix,
    prefix,
    enlist,
    delist,
    clear,
    delete
)
from .processor import (
    ProcessResultType,
    process_files,
    collect_files_generator
)

logger = logging.getLogger(__name__)

# ---------- CLI & Main ----------
def validate_args(args: argparse.Namespace) -> None:
    """Validate command line arguments comprehensively."""
    errors = []
    
    # Validate operation and required parameters
    if args.operation in ('find-replace', 'append', 'prefix', 'enlist', 'write', 'clear', 'delete', 'delist', 'purge'):
        if args.operation == 'find-replace' and (args.find is None or args.replace is None):
            errors.append("find-replace operation requires --find and --replace")
        if args.operation in ('append', 'prefix', 'enlist', 'delist') and args.value is None:
            errors.append(f"{args.operation} operation requires --value")
        if args.operation == 'write':
            if not (args.fields and args.value):
                errors.append("write operation requires --fields and --value")
        if args.operation in ('find-replace', 'append', 'prefix', 'enlist', 'delist', 'clear', 'delete') and not args.fields:
            errors.append(f"{args.operation} operation requires --fields")
    
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
        parser.add_argument("--operation", choices=['find-replace','append','prefix','enlist','delist','write','clear','delete','purge','print'], 
                        required=False, help="Operation (use 'write' for metadata assignment, 'clear' to empty, 'delete' to remove)")
        
        # Threading and performance
        parser.add_argument(
            "--threads", 
            type=int, 
            default=None,
            help="Number of threads for parallel processing (default: auto)"
        )
        
        # Field operations
        parser.add_argument("--fields", help="Comma-separated fields")

        
        parser.add_argument("--find", help="Find string or pattern (for find-replace)")
        parser.add_argument("--replace", help="Replacement string (for find-replace)")
        parser.add_argument("--value", help="Value for write/append/prefix/add operations")
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
        

        
        # Logging
        parser.add_argument("--verbose", action='store_true', default=None,
                           help="Enable verbose logging (overrides MUDIO_VERBOSE env var)")
        
        # Schema options
        parser.add_argument("--schema", choices=['canonical', 'extended', 'raw'], 
                           help="Metadata schema to use (overrides default/env var)")
        parser.add_argument("--namespace", 
                           help="Namespace for custom MP4 fields (overrides MUDIO_NAMESPACE env var)")
        
        args = parser.parse_args()
        
        # Setup logging - use env var default if flag not explicitly set
        if args.verbose is None:
            # Config hasn't loaded yet, so we check directly here
            verbose_env = os.getenv('MUDIO_VERBOSE', '').lower()
            args.verbose = verbose_env in ('1', 'true', 'yes')
        
        setup_logging(args.verbose)
        
        # Configuration precedence: CLI flag > environment variable > default
        try:
            Config.load_from_env()
            # Override namespace if provided via CLI (takes precedence over env var)
            if args.namespace:
                Config.DEFAULT_NAMESPACE = args.namespace
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
            # Import here to avoid circular dependency
            from .tests_integration import run_tests_on_dir, handle_test_mode_output
            handle_test_mode_output(args)
            return
        
        # Build operations from arguments
        ops, targeted_fields = build_operations_from_args(args)
        if not ops and args.operation != 'print':
            print("No operations defined. Use --operation or --run-tests.", file=sys.stderr)
            sys.exit(EXIT_CODE_USAGE)
        
        # Parse filters
        filters = parse_filters(args)
        
        # Process files
        try:
            exit_code = run_processing_session(args, ops, targeted_fields, filters)
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

def build_operations_from_args(args: argparse.Namespace) -> Tuple[List[FieldOperationsType], List[str]]:
    """Build operations from command line arguments."""
    targeted_fields = []
    ops = []
    
    if args.operation == 'purge':
        # Purge clears every canonical field at once (a convenience shortcut)
        targeted_fields = CANONICAL_FIELDS.copy()
        ops = [clear(f) for f in targeted_fields]
        return ops, targeted_fields
    
    if args.operation == 'print':
        # Print operation logic handled separately in main/print_file_result
        return [], []
    
    # helper to get delimiter
    delimiter = getattr(args, 'delimiter', ';')
    
    # 1. Handle targeted specific fields (--fields)
    if args.fields:
        requested = parse_field_list(args.fields)
        targeted_fields.extend(requested)
    
    # 2. Handle canonical fields via --schema (passed to processor)
        
    targeted_fields = list(set(targeted_fields)) # Deduplicate
    
    # 3. Create operations for explicitly targeted fields
    if args.operation == 'write':
        # Apply value to other targeted fields in write operation
        if args.value and targeted_fields:
             for field in targeted_fields:
                 ops.append(write(field, args.value, delimiter=delimiter))

    elif args.operation in ('find-replace', 'append', 'prefix', 'enlist', 'delist', 'clear', 'delete'):
        for field in targeted_fields:
            if args.operation == 'find-replace':
                ops.append(find_replace(field, args.find, args.replace, regex=args.regex, delimiter=delimiter))
            # Set operation
            elif args.operation == 'append':
                ops.append(append(field, args.value, delimiter=delimiter))
            elif args.operation == 'prefix':
                ops.append(prefix(field, args.value))
            elif args.operation == 'enlist':
                ops.append(enlist(field, args.value, delimiter=delimiter))
            elif args.operation == 'delist':
                ops.append(delist(field, args.value, delimiter=delimiter))
            elif args.operation == 'clear':
                ops.append(clear(field))
            elif args.operation == 'delete':
                ops.append(delete(field))

    return ops, targeted_fields

def parse_field_list(fields_str: str) -> List[str]:
    """Parse comma-separated field list and normalize to canonical names using CANON aliases."""
    from .core import canon_key
    
    fields = [f.strip() for f in fields_str.split(',') if f.strip()]
    return [canon_key(f) for f in fields]

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
    
    valid_fields = CANONICAL_FIELDS.copy()
    
    if field not in valid_fields:
        raise ValueError(f"invalid filter field: {field}. Must be one of: {', '.join(valid_fields)}")
    
    return field, pattern

def run_processing_session(args: argparse.Namespace, ops: List[FieldOperationsType], 
                          targeted_fields: List[str], filters: List[FilterType]) -> int:
    """Process files using the parallel processor. Returns exit code."""
    # Build extension set
    ext_set = None
    if args.ext:
        ext_set = set(
            e.strip().lower() if e.strip().startswith('.') else '.' + e.strip().lower() 
            for e in args.ext.split(',')
        )
    
    # Collect all matching audio files from the path (may be a single file or directory)
    files = list(collect_files_generator(Path(args.path), recursive=args.recursive, ext_set=ext_set))
    
    if not files:
        print("No files found matching criteria.")
        # Still create JSON report if requested (with empty results)
        if args.json_report:
            save_json_report([], args.json_report)
        return EXIT_CODE_NO_FILES
    
    print(f"Processing {len(files)} file(s)...", flush=True)
    
    # Hand off to the smart dispatcher (auto-selects parallel vs sequential)
    results = process_files(
        files,
        ops,
        max_workers=args.threads or 0,
        filters=filters,
        dry_run=args.dry_run,
        backup_dir=args.backup,
        delete_backups=args.delete_backups,
        force=args.force,
        verbose=args.verbose,
        read_schema=args.schema
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
    
    # Reread if schema is specified or default behavior for print
    if args.operation == 'print':
        read_schema = args.schema or 'extended' # Default for print is extended
            
        try:
            with managed_simple_music(Path(rec['path'])) as sm:
                orig = sm.read_fields(schema=read_schema)
        except Exception:
            pass # Fallback to cached original
            
    print("  Original:")
    print_metadata(orig, raw_fields=(args.schema == 'raw'))
    
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
            read_schema = args.schema or 'extended' # Default for verification read
                
            with managed_simple_music(Path(rec['path'])) as sm:
                final_fields = sm.read_fields(schema=read_schema)
            print("  Final metadata:")
            print_metadata(final_fields, raw_fields=(args.schema == 'raw'))
        except Exception as e:
            print(f"  Could not read final metadata: {e}")
    else:
        print(f"  Note: {rec.get('note', 'NOT WRITTEN')}")

def print_metadata(metadata: FieldValuesType, max_len: int = 150, raw_fields: bool = False) -> None:
    """
    Print metadata in a consistent format with truncation.
    
    Args:
        metadata: Dictionary of field values.
        max_len: Maximum length for displayed values before truncation.
        raw_fields: If True, keys are printed as-is (implies all_fields behavior).
    """
    
    def format_val(val_list: List[str]) -> str:
        """Format a value list for display, truncating if needed."""
        s = join_for_printing(val_list)
        if len(s) > max_len:
            return s[:max_len-3] + "..."
        return s

    if raw_fields:
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
        ('Artist', 'artist'),
        ('Album', 'album'),
        ('AlbumArtist', 'albumartist'),
        ('Genre', 'genre'),
        ('Comment', 'comment'),
        ('Composer', 'composer'),
        ('Performer', 'performer'),
        ('Date', 'date'),
        ('Track', 'track'),
        ('TotalTracks', 'totaltracks'),
        ('Disc', 'disc'),
        ('TotalDiscs', 'totaldiscs')
    ]
    
    # Track printed keys to avoid duplicates
    printed_keys = set()
    
    # Print canonical fields first with nice display names
    for display_name, field_name in fields:
        values = metadata.get(field_name, [])
        print(f"    {display_name}: {format_val(values)}")
        printed_keys.add(field_name)
            
    # Print any remaining (custom/extended) fields
    for key in metadata.keys():
        if key not in printed_keys:
            # Display key as is (no title casing, no sorting)
            display_key = key
            values = metadata[key]
            print(f"    {display_key}: {format_val(values)}")

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
    
    # Save JSON report (always create, even if no files)
    if args.json_report:
        save_json_report(results, args.json_report)

    # Check for critical errors in results
    for r in results:
        exc = r.get('exception')
        if exc and isinstance(exc, OSError) and exc.errno == 28: # ENOSPC
            return EXIT_CODE_DISK_FULL
            
    return EXIT_CODE_SUCCESS

def save_json_report(results: List[ProcessResultType], report_path: str) -> None:
    """Save processing results in documented JSON schema format."""
    from datetime import datetime
    
    # Calculate summary statistics
    total = len(results)
    success = sum(1 for r in results if r.get('passed', False))
    failed = sum(1 for r in results if r.get('error'))
    skipped = sum(1 for r in results if r.get('skipped'))
    
    # Count backups
    backups_created = 0
    backups_removed = 0
    for r in results:
        if r.get('backup_path'):
            backups_created += 1
            if r.get('backup_kept') == False:
                backups_removed += 1
    
    # Build schema-compliant structure
    report_data = {
        "version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "backups_created": backups_created,
            "backups_removed": backups_removed
        },
        "files": []
    }
    
    # Transform results to documented format
    for r in results:
        file_record = {
            "path": r.get('path', ''),
            "status": "skipped" if r.get('skipped') else ("error" if r.get('error') else "success")
        }
        
        # Add changes if present
        if r.get('original') and r.get('planned'):
            changes = {}
            for field in r.get('changed', {}).keys():
                if r['changed'][field]:  # Only include actually changed fields
                    changes[field] = {
                        "old": r['original'].get(field, []),
                        "new": r['planned'].get(field, [])
                    }
            if changes:
                file_record["changes"] = changes
        
        # Add error if present
        if r.get('error'):
            file_record["error"] = r['error']
        
        # Add backup info if present
        if r.get('backup_path'):
            file_record["backup_path"] = r['backup_path']
            file_record["backup_kept"] = r.get('backup_kept', True)
        
        report_data["files"].append(file_record)
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        print(f"JSON report written to {report_path}")
    except Exception as e:
        print(f"Failed to write JSON report: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()