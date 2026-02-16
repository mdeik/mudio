"""
Integration tests runner for mudio CLI.
"""

import argparse
import sys
import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Callable

from .core import managed_simple_music, SUPPORTED_EXT
from .processor import process_file, safe_file_copy
from .operations import (
    overwrite, 
    find_replace, 
    append, 
    clear,
    FieldOperationsType
)
from .cli import verify_written

# ---------- Test Suite ----------
def set_baseline(fpath: Path, baseline_fields: Dict[str, List[str]]) -> None:
    """Set baseline fields for a test file."""
    try:
        with managed_simple_music(fpath) as sm:
            sm.write_fields(baseline_fields)
    except Exception as e:
        raise RuntimeError(f"Failed to set baseline: {e}")

def run_single_test(file_path: Path, test_name: str, mode: str, fields_list: List[str], 
                   params: Dict[str, str], baseline_fn: Callable, check_fn: Callable, 
                   results: List[Tuple[str, bool, Optional[str]]]) -> None:
    """Run a single test case."""
    baseline = baseline_fn()
    try:
        set_baseline(file_path, baseline)
    except Exception as e:
        results.append((test_name, False, f"baseline setup failed: {e}"))
        print(f"  {test_name}: FAIL baseline", flush=True)
        return

    # Build operations
    ops, target = build_operations_for_test(mode, fields_list, params)
    if not ops:
        results.append((test_name, False, 'unknown mode'))
        print(f"  {test_name}: FAIL unknown mode", flush=True)
        return

    # Process file
    rec = process_file(str(file_path), ops, filters=None, dry_run=False, backup_dir=None)
    
    if rec.get('error'):
        results.append((test_name, False, rec['error']))
        print(f"  {test_name}: FAIL ({rec['error']})", flush=True)
        return
        
    if not rec.get('wrote'):
        results.append((test_name, False, 'not written'))
        print(f"  {test_name}: FAIL not written", flush=True)
        return

    # Verify result
    try:
        with managed_simple_music(file_path) as sm_final:
            final_fields = sm_final.read_fields()
    except Exception as e:
        results.append((test_name, False, f'readback failed: {e}'))
        print(f"  {test_name}: FAIL readback", flush=True)
        return
        
    try:
        ok = bool(check_fn(final_fields))
        results.append((test_name, ok, None if ok else f'final: {final_fields}'))
        print(f"  {test_name}: {'PASS' if ok else 'FAIL'}", flush=True)
    except Exception as e:
        results.append((test_name, False, f'check function failed: {e}'))
        print(f"  {test_name}: FAIL check function", flush=True)

def run_tests_on_dir(src_dir: str, test_dir: Optional[str] = None) -> Dict[str, Any]:
    """Run comprehensive test suite."""
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    if not test_dir:
        test_dir = Path.cwd() / f"mudio_test_{ts}"
    else:
        test_dir = Path(test_dir)
    
    print(f"Creating test directory: {test_dir}", flush=True)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect source files
    src_dir = Path(src_dir)
    files = []
    for fn in sorted(src_dir.iterdir()):
        if fn.is_file() and fn.suffix.lower() in SUPPORTED_EXT:
            dest = test_dir / fn.name
            safe_file_copy(fn, dest)
            files.append(dest)
    
    print(f"Copied {len(files)} supported file(s) to test dir.", flush=True)
    if not files:
        return {'error': 'no supported files found', 'test_dir': str(test_dir)}

    per_file_results: Dict[str, List[Tuple[str, bool, Optional[str]]]] = {}

    # Test definitions
    tests = create_test_definitions()
    
    # Run tests
    for file_path in files:
        print(f"\nPreparing file for tests: {file_path.name}", flush=True)
        per_file_results[str(file_path)] = []
        
        for test_name, mode, fields_list, params, baseline_fn, check_fn in tests:
            run_single_test(
                file_path, test_name, mode, fields_list, params, 
                baseline_fn, check_fn, per_file_results[str(file_path)]
            )

    # Finalize test state
    finalize_test_state(files, per_file_results)
    
    # Aggregate results
    per_ext_summary = aggregate_test_results(per_file_results)
    
    return {
        'test_dir': str(test_dir), 
        'per_file': per_file_results, 
        'per_ext_summary': per_ext_summary
    }

def create_test_definitions() -> List[Tuple]:
    """Create comprehensive test definitions."""
    tests = []
    
    # Overwrite all fields test
    tests.append((
        'overwrite_all', 'overwrite', 
        ['title','album','artist','albumartist','genre','comment','date','track','totaltracks','disc','totaldiscs','composer','performer'],
        {
            'value_title': 'T_OVER', 'value_album': 'A_OVER', 'value_artist': 'AR_OVER1;AR_OVER2',
            'value_albumartist': 'ALBART_OVER', 'value_genre': 'GEN_OVER1;GEN_OVER2', 
            'value_comment': 'COMMENT_OVER', 'date': '1234-56-78', 'track': '111', 
            'totaltracks': '999', 'disc': '111', 'totaldiscs': '999',
            'value_composer': 'COMP_OVER', 'value_performer': 'PERF_OVER'
        },
        lambda: {
            'title': ['B_TITLE'], 'album': ['B_ALBUM'], 'artist': ['B_ART'], 
            'albumartist': ['B_ALBART'], 'genre': ['B_GEN'], 'comment': ['C_B'],
            'date': ['2000'], 'track': ['1'], 'totaltracks': ['10'], 
            'disc': ['1'], 'totaldiscs': ['1'], 'composer': ['C1'], 'performer': ['P1']
        },
        lambda f: (
            f.get('title') == ['T_OVER'] and
            f.get('album') == ['A_OVER'] and
            set(s.lower() for s in f.get('artist', [])) == {'ar_over1', 'ar_over2'} and
            any('comment_over' in s.lower() for s in f.get('comment', []))
        )
    ))
    
    # Find and replace test
    tests.append((
        'find_replace', 'find-replace',
        ['title'],
        {'find': 'T_OVER', 'replace': 'T_REPLACED', 'regex': False},
        lambda: {'title': ['T_OVER'], 'artist': ['Artist1']},
        lambda f: f.get('title') == ['T_REPLACED']
    ))
    
    # Append test
    tests.append((
        'append', 'append',
        ['comment'],
        {'value': ' [APPENDED]'},
        lambda: {'comment': ['Original']},
        lambda f: f.get('comment') == ['Original [APPENDED]']
    ))
    
    # Clear test
    tests.append((
        'clear', 'clear',
        ['comment'],
        {},
        lambda: {'comment': ['Some comment']},
        lambda f: not f.get('comment')
    ))

    return tests

