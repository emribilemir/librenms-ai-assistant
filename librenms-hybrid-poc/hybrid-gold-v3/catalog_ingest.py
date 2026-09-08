#!/usr/bin/env python3
"""Evaluation-bundle compatibility import for the runtime catalog helper."""

import sys
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parent.parent
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from catalog_ingest import *  # noqa: F401,F403,E402
