"""Integration tests for the complete analysis pipeline."""

import json
from pathlib import Path
from click.testing import CliRunner

from devworkbench.cli import main
from devworkbench.scanner import Scanner


def test_analysis_pipeline_detects_syntax_errors(tmp_path: Path) -> None:
    # 1. Broken Python file
    py_dir = tmp_path / "src"
    py_dir.mkdir()
    (py_dir / "bad.py").write_text("def broken(\n  123\n")

    # 2. Broken YAML file
    k8s_dir = tmp_path / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "bad.yaml").write_text("apiVersion: v1\nkind: [unclosed")

    scanner = Scanner()
    result = scanner.scan(str(tmp_path))

    assert result.summary.errors_count >= 2
    assert result.summary.files_with_issues >= 2
    assert result.summary.modified_files == 0

    sources = {d.source for d in result.diagnostics}
    assert "python-ast" in sources
    assert "pyyaml" in sources


def test_cli_json_flag(tmp_path: Path) -> None:
    (tmp_path / "test.py").write_text("print('hello')\n")
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "diagnostics" in data
    assert "tool_warnings" in data
    assert "summary" in data
    assert data["summary"]["analyzed_files"] == 1


def test_cli_tool_warnings_rendered(tmp_path: Path) -> None:
    # A shell script in the workspace when shellcheck is absent triggers a tool warning
    (tmp_path / "run.sh").write_text("#!/bin/bash\necho 123\n")
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    assert "Shell" in result.output
