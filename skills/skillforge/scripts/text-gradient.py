#!/usr/bin/env python3
"""CLI entry point — delegates to text_gradient.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from text_gradient import main
if __name__ == "__main__":
    main()
