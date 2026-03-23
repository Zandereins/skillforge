#!/usr/bin/env python3
"""CLI entry point — delegates to episodic_store.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from episodic_store import main
if __name__ == "__main__":
    main()
