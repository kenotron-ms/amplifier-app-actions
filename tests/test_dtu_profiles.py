"""Tests for DTU profile YAML files under .amplifier/digital-twin-universe/profiles/."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# Root of the amplifier-app-actions repo (parent of this tests/ directory)
_REPO_ROOT = Path(__file__).parent.parent
_PROFILES_DIR = _REPO_ROOT / ".amplifier" / "digital-twin-universe" / "profiles"


class TestValidatePromptProfile:
    """Validates the validate-prompt.yaml DTU profile structure and content."""

    @pytest.fixture
    def profile_path(self) -> Path:
        return _PROFILES_DIR / "validate-prompt.yaml"

    @pytest.fixture
    def profile(self, profile_path: Path) -> dict:
        """Parse and return the profile YAML."""
        return yaml.safe_load(profile_path.read_text())

    def test_file_exists(self, profile_path: Path) -> None:
        assert profile_path.exists(), (
            f"validate-prompt.yaml not found at {profile_path}"
        )

    def test_valid_yaml(self, profile_path: Path) -> None:
        """Profile must be parseable YAML (no syntax errors)."""
        content = yaml.safe_load(profile_path.read_text())
        assert content is not None
        assert isinstance(content, dict)

    def test_name(self, profile: dict) -> None:
        assert profile["name"] == "validate-prompt"

    def test_base_image(self, profile: dict) -> None:
        assert profile["base"]["image"] == "ubuntu:24.04"

    def test_vars_declared(self, profile: dict) -> None:
        """GITEA_URL and GITEA_TOKEN must be required vars; core_ref and foundation_ref optional."""
        vars_list = profile["vars"]
        var_names = {v["name"] for v in vars_list}
        assert "GITEA_URL" in var_names, "GITEA_URL var not declared"
        assert "GITEA_TOKEN" in var_names, "GITEA_TOKEN var not declared"
        assert "core_ref" in var_names, "core_ref var not declared"
        assert "foundation_ref" in var_names, "foundation_ref var not declared"

    def test_gitea_url_required(self, profile: dict) -> None:
        gitea_url_var = next(v for v in profile["vars"] if v["name"] == "GITEA_URL")
        assert gitea_url_var.get("required") is True

    def test_gitea_token_required(self, profile: dict) -> None:
        gitea_token_var = next(v for v in profile["vars"] if v["name"] == "GITEA_TOKEN")
        assert gitea_token_var.get("required") is True

    def test_core_ref_default_empty(self, profile: dict) -> None:
        core_ref_var = next(v for v in profile["vars"] if v["name"] == "core_ref")
        assert core_ref_var.get("default") == ""

    def test_foundation_ref_default_empty(self, profile: dict) -> None:
        foundation_ref_var = next(
            v for v in profile["vars"] if v["name"] == "foundation_ref"
        )
        assert foundation_ref_var.get("default") == ""

    def test_passthrough_allow_external(self, profile: dict) -> None:
        assert profile["passthrough"]["allow_external"] is True

    def test_passthrough_anthropic_service(self, profile: dict) -> None:
        services = profile["passthrough"]["services"]
        service_names = [s["name"] for s in services]
        assert "anthropic" in service_names

    def test_anthropic_key_env(self, profile: dict) -> None:
        anthropic = next(
            s for s in profile["passthrough"]["services"] if s["name"] == "anthropic"
        )
        assert anthropic["key_env"] == "ANTHROPIC_API_KEY"

    def test_url_rewrites_auth(self, profile: dict) -> None:
        auth = profile["url_rewrites"]["auth"]
        assert auth["username"] == "admin"
        assert auth["token_var"] == "GITEA_TOKEN"

    def test_url_rewrites_no_fast_path(self, profile: dict) -> None:
        assert profile["url_rewrites"]["allow_uv_github_fast_path"] is False

    def test_url_rewrites_boundary_mode(self, profile: dict) -> None:
        assert profile["url_rewrites"]["default_match_mode"] == "boundary"

    def test_url_rewrite_app_actions_rule(self, profile: dict) -> None:
        rules = profile["url_rewrites"]["rules"]
        matches = [r["match"] for r in rules]
        assert "github.com/microsoft/amplifier-app-actions" in matches

    def test_url_rewrite_app_actions_target(self, profile: dict) -> None:
        rules = profile["url_rewrites"]["rules"]
        rule = next(
            r for r in rules if r["match"] == "github.com/microsoft/amplifier-app-actions"
        )
        assert "${GITEA_URL}/admin/amplifier-app-actions" in rule["target"]

    def test_provision_has_setup_cmds(self, profile: dict) -> None:
        assert "setup_cmds" in profile["provision"]
        assert len(profile["provision"]["setup_cmds"]) >= 5, (
            "Expected at least 5 setup_cmds steps"
        )

    def test_provision_installs_deps(self, profile: dict) -> None:
        """First setup cmd must install system dependencies including jq."""
        first_cmd = profile["provision"]["setup_cmds"][0]
        assert "apt-get" in first_cmd
        assert "jq" in first_cmd

    def test_provision_installs_uv(self, profile: dict) -> None:
        """One setup cmd installs uv via the official installer script."""
        cmds = profile["provision"]["setup_cmds"]
        assert any("astral.sh/uv" in cmd for cmd in cmds), (
            "No step installs uv via astral.sh"
        )

    def test_provision_creates_gitea_test_data(self, profile: dict) -> None:
        """One step creates test-org and test-repo in Gitea."""
        cmds = " ".join(str(c) for c in profile["provision"]["setup_cmds"])
        assert "test-org" in cmds
        assert "test-repo" in cmds

    def test_provision_installs_amplifier_triage(self, profile: dict) -> None:
        """One step installs amplifier-app-actions via uv tool install."""
        cmds = " ".join(str(c) for c in profile["provision"]["setup_cmds"])
        assert "uv tool install" in cmds
        assert "amplifier-app-actions" in cmds

    def test_provision_writes_event_json(self, profile: dict) -> None:
        """One step writes event.json with action='opened'."""
        cmds = " ".join(str(c) for c in profile["provision"]["setup_cmds"])
        assert "event.json" in cmds
        assert '"opened"' in cmds or "'opened'" in cmds or "opened" in cmds

    def test_provision_runs_amplifier_triage(self, profile: dict) -> None:
        """One step runs amplifier-triage with --prompt, --provider, --event-path."""
        cmds = " ".join(str(c) for c in profile["provision"]["setup_cmds"])
        assert "amplifier-triage" in cmds
        assert "--prompt" in cmds
        assert "--provider" in cmds
        assert "--event-path" in cmds

    def test_provision_verifies_comment_count(self, profile: dict) -> None:
        """Verification step checks COMMENT_COUNT >= 1."""
        cmds = " ".join(str(c) for c in profile["provision"]["setup_cmds"])
        assert "COMMENT_COUNT" in cmds
        assert "validation.done" in cmds

    def test_readiness_check(self, profile: dict) -> None:
        """Readiness check must verify /root/validation.done exists."""
        readiness = profile["readiness"]
        assert len(readiness) >= 1
        commands = [r.get("command", "") for r in readiness]
        assert any("validation.done" in cmd for cmd in commands), (
            "No readiness check tests for /root/validation.done"
        )
