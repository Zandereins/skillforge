#!/usr/bin/env python3
"""CLI entry point — delegates to meta_report.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from meta_report import main
if __name__ == "__main__":
    main()
