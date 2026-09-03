#!/usr/bin/python3
import sys

sys.path.insert(0, "/opt/librenms-ai-lab/runner")

from simulation.runner.local_admin import reset_current, write_result

raise SystemExit(write_result(reset_current()))
