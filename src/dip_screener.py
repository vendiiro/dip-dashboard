#!/usr/bin/env python3
"""Compatibility wrapper: the screener now lives in the dipdash package (src/dipdash/).

    python src/dip_screener.py --demo --out output/demo.html
    python src/dip_screener.py --out output/dashboard.html --open

Educational research tool. Not investment advice.
"""
import sys

from dipdash.cli import main

if __name__ == "__main__":
    sys.exit(main())
