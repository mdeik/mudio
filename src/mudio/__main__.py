"""
Main entry point for running mudio as a module.
Allows: python -m mudio ...
"""
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
