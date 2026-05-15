"""Verify each GitHub tool is a proper Python package directory, not a flat .py file.

RED: fails while tools live in github_post_comment.py etc.
GREEN: passes once each is converted to github_post_comment/__init__.py.
"""

from __future__ import annotations

import importlib


_TOOL_MODULES = [
    "amplifier_app_actions.tools.github_post_comment",
    "amplifier_app_actions.tools.github_add_label",
    "amplifier_app_actions.tools.github_checkout_repo",
]


def test_tool_modules_are_packages():
    """Each tool module's __file__ must be an __init__.py (package), not a flat .py."""
    for mod_name in _TOOL_MODULES:
        mod = importlib.import_module(mod_name)
        assert mod.__file__ is not None, f"{mod_name} has no __file__"
        assert mod.__file__.endswith("__init__.py"), (
            f"{mod_name} is a flat module file ({mod.__file__!r}), "
            "expected a package directory with __init__.py"
        )
