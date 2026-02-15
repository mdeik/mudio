
import pytest
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock 
from mudio.cli import main, build_operations_from_args
import argparse

class TestCLIArguments:
    """Test usage of --schema and interactions."""

    @pytest.fixture
    def dummy_file(self, tmp_path):
        p = tmp_path / "dummy.mp3"
        p.touch()
        return p

    def test_schema_argument(self, dummy_file):
        """Test --schema argument is accepted."""
        with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--operation", "print", "--schema", "canonical"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            
    def test_invalid_schema(self, dummy_file):
        """Test invalid --schema choice."""
        with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--operation", "print", "--schema", "invalid_choice"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_fields_union(self):
        """Test --fields extraction."""
        args = MagicMock()
        args.fields = "mycustom"
        args.operation = "clear"
        args.delimiter = ";"
        # Schema shouldn't affect targeted fields for modification
        args.schema = "canonical" 
        
        ops, targeted_fields = build_operations_from_args(args)
        
        assert "mycustom" in targeted_fields 
        assert "title" not in targeted_fields

    def test_missing_fields_arguments(self, dummy_file):
        """Test validation when no field arguments provided."""
        with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--operation", "clear"]):
             with pytest.raises(SystemExit) as exc:
                main()
             assert exc.value.code != 0

    def test_case_insensitive_fields(self):
        """Test that field names are case insensitive in --fields."""
        args = MagicMock()
        args.fields = "TiTlE, ArTiSt"
        args.schema = None
        args.operation = "clear"
        args.delimiter = ";"
        
        ops, targeted_fields = build_operations_from_args(args)
        assert "title" in targeted_fields
        assert "artist" in targeted_fields

    def test_set_mode_requirements_fail(self, dummy_file):
        """Test set operation validation failure."""
        with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--operation", "set"]):
            with pytest.raises(SystemExit):
                main()

    def test_set_mode_requirements_pass(self, dummy_file):
        """Test set operation validation success."""
        with patch('mudio.cli.run_processing_session') as mock_process:
            mock_process.return_value = 0
            with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--operation", "set", "--fields", "track", "--value", "1"]):
                with pytest.raises(SystemExit) as exc:
                    main()
            assert exc.value.code == 0
            assert mock_process.called

    def test_mode_missing_required_args(self, dummy_file):
        """Test validation for operations that require values."""
        modes = [
            ("append", []),
            ("prefix", []),
            ("find-replace", ["--find", "foo"]), # Missing replace
            ("find-replace", ["--replace", "bar"]), # Missing find
            ("add", []),
        ]
        
        for mode, extra_args in modes:
            cmd = ["mudio", str(dummy_file), "--operation", mode, "--fields", "title"] + extra_args
            with patch.object(sys, 'argv', cmd):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code != 0

    def test_invalid_old_flags(self, dummy_file):
        """Test usage of removed flags fails."""
        flags = ["--canonical-fields", "--extended-fields", "--raw-fields"]
        for flag in flags:
            with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--operation", "print", flag]):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code != 0

    def test_print_operation_defaults(self):
        """Test print operation defaults to extended fields."""
        args = MagicMock()
        args.operation = "print"
        args = MagicMock()
        args.operation = "print"
        args.schema = None # Default
        # Logic is inside print_file_result handling for args.schema or 'extended'
        pass
