
import pytest
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock 
from mudio.cli import main, build_operations_from_args
import argparse

class TestCLIArguments:
    """Test usage of --standard-fields, --all-fields and interactions."""

    @pytest.fixture
    def dummy_file(self, tmp_path):
        p = tmp_path / "dummy.mp3"
        p.touch()
        return p

    def test_standard_fields_only(self, dummy_file):
        """Test --standard-fields dispatch."""
        with patch('mudio.cli.run_processing_session') as mock_process:
            mock_process.return_value = 0
            with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--mode", "clear", "--standard-fields"]):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0
            
            # Verify run_processing_session was called with targeted columns including canonical ones
            assert mock_process.called
            args, ops, targeted, filters, dynamic_op = mock_process.call_args[0]
            
            # targeted should contain standard fields
            assert "title" in targeted
            assert "artist" in targeted
            # dynamic_op should be None
            assert dynamic_op is None

    def test_all_fields_only(self, dummy_file):
        """Test --all-fields dispatch."""
        with patch('mudio.cli.run_processing_session') as mock_process:
            mock_process.return_value = 0
            with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--mode", "clear", "--all-fields"]):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0
            
            assert mock_process.called
            args, ops, targeted, filters, dynamic_op = mock_process.call_args[0]
            
            assert dynamic_op is not None

    def test_fields_union(self):
        """Test --standard-fields combined with --fields."""
        args = MagicMock()
        args.standard_fields = True
        args.fields = "mycustom"
        args.all_fields = False
        args.mode = "clear"
        args.delimiter = ";"
        
        ops, targeted_fields, dynamic_op = build_operations_from_args(args)
        
        assert "title" in targeted_fields # From standard
        assert "mycustom" in targeted_fields # From specific
        assert dynamic_op is None

    def test_all_fields_overrides_others(self):
        """Test --all-fields combined with others."""
        args = MagicMock()
        args.standard_fields = True
        args.fields = "title"
        args.all_fields = True
        args.mode = "clear"
        args.delimiter = ";"
        
        ops, targeted_fields, dynamic_op = build_operations_from_args(args)
        
        assert "title" in targeted_fields
        assert dynamic_op is not None

    def test_missing_fields_arguments(self, dummy_file):
        """Test validation when no field arguments provided."""
        with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--mode", "clear"]):
             with pytest.raises(SystemExit) as exc:
                main()
             assert exc.value.code != 0

    def test_case_insensitive_fields(self):
        """Test that field names are case insensitive in --fields."""
        args = MagicMock()
        args.fields = "TiTlE, ArTiSt"
        args.standard_fields = False
        args.all_fields = False
        args.mode = "clear"
        args.delimiter = ";"
        
        ops, targeted_fields, dynamic_op = build_operations_from_args(args)
        assert "title" in targeted_fields
        assert "artist" in targeted_fields

    def test_dynamic_op_logic(self):
        """Test that dynamic_op_factory creates correct operations."""
        args = MagicMock()
        args.all_fields = True
        args.mode = "find-replace"
        args.find = "foo"
        args.replace = "bar"
        args.regex = False
        args.delimiter = ";"
        
        ops, targeted_fields, dynamic_op = build_operations_from_args(args)
        assert dynamic_op is not None
        
        op = dynamic_op("any_field")
        assert callable(op)

    def test_set_mode_requirements_fail(self, dummy_file):
        """Test set mode validation failure."""
        with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--mode", "set"]):
            with pytest.raises(SystemExit):
                main()

    def test_set_mode_requirements_pass(self, dummy_file):
        """Test set mode validation success."""
        with patch('mudio.cli.run_processing_session') as mock_process:
            mock_process.return_value = 0
            with patch.object(sys, 'argv', ["mudio", str(dummy_file), "--mode", "set", "--track", "1"]):
                with pytest.raises(SystemExit) as exc:
                    main()
            assert exc.value.code == 0
            assert mock_process.called

    def test_mode_missing_required_args(self, dummy_file):
        """Test validation for modes that require values."""
        modes = [
            ("append", []),
            ("prefix", []),
            ("find-replace", ["--find", "foo"]), # Missing replace
            ("find-replace", ["--replace", "bar"]), # Missing find
            ("add", []),
        ]
        
        for mode, extra_args in modes:
            cmd = ["mudio", str(dummy_file), "--mode", mode, "--fields", "title"] + extra_args
            with patch.object(sys, 'argv', cmd):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code != 0

    def test_invalid_standard_fields_usage(self, dummy_file):
        """Test usage of --standard-fields in set mode (allowed but check behavior)."""
        # set mode target fields logic:
        # It adds specific numeric fields to target.
        # If --standard-fields is used, they are added to target list.
        # If --value is present, it applies to *all* target list (except numeric ones which have specific args).
        
        with patch('mudio.cli.run_processing_session') as mock_process:
            mock_process.return_value = 0
            # changing all standard fields to "test"
            cmd = ["mudio", str(dummy_file), "--mode", "set", "--standard-fields", "--value", "test"]
            with patch.object(sys, 'argv', cmd):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0
            
            assert mock_process.called
            args, ops, targeted, filters, dynamic_op = mock_process.call_args[0]
            
            # Should have expanded standard fields
            assert len(targeted) > 10 # Canonical list is ~13
            assert "title" in targeted
            assert "artist" in targeted
            
            # Check ops
            assert ops['title'] is not None
            # Check a numeric one like 'track' is incorrectly set to "test" string if not careful?
            # set mode logic:
            # if args.value and targeted_fields:
            #   for field in targeted_fields:
            #       if field not in ops: ops[field] = overwrite...
            
            assert ops['track'] is not None 
            # This is technically allowed user behavior, even if silly to set track to "test"
            # The test just confirms it works as logic dictates.
