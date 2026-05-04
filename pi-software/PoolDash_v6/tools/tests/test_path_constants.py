"""Regression tests for hardcoded paths in scripts/.

v6.11.10 and earlier had `Path("/home/poolaissistant/chunk_manager.py")` and
`Path("/home/poolaissistant/update_check.py")` in health_reporter.py. The user
poolaissistant has never existed on production installs (the actual user is
`poolai`), so every admin-triggered 'upload' or 'update' command failed with
"Chunk manager not found" / "Update script not found" silently.

These tests pin down the rule: paths used at runtime must resolve relative to
__file__, not to a hardcoded absolute under /home/.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable for tests in tools/tests/.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def test_health_reporter_chunk_manager_path_resolves() -> None:
    import health_reporter  # noqa: E402
    assert health_reporter.CHUNK_MANAGER.exists(), (
        f"CHUNK_MANAGER points to {health_reporter.CHUNK_MANAGER}, which doesn't "
        "exist. The path constant must resolve relative to __file__, not a "
        "hardcoded /home/* directory."
    )
    assert health_reporter.CHUNK_MANAGER.name == "chunk_manager.py"


def test_health_reporter_update_check_path_resolves() -> None:
    import health_reporter
    assert health_reporter.UPDATE_CHECK.exists(), (
        f"UPDATE_CHECK points to {health_reporter.UPDATE_CHECK}, which doesn't "
        "exist. Same rule as CHUNK_MANAGER — path must come from __file__."
    )
    assert health_reporter.UPDATE_CHECK.name == "update_check.py"


def test_no_hardcoded_home_poolaissistant_paths() -> None:
    """Defence-in-depth: if anyone re-introduces /home/poolaissistant in
    health_reporter, fail loudly. The user does not exist on production."""
    src = (_SCRIPTS_DIR / "health_reporter.py").read_text()
    # Allow the comment line that explains the historical bug.
    lines = [
        ln for ln in src.splitlines()
        if "/home/poolaissistant" in ln
        and not ln.lstrip().startswith("#")
    ]
    assert lines == [], (
        "Found uncommented /home/poolaissistant references in "
        f"health_reporter.py: {lines}"
    )
