#!/usr/bin/env python3
"""CLI entry point — delegates to parallel_runner.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from parallel_runner import main
if __name__ == "__main__":
    main()
