"""
Tests for configuration and environment variables.
"""
import pytest
import os
from unittest.mock import patch
from mudio.utils import Config

class TestConfig:
    """Tests for Config class and environment variables."""
    
    def setup_method(self):
        """Reset config before each test."""
        self.original_verbose = Config.DEFAULT_VERBOSE
        self.original_namespace = Config.DEFAULT_NAMESPACE
        
    def teardown_method(self):
        """Restore config after each test."""
        Config.DEFAULT_VERBOSE = self.original_verbose
        Config.DEFAULT_NAMESPACE = self.original_namespace
        
        # Clean up env vars
        for var in ['MUDIO_VERBOSE', 'MUDIO_NAMESPACE', 'MUDIO_MAX_FILE_SIZE', 'MUDIO_MAX_WORKERS']:
            if var in os.environ:
                del os.environ[var]

    # --- Verbose Config Tests ---
    
    def test_default_verbose_is_false(self):
        """Test that default verbose is False when env var not set."""
        if 'MUDIO_VERBOSE' in os.environ:
            del os.environ['MUDIO_VERBOSE']
        
        Config.DEFAULT_VERBOSE = False
        Config.load_from_env()
        assert Config.DEFAULT_VERBOSE is False
    
    def test_verbose_env_var_variants(self):
        """Test various MUDIO_VERBOSE values."""
        variants = [
            ('1', True), ('true', True), ('TRUE', True), ('yes', True),
            ('0', False), ('false', False), ('no', False), ('invalid', False), ('', False)
        ]
        
        for val, expected in variants:
            os.environ['MUDIO_VERBOSE'] = val
            # Reset to ensure clean state
            Config.DEFAULT_VERBOSE = False 
            Config.load_from_env()
            assert Config.DEFAULT_VERBOSE is expected, f"Failed for value: {val}"
    
    # --- Namespace Config Tests ---
    
    def test_default_namespace(self):
        """Test default namespace."""
        Config.DEFAULT_NAMESPACE = "com.apple.iTunes" # ensure default
        Config.load_from_env()
        assert Config.DEFAULT_NAMESPACE == "com.apple.iTunes"
        
    def test_namespace_env_var(self):
        """Test MUDIO_NAMESPACE env var."""
        os.environ['MUDIO_NAMESPACE'] = "org.mudio"
        Config.load_from_env()
        assert Config.DEFAULT_NAMESPACE == "org.mudio"
        
    # --- Validation Tests ---

    def test_validate_accepts_valid(self):
        """Test that validation accepts valid values."""
        Config.DEFAULT_VERBOSE = True
        Config.validate()
        
    def test_validate_rejects_invalid_types(self):
        """Test that validation rejects non-boolean verbose."""
        Config.DEFAULT_VERBOSE = "true"
        with pytest.raises(ValueError, match="DEFAULT_VERBOSE must be a boolean"):
            Config.validate()
            
    def test_validate_rejects_invalid_values(self):
        """Test validation logic (e.g. positive workers)."""
        original = Config.MAX_WORKERS
        try:
            Config.MAX_WORKERS = -1
            with pytest.raises(ValueError, match="MAX_WORKERS must be positive"):
                Config.validate()
        finally:
            Config.MAX_WORKERS = original

    def test_from_env_overrides(self):
        """Test other env var overrides."""
        env = {
            'MUDIO_MAX_FILE_SIZE': '999',
            'MUDIO_MAX_WORKERS': '5'
        }
        original_size = Config.MAX_FILE_SIZE
        original_workers = Config.MAX_WORKERS
        
        try:
            with patch.dict(os.environ, env):
                Config.load_from_env()
                assert Config.MAX_FILE_SIZE == 999
                assert Config.MAX_WORKERS == 5
        finally:
            Config.MAX_FILE_SIZE = original_size
            Config.MAX_WORKERS = original_workers
