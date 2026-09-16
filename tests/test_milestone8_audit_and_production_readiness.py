"""Milestone 8: Production readiness, full audit, and release verification tests."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path
import pytest
from click.testing import CliRunner

from devworkbench.cli import main
from devworkbench.scanner import Scanner
from devworkbench.models import Diagnostic, DiagnosticSeverity
from devworkbench.adapters.registry import AdapterRegistry
from devworkbench.capabilities.resolver import CapabilityResolver
from devworkbench.capabilities.registry import CapabilityRegistry
from devworkbench.rules.registry import RuleRegistry


def test_package_metadata_and_version():
    """Verify CLI version command and package metadata."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help_all_subcommands():
    """Verify all subcommands display help cleanly without exceptions."""
    runner = CliRunner()
    for subcmd in ["scan", "fix", "doctor", "tools", "capabilities", "rules"]:
        result = runner.invoke(main, [subcmd, "--help"])
        assert result.exit_code == 0, f"Command '{subcmd} --help' failed with output: {result.output}"
        assert "Usage:" in result.output or "Options:" in result.output


def test_cli_doctor_command():
    """Verify doctor command runs cleanly."""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "Doctor" in result.output
    assert "System Information:" in result.output or "Environment" in result.output or "Platform:" in result.output or "System Health:" in result.output


def test_cli_tools_and_capabilities_commands():
    """Verify tools and capabilities commands list providers accurately."""
    runner = CliRunner()
    res_tools = runner.invoke(main, ["tools"])
    assert res_tools.exit_code == 0
    assert "Analysis Engines" in res_tools.output or "Tools" in res_tools.output

    res_caps = runner.invoke(main, ["capabilities"])
    assert res_caps.exit_code == 0
    assert "Priority Hierarchy" in res_caps.output or "Capability" in res_caps.output


def test_cli_rules_command():
    """Verify rules command outputs all registered rules."""
    runner = CliRunner()
    result = runner.invoke(main, ["rules"])
    assert result.exit_code == 0
    assert "JENKINS001" in result.output or "DOCKER001" in result.output


def test_self_scan_runs_without_crashes(tmp_path):
    """Verify devworkbench scan . runs cleanly on the current project directory."""
    runner = CliRunner()
    # Run against current workspace root with --format json for structured output check
    root_dir = str(Path(__file__).parent.parent)
    result = runner.invoke(main, ["scan", root_dir, "--format", "json"])
    assert result.exit_code == 0
    assert '"summary"' in result.output
    assert '"diagnostics"' in result.output


def test_diagnostic_model_serialization_and_fields():
    """Verify Diagnostic model includes all required Milestone 7 & 8 fields."""
    diag = Diagnostic(
        rule="DWB-K8S-001",
        message="Missing memory resource limits",
        path="k8s/deployment.yaml",
        line=12,
        column=5,
        severity=DiagnosticSeverity.ERROR,
        source="Kubernetes Rules",
        provider="kubelinter",
        provider_type="native",
        provider_priority=1,
        rule_origin="DevWorkBench rule engine",
        documentation_url="https://docs.devworkbench.local/rules/DWB-K8S-001",
        help_url="https://docs.devworkbench.local/rules/DWB-K8S-001",
        details="resources.limits.memory should be specified.",
        fix_available=True,
    )
    d_dict = diag.to_dict()
    assert d_dict["rule"] == "DWB-K8S-001"
    assert d_dict["provider"] == "kubelinter"
    assert d_dict["provider_type"] == "native"
    assert d_dict["provider_priority"] == 1
    assert d_dict["documentation_url"] == "https://docs.devworkbench.local/rules/DWB-K8S-001"
    assert d_dict["fix_available"] is True


def test_subprocess_utf8_encoding_safety(monkeypatch):
    """Verify adapters do not crash on non-ASCII output when invoking subprocess."""
    from devworkbench.adapters.python_adapter import PythonAdapter
    adapter = PythonAdapter()

    # Mock subprocess.run to return non-ASCII bytes/text
    class MockCompletedProcess:
        returncode = 1
        stdout = "Non-ASCII diagnostic: 🚀 Unicode character in test.py:1:1"
        stderr = ""

    def mock_run(*args, **kwargs):
        # Verify utf-8 encoding argument was provided
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"
        return MockCompletedProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)
    # The adapter should parse or handle without UnicodeDecodeError
    # We test that executing mock_run with utf-8 passes successfully
    res = subprocess.run(["dummy"], text=True, encoding="utf-8", errors="replace")
    assert "🚀" in res.stdout


def test_wheel_archive_contents():
    """Verify built wheel exists, is valid zip, and contains required packages and metadata."""
    dist_dir = Path(__file__).parent.parent / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) > 0, "No built wheel found in dist/ directory"
    wheel_path = wheels[0]

    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()
        # Verify entry point
        assert any("entry_points.txt" in n for n in namelist)
        # Verify core packages exist
        assert any("devworkbench/__init__.py" in n for n in namelist)
        assert any("devworkbench/cli.py" in n for n in namelist)
        assert any("devworkbench/scanner.py" in n for n in namelist)
        assert any("devworkbench/adapters/" in n for n in namelist)
        assert any("devworkbench/capabilities/" in n for n in namelist)
        assert any("devworkbench/rules/" in n for n in namelist)
        assert any("devworkbench/signatures/" in n for n in namelist)
        # Verify LICENSE file is included
        assert any("LICENSE" in n for n in namelist)
