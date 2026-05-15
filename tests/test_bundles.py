"""Tests for bundle files in bundles/ — structure and composition validation."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).parent.parent
_BUNDLES_DIR = _REPO_ROOT / "bundles"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(path: Path) -> dict:
    """Extract and parse YAML frontmatter between --- markers."""
    content = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def _tool_modules(fm: dict) -> list[str]:
    return [t.get("module", "") for t in (fm.get("tools") or [])]


def _include_bundles(fm: dict) -> list[str]:
    return [i.get("bundle", "") for i in (fm.get("includes") or [])]


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_triage_safe_bundle_exists():
    """bundles/triage-safe.bundle.md must exist."""
    assert (_BUNDLES_DIR / "triage-safe.bundle.md").exists()


def test_triage_repro_bundle_exists():
    """bundles/triage-repro.bundle.md must exist."""
    assert (_BUNDLES_DIR / "triage-repro.bundle.md").exists()


def test_triage_amplifier_bundle_exists():
    """bundles/triage-amplifier.bundle.md must exist."""
    assert (_BUNDLES_DIR / "triage-amplifier.bundle.md").exists()


# ---------------------------------------------------------------------------
# triage-safe: includes foundation, local tools, no fat overrides
# ---------------------------------------------------------------------------


def test_triage_safe_includes_foundation():
    """triage-safe.bundle.md must include amplifier-foundation."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-safe.bundle.md")
    includes = _include_bundles(fm)
    assert any("amplifier-foundation" in inc for inc in includes), (
        "triage-safe must include amplifier-foundation"
    )


def test_triage_safe_has_all_three_github_tools():
    """triage-safe.bundle.md must declare the three local GitHub tools."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-safe.bundle.md")
    modules = _tool_modules(fm)
    assert "tool-github-post-comment" in modules
    assert "tool-github-add-label" in modules
    assert "tool-github-checkout-repo" in modules


def test_triage_safe_no_launch_dtu():
    """triage-safe.bundle.md must NOT declare tool-launch-dtu."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-safe.bundle.md")
    modules = _tool_modules(fm)
    assert "tool-launch-dtu" not in modules


def test_triage_safe_github_tools_have_local_sources():
    """Each GitHub tool in triage-safe must have a local source: path."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-safe.bundle.md")
    tools = {t.get("module", ""): t for t in (fm.get("tools") or [])}
    for name in [
        "tool-github-post-comment",
        "tool-github-add-label",
        "tool-github-checkout-repo",
    ]:
        assert "source" in tools.get(name, {}), f"{name} must have a local source: path"


def test_triage_safe_github_tool_sources_reference_local_paths():
    """GitHub tool source paths must reference the local amplifier_app_actions/tools/ directory."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-safe.bundle.md")
    tools_by_module = {t.get("module", ""): t for t in (fm.get("tools") or [])}
    for name, tool_short in [
        ("tool-github-post-comment", "github_post_comment"),
        ("tool-github-add-label", "github_add_label"),
        ("tool-github-checkout-repo", "github_checkout_repo"),
    ]:
        source = tools_by_module.get(name, {}).get("source", "")
        assert tool_short in source, (
            f"{name} source {source!r} must reference {tool_short}"
        )


def test_triage_safe_no_session_override():
    """triage-safe.bundle.md must NOT declare a session: block (fat bundle anti-pattern)."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-safe.bundle.md")
    assert "session" not in fm, (
        "triage-safe must not override session (use foundation defaults)"
    )


def test_triage_safe_no_providers_override():
    """triage-safe.bundle.md must NOT declare a providers: block (fat bundle anti-pattern)."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-safe.bundle.md")
    assert "providers" not in fm, (
        "triage-safe must not override providers (use foundation defaults)"
    )


# ---------------------------------------------------------------------------
# triage-repro: includes triage-safe + digital-twin-universe
# ---------------------------------------------------------------------------


def test_triage_repro_includes_triage_safe():
    """triage-repro.bundle.md must include the triage-safe bundle."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-repro.bundle.md")
    includes = _include_bundles(fm)
    assert any("triage-safe" in inc for inc in includes), (
        "triage-repro must include triage-safe"
    )


def test_triage_repro_includes_digital_twin_universe():
    """triage-repro.bundle.md must include amplifier-bundle-digital-twin-universe."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-repro.bundle.md")
    includes = _include_bundles(fm)
    assert any("digital-twin-universe" in inc for inc in includes), (
        "triage-repro must include digital-twin-universe"
    )


def test_triage_repro_no_launch_dtu():
    """triage-repro.bundle.md must NOT declare tool-launch-dtu."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-repro.bundle.md")
    modules = _tool_modules(fm)
    assert "tool-launch-dtu" not in modules


def test_triage_repro_no_session_override():
    """triage-repro.bundle.md must NOT declare a session: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-repro.bundle.md")
    assert "session" not in fm


def test_triage_repro_no_providers_override():
    """triage-repro.bundle.md must NOT declare a providers: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-repro.bundle.md")
    assert "providers" not in fm


# ---------------------------------------------------------------------------
# triage-amplifier: includes triage-repro
# ---------------------------------------------------------------------------


def test_triage_amplifier_includes_triage_repro():
    """triage-amplifier.bundle.md must include the triage-repro bundle."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-amplifier.bundle.md")
    includes = _include_bundles(fm)
    assert any("triage-repro" in inc for inc in includes), (
        "triage-amplifier must include triage-repro"
    )


def test_triage_amplifier_no_launch_dtu():
    """triage-amplifier.bundle.md must NOT declare tool-launch-dtu."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-amplifier.bundle.md")
    modules = _tool_modules(fm)
    assert "tool-launch-dtu" not in modules


def test_triage_amplifier_no_session_override():
    """triage-amplifier.bundle.md must NOT declare a session: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-amplifier.bundle.md")
    assert "session" not in fm


def test_triage_amplifier_no_providers_override():
    """triage-amplifier.bundle.md must NOT declare a providers: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "triage-amplifier.bundle.md")
    assert "providers" not in fm
