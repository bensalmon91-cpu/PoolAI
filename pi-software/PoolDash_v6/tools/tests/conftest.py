"""Test config: make the parent tools/ directory importable as a package root.

The Pi runs tools/modbus_logger.py as a script, so the directory has no
__init__.py. For tests we want `import modbus_logger` to resolve, so add
tools/ to sys.path before pytest collects test modules.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# Also make the app root importable so tests can use pooldash_app.* modules
# (e.g. pooldash_app.db.maintenance).
_APP_ROOT = _TOOLS_DIR.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
