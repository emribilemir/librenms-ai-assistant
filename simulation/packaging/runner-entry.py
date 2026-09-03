#!/usr/bin/python3
import sys

sys.path.insert(0, "/opt/librenms-ai-lab/runner")

from simulation.runner.forced_command import main

raise SystemExit(main())
