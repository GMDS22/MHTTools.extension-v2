# -*- coding: utf-8 -*-
"""Entry point for synchronous Quick Fire Damper Placement."""

import os
import sys

from pyrevit import script

TOOL_DIR = os.path.dirname(__file__)
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from quick_fire_damper_command import run

run()
script.exit()
