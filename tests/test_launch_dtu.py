"""Tests for amplifier_app_actions.tools.launch_dtu — _parse_repo helper."""

from __future__ import annotations

from amplifier_app_actions.tools.launch_dtu import (
    LaunchDTUTool,  # noqa: F401
    _is_sha,  # noqa: F401
    _parse_repo,
    mount,  # noqa: F401
)


# ---------------------------------------------------------------------------
# _parse_repo tests
# ---------------------------------------------------------------------------


def test_parse_repo_owner_repo_and_tag():
    """'owner/repo@v1.2.3' → ('owner', 'repo', 'v1.2.3')."""
    owner, repo, ref = _parse_repo("myorg/myrepo@v1.2.3")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "v1.2.3"


def test_parse_repo_owner_repo_and_branch():
    """'owner/repo@main' → ('owner', 'repo', 'main')."""
    owner, repo, ref = _parse_repo("myorg/myrepo@main")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "main"


def test_parse_repo_branch_with_slash():
    """'owner/repo@feat/my-branch' → ('owner', 'repo', 'feat/my-branch').

    Uses rsplit('@', 1) so branch names containing '/' are handled correctly.
    """
    owner, repo, ref = _parse_repo("myorg/myrepo@feat/my-branch")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "feat/my-branch"


def test_parse_repo_no_ref_returns_none():
    """'owner/repo' with no '@' suffix returns ref=None."""
    owner, repo, ref = _parse_repo("myorg/myrepo")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref is None


def test_parse_repo_sha_ref():
    """'owner/repo@abc1234' → ('owner', 'repo', 'abc1234')."""
    owner, repo, ref = _parse_repo("myorg/myrepo@abc1234")
    assert owner == "myorg"
    assert repo == "myrepo"
    assert ref == "abc1234"


# ---------------------------------------------------------------------------
# _is_sha tests
# ---------------------------------------------------------------------------


def test_is_sha_seven_char_hex():
    """Seven lowercase hex chars ('abc1234') → True."""
    assert _is_sha("abc1234") is True


def test_is_sha_forty_char_hex():
    """Forty lowercase hex chars → True (full SHA-1 length)."""
    assert _is_sha("a" * 40) is True


def test_is_sha_tag_is_not_sha():
    """Version tag ('v1.2.3') contains dots/uppercase → False."""
    assert _is_sha("v1.2.3") is False


def test_is_sha_branch_main_is_not_sha():
    """Branch name 'main' contains non-hex chars → False."""
    assert _is_sha("main") is False
