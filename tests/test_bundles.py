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


def _provider_modules(fm: dict) -> list[str]:
    return [p.get("module", "") for p in (fm.get("providers") or [])]


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_github_tools_bundle_exists():
    """bundles/github-tools.bundle.md must exist."""
    assert (_BUNDLES_DIR / "github-tools.bundle.md").exists()


def test_github_tools_dtu_bundle_exists():
    """bundles/github-tools-dtu.bundle.md must exist."""
    assert (_BUNDLES_DIR / "github-tools-dtu.bundle.md").exists()


def test_github_tools_amplifier_dev_bundle_exists():
    """bundles/github-tools-amplifier-dev.bundle.md must exist."""
    assert (_BUNDLES_DIR / "github-tools-amplifier-dev.bundle.md").exists()


# ---------------------------------------------------------------------------
# github-tools: base tier — includes foundation, local tools, explicit provider
# ---------------------------------------------------------------------------


def test_github_tools_includes_foundation():
    """github-tools.bundle.md must include amplifier-foundation."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools.bundle.md")
    includes = _include_bundles(fm)
    assert any("amplifier-foundation" in inc for inc in includes), (
        "github-tools must include amplifier-foundation"
    )


def test_github_tools_has_all_three_github_tools():
    """github-tools.bundle.md must declare the three local GitHub tools."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools.bundle.md")
    modules = _tool_modules(fm)
    assert "tool-github-post-comment" in modules
    assert "tool-github-add-label" in modules
    assert "tool-github-checkout-repo" in modules


def test_github_tools_use_entry_points():
    """GitHub tools in github-tools must NOT have a source: path (they use entry points)."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools.bundle.md")
    tools = {t.get("module", ""): t for t in (fm.get("tools") or [])}
    for name in [
        "tool-github-post-comment",
        "tool-github-add-label",
        "tool-github-checkout-repo",
    ]:
        assert "source" not in tools.get(name, {}), (
            f"{name} must not have a source: path — registered via pyproject.toml entry points"
        )


def test_github_tools_no_session_override():
    """github-tools.bundle.md must NOT declare a session: block (fat bundle anti-pattern)."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools.bundle.md")
    assert "session" not in fm, (
        "github-tools must not override session (use foundation defaults)"
    )


def test_github_tools_has_explicit_provider():
    """github-tools.bundle.md must declare provider-anthropic for in-process session creation."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools.bundle.md")
    providers = _provider_modules(fm)
    assert "provider-anthropic" in providers, (
        "github-tools must declare provider-anthropic "
        "(required for in-process session creation via _create_session)"
    )


# ---------------------------------------------------------------------------
# github-tools-dtu: extends github-tools with Digital Twin Universe
# ---------------------------------------------------------------------------


def test_github_tools_dtu_includes_github_tools():
    """github-tools-dtu.bundle.md must include the github-tools bundle."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-dtu.bundle.md")
    includes = _include_bundles(fm)
    assert any("github-tools" in inc for inc in includes), (
        "github-tools-dtu must include github-tools"
    )


def test_github_tools_dtu_includes_digital_twin_universe():
    """github-tools-dtu.bundle.md must include amplifier-bundle-digital-twin-universe."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-dtu.bundle.md")
    includes = _include_bundles(fm)
    assert any("digital-twin-universe" in inc for inc in includes), (
        "github-tools-dtu must include digital-twin-universe"
    )


def test_github_tools_dtu_no_session_override():
    """github-tools-dtu.bundle.md must NOT declare a session: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-dtu.bundle.md")
    assert "session" not in fm


def test_github_tools_dtu_no_providers_override():
    """github-tools-dtu.bundle.md must NOT declare a providers: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-dtu.bundle.md")
    assert "providers" not in fm


# ---------------------------------------------------------------------------
# github-tools-amplifier-dev: extends github-tools-dtu with Amplifier dev tooling
# ---------------------------------------------------------------------------


def test_github_tools_amplifier_dev_includes_dtu():
    """github-tools-amplifier-dev.bundle.md must include the github-tools-dtu bundle."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-amplifier-dev.bundle.md")
    includes = _include_bundles(fm)
    assert any("github-tools-dtu" in inc for inc in includes), (
        "github-tools-amplifier-dev must include github-tools-dtu"
    )


def test_github_tools_amplifier_dev_no_launch_dtu():
    """github-tools-amplifier-dev.bundle.md must NOT declare tool-launch-dtu."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-amplifier-dev.bundle.md")
    modules = _tool_modules(fm)
    assert "tool-launch-dtu" not in modules


def test_github_tools_amplifier_dev_no_session_override():
    """github-tools-amplifier-dev.bundle.md must NOT declare a session: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-amplifier-dev.bundle.md")
    assert "session" not in fm


def test_github_tools_amplifier_dev_no_providers_override():
    """github-tools-amplifier-dev.bundle.md must NOT declare a providers: block."""
    fm = _parse_frontmatter(_BUNDLES_DIR / "github-tools-amplifier-dev.bundle.md")
    assert "providers" not in fm
