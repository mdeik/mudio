
import pytest
import sys
from unittest.mock import patch, MagicMock
from mudio.cli import main
from mudio.utils import EXIT_CODE_USAGE, EXIT_CODE_PERMISSION, EXIT_CODE_INTERRUPTED, EXIT_CODE_ERROR, EXIT_CODE_NO_FILES, EXIT_CODE_DISK_FULL

class TestExitCodes:
    """Test exit codes for various scenarios."""

    def test_no_args_exit_code(self):
        """Test strict no-args exit code (should be usage error)."""
        # If no args provided, mudio defaults to path='.', requiring mode.
        with patch.object(sys, 'argv', ['mudio']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_USAGE

    def test_invalid_args_exit_code(self):
        """Test invalid arguments exit code."""
        # Find-replace without --find/--replace
        args = ['mudio', '.', '--operation', 'find-replace', '--fields', 'title']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_USAGE

    def test_invalid_filter_exit_code(self):
        """Test invalid filter syntax exit code."""
        args = ['mudio', '.', '--operation', 'print', '--filter', 'badfilter']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_USAGE

    @patch('mudio.cli.run_processing_session')
    def test_interrupt_exit_code(self, mock_run):
        """Test KeyboardInterrupt handling."""
        mock_run.side_effect = KeyboardInterrupt
        args = ['mudio', '.', '--operation', 'print']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_INTERRUPTED
            
    def test_permission_error_exit_code(self):
        """Test PermissionError during argument validation."""
        # We simulate this by mocking os.access to return False for the path
        with patch('os.access', return_value=False):
            # Also patch os.path.exists to return True so we hit the permission check
            with patch('os.path.exists', return_value=True):
                args = ['mudio', '/protected/path', '--operation', 'print']
                with patch.object(sys, 'argv', args):
                    with pytest.raises(SystemExit) as exc:
                        main()
                    assert exc.value.code == EXIT_CODE_PERMISSION

    @patch('mudio.cli.run_processing_session')
    def test_generic_exception_exit_code(self, mock_run):
        """Test unhandled exception exit code."""
        mock_run.side_effect = Exception("Unexpected crash")
        args = ['mudio', '.', '--operation', 'print']
        with patch.object(sys, 'argv', args):
             with pytest.raises(SystemExit) as exc:
                main()
             assert exc.value.code == EXIT_CODE_ERROR

    @patch('mudio.cli.collect_files_generator')
    def test_no_files_exit_code(self, mock_collect):
        """Test no files found exit code."""
        # Mock collecting no files
        mock_collect.return_value = iter([])
        args = ['mudio', '.', '--operation', 'print']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 3 # EXIT_CODE_NO_FILES

    @patch('mudio.cli.run_processing_session')
    def test_disk_full_exception_exit_code(self, mock_run):
        """Test OSError(ENOSPC) caught in main."""
        # Simulate disk full error raised directly
        import errno
        os_err = OSError(errno.ENOSPC, "No space left on device")
        mock_run.side_effect = os_err
        
        args = ['mudio', '.', '--operation', 'write', '--fields', 'artist', '--value', 'New Artist']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 5 # EXIT_CODE_DISK_FULL

    @patch('mudio.cli.collect_files_generator')
    @patch('mudio.cli.process_files')
    def test_disk_full_result_exit_code(self, mock_process, mock_collect):
        """Test disk full error reported in process results."""
        import errno
        # Mock finding files
        mock_collect.return_value = iter([1]) # dummy
        
        # Mock result with ENOSPC exception
        os_err = OSError(errno.ENOSPC, "No space")
        mock_process.return_value = [{
            'path': 'dummy.mp3',
            'passed': False,
            'exception': os_err
        }]
        
        args = ['mudio', '.', '--operation', 'print']
        with patch.object(sys, 'argv', args):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == EXIT_CODE_DISK_FULL
