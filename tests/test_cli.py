"""Integration tests for the DevWorkBench CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from devworkbench.cli import main


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "DevWorkBench" in result.output
    assert "scan" in result.output
    assert "version" in result.output


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert "DevWorkBench version 0.1.0" in result.output


def test_cli_scan_human_format() -> None:
    repo_path = Path(__file__).parent / "fixtures" / "synthetic_repo"
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(repo_path)])
    assert result.exit_code == 0
    assert "DevWorkBench" in result.output
    assert "Jenkins" in result.output
    assert "Kubernetes" in result.output
    assert "Helm" in result.output
    assert "Terraform" in result.output
    assert "No files modified." in result.output


def test_cli_scan_json_format() -> None:
    repo_path = Path(__file__).parent / "fixtures" / "synthetic_repo"
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(repo_path), "--format", "json"])
    assert result.exit_code == 0

    # Parse JSON and verify schema stability
    data = json.loads(result.output)
    assert "target_path" in data
    assert "summary" in data
    assert "detections" in data
    assert "helm_charts" in data
    assert data["summary"]["modified_files"] == 0
    assert data["summary"]["supported_files"] > 0


def test_cli_scan_to_output_file(tmp_path: Path) -> None:
    repo_path = Path(__file__).parent / "fixtures" / "synthetic_repo"
    output_json = tmp_path / "out_report.json"

    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(repo_path), "--format", "json", "-o", str(output_json)])
    assert result.exit_code == 0
    assert output_json.exists()

    data = json.loads(output_json.read_text(encoding="utf-8"))
    assert data["summary"]["supported_files"] > 0


def test_cli_scan_invalid_path() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "this_path_does_not_exist_at_all_999"])
    assert result.exit_code == 1
    assert "does not exist" in result.output