def build_operations_for_test(mode: str, fields_list: List[str], params: Dict[str, str]) -> Tuple[FieldOperationsType, List[str]]:
    """Build operations based on mode and parameters."""
    ops = []
    target = []
    
    if mode == 'overwrite':
        # Handle overwrite operations
        for field in fields_list:
            param_key = f'value_{field}' if field in ['title', 'album', 'artist', 'albumartist', 'genre', 'comment', 'composer', 'performer'] else field
            if param_key in params:
                ops.append(overwrite(field, params[param_key]))
                target.append(field)
    
    elif mode == 'find-replace':
        for field in fields_list:
            if 'find' in params and 'replace' in params:
                ops.append(find_replace(field, params['find'], params['replace'], params.get('regex', False)))
                target.append(field)
    
    elif mode == 'append':
        for field in fields_list:
            if 'value' in params:
                ops.append(append(field, params['value']))
                target.append(field)
    
    elif mode == 'clear':
        for field in fields_list:
            ops.append(clear(field))
            target.append(field)
    
    return ops, target

def finalize_test_state(files: List[Path], per_file_results: Dict[str, List[Tuple[str, bool, Optional[str]]]]) -> None:
    """Set final test state for all files."""
    print("\nFinalizing test files to 'Passed' state...", flush=True)
    for file_path in files:
        try:
            with managed_simple_music(file_path) as sm:
                final_state = {
                    'title': ['Passed'], 'album': ['Passed'], 'comment': ['Passed'],
                    'date': ['1234-56-78'], 'track': ['111'], 'totaltracks': ['999'],
                    'disc': ['111'], 'totaldiscs': ['999'], 'artist': ['Passed', 'Tests'],
                    'albumartist': ['Passed', 'Tests'], 'genre': ['Passed', 'Tests'],
                    'composer': ['Passed'], 'performer': ['Passed']
                }
                sm.write_fields(final_state)
            
            verification_fields = ['date', 'track', 'totaltracks', 'disc', 'totaldiscs', 
                                 'title', 'album', 'comment', 'artist', 'albumartist', 
                                 'genre', 'composer', 'performer']
            rec_ver = verify_written(file_path, {k: final_state[k] for k in verification_fields})
            ok = all(rec_ver.values())
            
            per_file_results[str(file_path)].append(('finalize_passed_state', ok, None if ok else f'verify failed: {rec_ver}'))
            print(f"  {file_path.name} finalize: {'PASS' if ok else 'FAIL'}", flush=True)
        except Exception as e:
            per_file_results[str(file_path)].append(('finalize_passed_state', False, str(e)))
            print(f"  {file_path.name} finalize: FAIL ({e})", flush=True)

def aggregate_test_results(per_file_results: Dict[str, List[Tuple[str, bool, Optional[str]]]]) -> Dict[str, Dict[str, int]]:
    """Aggregate test results by file extension."""
    per_ext_summary = {}
    for file_path, results in per_file_results.items():
        ext = Path(file_path).suffix.lower()
        passed = sum(1 for _, ok, _ in results if ok)
        total = len(results)
        per_ext_summary.setdefault(ext, {'files': 0, 'passed': 0, 'total': 0})
        per_ext_summary[ext]['files'] += 1
        per_ext_summary[ext]['passed'] += passed
        per_ext_summary[ext]['total'] += total
    return per_ext_summary

def handle_test_mode_output(args: argparse.Namespace) -> None:
    """Handle test mode execution."""
    from .cli import save_json_report
    
    res = run_tests_on_dir(args.path, test_dir=args.test_dir)
    td = res.get('test_dir')
    
    if 'error' in res:
        print(f"Test run failed: {res['error']}")
        if td:
            print("Test dir:", td)
        sys.exit(1)
    
    print(f"\nTests executed in: {td}\n")
    
    # Print results
    for file_path, results in sorted(res['per_file'].items()):
        filename = Path(file_path).name
        ext = Path(file_path).suffix.lower()
        passed = sum(1 for _, ok, _ in results if ok)
        total = len(results)
        
        print(f"File: {filename} ({ext})")
        for name, ok, note in results:
            status = "PASS" if ok else "FAIL"
            note_str = "" if note is None else f" - {note}"
            print(f"  {name:20s} : {status}{note_str}")
        print(f"  Result: {passed}/{total} tests passed\n")
    
    # Print summary
    print("--- Aggregated by filetype ---")
    for ext, summary in res['per_ext_summary'].items():
        files = summary['files']
        passed = summary['passed']
        total = summary['total']
        print(f"  {ext}: {files} file(s) — {passed}/{total} test checks passed")
    
    # Save JSON report if requested
    if args.json_report:
        save_json_report(res, args.json_report)
