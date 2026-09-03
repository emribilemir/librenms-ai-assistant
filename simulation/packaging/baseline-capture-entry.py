#!/usr/bin/python3
import sys

sys.path.insert(0, "/opt/librenms-ai-lab/runner")

from simulation.runner.local_admin import capture_baseline

capture_baseline()
