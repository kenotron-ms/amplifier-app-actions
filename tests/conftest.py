"""Shared pytest fixtures for amplifier_app_actions tests."""

import pytest


@pytest.fixture
def issue_event_json() -> dict:
    """Minimal GitHub issues.opened webhook payload."""
    return {
        "action": "opened",
        "issue": {
            "number": 1,
            "title": "Test issue",
            "body": "Something is broken in the auth module",
            "user": {"login": "test-user"},
            "labels": [],
        },
        "repository": {
            "name": "test-repo",
            "owner": {"login": "test-org"},
        },
    }


@pytest.fixture
def pr_event_json() -> dict:
    """Minimal GitHub pull_request.opened webhook payload."""
    return {
        "action": "opened",
        "pull_request": {
            "number": 2,
            "title": "Fix auth module bug",
            "body": "This PR fixes the bug reported in the auth module.",
            "user": {"login": "test-user"},
            "labels": [],
            "base": {"ref": "main"},
            "head": {"ref": "feature/test"},
        },
        "repository": {
            "name": "test-repo",
            "owner": {"login": "test-org"},
        },
    }
