#!/usr/bin/env python3
"""Evaluation-bundle compatibility import for the active runtime resolver."""

import sys
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parent.parent
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from resolver_v5 import *  # noqa: F401,F403,E402
