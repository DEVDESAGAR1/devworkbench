"""Integration tests for multi-target scanning and build-log CLI commands."""

import json
from pathlib import Path

from click.testing import CliRunner

from devworkbench.cli import main


def test_cli_scan_single_file() -> None:
    jf_path = Path(__file__).parent / "fixtures" / "synthetic_repo" / "Jenkinsfile"
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(jf_path)])

    assert result.exit_code == 0
    assert "Jenkins" in result.output
    assert "No files modified." in result.output


def test_cli_scan_multiple_files() -> None:
    repo = Path(__file__).parent / "fixtures" / "synthetic_repo"
    f1 = repo / "k8s" / "deployment.yaml"
    f2 = repo / "k8s" / "service.yaml"

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(f1), str(f2)])

    assert result.exit_code == 0
    assert "Kubernetes" in result.output
    assert "2 files analyzed" in result.output


def test_cli_scan_mixed_file_and_directory() -> None:
    repo = Path(__file__).parent / "fixtures" / "synthetic_repo"
    jf = repo / "Jenkinsfile"
    k8s_dir = repo / "k8s"

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(jf), str(k8s_dir)])

    assert result.exit_code == 0
    assert "Jenkins" in result.output
    assert "Kubernetes" in result.output


def test_cli_analyze_build_file(tmp_path: Path) -> None:
    log_file = tmp_path / "ci_build.log"
    log_file.write_text("""[Pipeline] stage: Deploy
Error: unauthorized: authentication required
ERROR: script returned exit code 1
""")

    runner = CliRunner()
    result = runner.invoke(main, ["analyze-build", str(log_file)])

    assert result.exit_code == 0
    assert "Build Log Analysis" in result.output
    assert "Root Cause Candidates" in result.output
    assert "authentication failed" in result.output


def test_cli_analyze_build_json(tmp_path: Path) -> None:
    log_file = tmp_path / "ci_build.log"
    log_file.write_text("""CrashLoopBackOff\nERROR: script returned exit code 1\n""")

    runner = CliRunner()
    result = runner.invoke(main, ["analyze-build", str(log_file), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "root_causes" in data
    assert "diagnostics" in data
    assert len(data["root_causes"]) >= 1


def test_cli_analyze_build_stdin() -> None:
    runner = CliRunner()
    stdin_data = "unauthorized: authentication required\nERROR: exit 1\n"
    result = runner.invoke(main, ["analyze-build", "-"], input=stdin_data)

    assert result.exit_code == 0
    assert "Build Log Analysis" in result.output
    assert "authentication failed" in result.output
