"""Unit and integration tests for DependencyInstaller, error classification, and setup CLI."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from devworkbench.capabilities.installer import DependencyInstaller
from devworkbench.capabilities.model import (
    InstallationErrorKind,
    InstallMethod,
    ToolPriority,
    ToolProvider,
)
from devworkbench.capabilities.registry import CapabilityRegistry
from devworkbench.cli import main
from devworkbench.models import Technology


def test_installer_already_available_tool() -> None:
    """Verify that an already available tool is recorded as already_available and verified."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    provider = ToolProvider(
        name="test-available",
        technology=Technology.PYTHON,
        capability="python_lint",  # type: ignore
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="MIT",
        is_available_fn=lambda: True,
        version_fn=lambda: "1.0.0",
    )
    registry.register(provider)

    installer = DependencyInstaller(registry)
    res = installer.install_provider(provider)

    assert res.status == "already_available"
    assert res.verified is True
    assert res.version == "1.0.0"


def test_installer_successful_pip_install_and_verification() -> None:
    """Verify that a successful pip installation runs post-install verification probe."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    avail_state = [False]

    provider = ToolProvider(
        name="test-pip-tool",
        technology=Technology.PYTHON,
        capability="python_lint",  # type: ignore
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="MIT",
        install_method=InstallMethod.PIP,
        install_package_name="test-pip-tool",
        is_available_fn=lambda: avail_state[0],
        version_fn=lambda: "2.1.0" if avail_state[0] else None,
    )
    registry.register(provider)

    installer = DependencyInstaller(registry)

    # Mock subprocess.run success
    def mock_subprocess_run(*args, **kwargs):
        avail_state[0] = True
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Successfully installed test-pip-tool"
        mock_proc.stderr = ""
        return mock_proc

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        res = installer.install_provider(provider)

        assert res.status == "success"
        assert res.verified is True
        assert res.version == "2.1.0"
        assert "Successfully installed" in res.message


def test_installer_post_install_verification_failure() -> None:
    """Verify that if pip succeeds but post-install probe fails, VERIFICATION_FAILED is returned."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    provider = ToolProvider(
        name="test-broken-tool",
        technology=Technology.PYTHON,
        capability="python_lint",  # type: ignore
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="MIT",
        install_method=InstallMethod.PIP,
        install_package_name="test-broken-tool",
        is_available_fn=lambda: False,  # Still unavailable!
    )
    registry.register(provider)

    installer = DependencyInstaller(registry)

    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Successfully installed"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        res = installer.install_provider(provider)

        assert res.status == "failed"
        assert res.verified is False
        assert res.error_kind == InstallationErrorKind.VERIFICATION_FAILED


def test_installer_error_classification() -> None:
    """Verify proper classification of network, TLS, proxy, and permission errors."""
    # 1. TLS error
    assert DependencyInstaller.classify_error(1, "", "SSLError: CERTIFICATE_VERIFY_FAILED") == InstallationErrorKind.TLS_ERROR

    # 2. Network unreachable / offline
    assert DependencyInstaller.classify_error(1, "", "ConnectionError: Failed to establish a new connection: [Errno 11001] getaddrinfo failed") in [
        InstallationErrorKind.NETWORK_UNAVAILABLE,
        InstallationErrorKind.DNS_ERROR,
    ]

    # 3. Proxy error
    assert DependencyInstaller.classify_error(1, "", "ProxyError: Cannot connect to proxy: 407 Proxy Authentication Required") == InstallationErrorKind.PROXY_ERROR

    # 4. Permission denied
    assert DependencyInstaller.classify_error(1, "", "PermissionError: [WinError 5] Access is denied") == InstallationErrorKind.PERMISSION_DENIED

    # 5. Package not found
    assert DependencyInstaller.classify_error(1, "", "ERROR: No matching distribution found for nonexistent-pkg") == InstallationErrorKind.PACKAGE_NOT_FOUND


def test_installer_timeout_error_handling() -> None:
    """Verify that subprocess timeout is caught and categorized without hanging."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    provider = ToolProvider(
        name="timeout-tool",
        technology=Technology.PYTHON,
        capability="python_lint",  # type: ignore
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="MIT",
        install_method=InstallMethod.PIP,
        install_package_name="timeout-tool",
        is_available_fn=lambda: False,
    )
    registry.register(provider)

    installer = DependencyInstaller(registry)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pip", timeout=60)):
        res = installer.install_provider(provider)
        assert res.status == "failed"
        assert res.error_kind == InstallationErrorKind.TIMEOUT


def test_setup_environment_continues_on_failure_with_fallbacks() -> None:
    """Verify that setup runs through multiple tools and records fallbacks for failures."""
    registry = CapabilityRegistry()
    registry.providers.clear()

    # Tool 1: fails
    tool1 = ToolProvider(
        name="tool1",
        technology=Technology.YAML,
        capability="yaml_lint",  # type: ignore
        priority=ToolPriority.OPENSOURCE,
        source="Python package",
        license="GPL",
        install_method=InstallMethod.PIP,
        install_package_name="tool1",
        is_available_fn=lambda: False,
    )
    # Tool 1 Fallback: DWB rule
    tool1_dwb = ToolProvider(
        name="devworkbench-yaml",
        technology=Technology.YAML,
        capability="yaml_lint",  # type: ignore
        priority=ToolPriority.DEVWORKBENCH,
        source="Internal engine",
        license="Apache-2.0",
        is_available_fn=lambda: True,
    )
    # Tool 2: already available
    tool2 = ToolProvider(
        name="tool2",
        technology=Technology.PYTHON,
        capability="python_syntax",  # type: ignore
        priority=ToolPriority.NATIVE,
        source="Python stdlib",
        license="PSF",
        is_available_fn=lambda: True,
    )

    registry.register(tool1)
    registry.register(tool1_dwb)
    registry.register(tool2)

    installer = DependencyInstaller(registry)

    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "ConnectionError: network unreachable"
        mock_run.return_value = mock_proc

        report = installer.setup_environment()

        assert len(report.failed) == 1
        assert report.failed[0].tool_name == "tool1"
        assert report.failed[0].error_kind == InstallationErrorKind.NETWORK_UNAVAILABLE
        assert len(report.already_available) == 1
        assert report.already_available[0].tool_name == "tool2"
        assert len(report.fallbacks) == 1
        assert report.fallbacks[0]["fallback"] == "DEVWORKBENCH:devworkbench-yaml"


def test_cli_setup_command() -> None:
    """Verify devworkbench setup CLI command (dry-run, json)."""
    runner = CliRunner()

    # Dry run
    res_dry = runner.invoke(main, ["setup", "--dry-run"])
    assert res_dry.exit_code == 0
    assert "DevWorkBench - Dependency & Tool Setup" in res_dry.output

    # JSON format
    res_json = runner.invoke(main, ["setup", "--dry-run", "--json"])
    assert res_json.exit_code == 0
    assert '"successful":' in res_json.output
    assert '"already_available":' in res_json.output
    assert '"failed":' in res_json.output
