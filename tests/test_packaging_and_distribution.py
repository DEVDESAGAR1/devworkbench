"""Unit and integration tests for packaging, distribution, and doctor command."""

import re
from pathlib import Path

from click.testing import CliRunner

from devworkbench import __version__
from devworkbench.cli import main
from devworkbench.doctor import DoctorEngine


def test_doctor_engine_diagnose_structure() -> None:
    """Verify that DoctorEngine.diagnose returns complete system and tool diagnostics."""
    diag = DoctorEngine.diagnose()

    assert diag.devworkbench_version == __version__
    assert diag.python_version != ""
    assert diag.platform_name != ""
    assert diag.architecture != ""
    assert len(diag.core_dependencies) >= 3

    dep_names = {d.name for d in diag.core_dependencies}
    assert "click" in dep_names
    assert "rich" in dep_names
    assert "pyyaml" in dep_names

    assert len(diag.external_tools) >= 5
    tool_names = {t.name for t in diag.external_tools}
    assert "helm" in tool_names
    assert "terraform" in tool_names
    assert "ruff" in tool_names

    cap = diag.capability_summary
    assert "total_capabilities" in cap
    assert cap["total_capabilities"] > 0

    dict_data = diag.to_dict()
    assert "system" in dict_data
    assert "core_dependencies" in dict_data
    assert "external_tools" in dict_data
    assert "capability_summary" in dict_data


def test_doctor_cli_human_and_json_output() -> None:
    """Verify devworkbench doctor CLI command in human and JSON format."""
    runner = CliRunner()

    # Human output
    res_human = runner.invoke(main, ["doctor"])
    assert res_human.exit_code == 0
    assert "DevWorkBench - Environment Doctor & Health Diagnostics" in res_human.output
    assert "Core Python Runtime Dependencies" in res_human.output
    assert "External Tools & Engines Status" in res_human.output
    assert "Capability Priority Resolution" in res_human.output

    # JSON output
    res_json = runner.invoke(main, ["doctor", "--json"])
    assert res_json.exit_code == 0
    assert '"devworkbench_version":' in res_json.output
    assert '"core_dependencies":' in res_json.output
    assert '"capability_summary":' in res_json.output


def test_version_consistency_with_pyproject() -> None:
    """Verify that __version__ in __init__.py matches pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    assert pyproject_path.is_file()

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    assert match is not None, "Version not found in pyproject.toml"
    assert match.group(1) == __version__


def test_cli_entrypoint_help_and_subcommands() -> None:
    """Verify that all top-level CLI commands are registered and documented."""
    runner = CliRunner()
    res = runner.invoke(main, ["--help"])
    assert res.exit_code == 0
    assert "scan" in res.output
    assert "doctor" in res.output
    assert "capabilities" in res.output
    assert "tools" in res.output
    assert "rules" in res.output
    assert "setup" in res.output
    assert "fix" in res.output
    assert "analyze-build" in res.output
    assert "version" in res.output
