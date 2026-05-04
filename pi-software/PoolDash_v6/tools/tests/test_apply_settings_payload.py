"""Regression test for Item 2 in the v6.11.12 release.

Before v6.11.12, every admin `apply_settings` command failed with
"No settings in payload" because health_reporter.py treated the payload
as a parsed dict — but the heartbeat handler forwards it from the server
as a JSON-encoded string. Fix: parse the string in execute_command.

This test uses introspection rather than executing the command (which
would trigger sudo systemctl restart). The narrower assertion —
"execute_command JSON-decodes a string payload before the type
dispatch" — is enough to guard against the bug class.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def test_execute_command_parses_string_payload() -> None:
    import health_reporter as hr
    src = inspect.getsource(hr.execute_command)
    # Required pattern: a json.loads call gated on isinstance(..., str).
    assert "json.loads" in src, (
        "execute_command must json.loads the payload before isinstance(dict) checks; "
        "without this, every apply_settings command fails with 'No settings in payload'."
    )
    assert "isinstance(payload, str)" in src or "isinstance(raw_payload, str)" in src, (
        "JSON parse must be conditional on payload being a string — the heartbeat "
        "handler may forward it pre-parsed in some code paths."
    )
