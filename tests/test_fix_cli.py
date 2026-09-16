"""Integration and CLI tests for `devworkbench fix` command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from devworkbench.cli import main
from devworkbench.models import FixCandidate, FixKind, FixPlan, FixSafety


def test_fix_cli_dry_run(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("import os\n\nprint('hello')\n")

    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(test_file), "--dry-run"])

    assert result.exit_code == 0
    assert "Fix (Dry Run)" in result.output or "Planned changes" in result.output or "No safe automatic fixes" in result.output
    assert "No files modified." in result.output


def test_fix_cli_confirmation_user_says_no(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("import os\n\nprint('hello')\n")

    runner = CliRunner()
    # Mock planning to have 1 safe candidate
    cand = FixCandidate(
        path=str(test_file),
        rule="F401",
        message="Unused import",
        source="ruff",
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_safety=FixSafety.SAFE,
        description="Ruff native fix for F401",
    )
    mock_plan = FixPlan(
        target_paths=[str(test_file)],
        safe_candidates=[cand],
        manual_candidates=[],
        conflicts=[],
        files_to_modify=[str(test_file)],
        file_hashes_before={str(test_file): "abc"},
    )

    with patch("devworkbench.scanner.Scanner.plan_fix", return_value=(MagicMock(), mock_plan)):
        # User enters 'n' at confirmation prompt
        result = runner.invoke(main, ["fix", str(test_file)], input="n\n")

        assert result.exit_code == 0
        assert "No changes applied." in result.output
        assert "No files modified." in result.output


def test_fix_cli_confirmation_user_says_yes(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("import os\n\nprint('hello')\n")

    runner = CliRunner()
    cand = FixCandidate(
        path=str(test_file),
        rule="F401",
        message="Unused import",
        source="ruff",
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_safety=FixSafety.SAFE,
        description="Ruff native fix for F401",
    )
    mock_plan = FixPlan(
        target_paths=[str(test_file)],
        safe_candidates=[cand],
        manual_candidates=[],
        conflicts=[],
        files_to_modify=[str(test_file)],
        file_hashes_before={str(test_file): "abc"},
    )

    with patch("devworkbench.scanner.Scanner.plan_fix", return_value=(MagicMock(), mock_plan)), \
         patch("devworkbench.runner.Runner.run_fix") as mock_run_fix:
        # User enters 'y' at confirmation prompt
        result = runner.invoke(main, ["fix", str(test_file)], input="y\n")

        assert result.exit_code == 0
        assert "Applying safe fixes..." in result.output
        mock_run_fix.assert_called_once()


def test_fix_cli_yes_flag_bypasses_confirmation(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("x = 1\n")

    runner = CliRunner()
    with patch("devworkbench.runner.Runner.run_fix") as mock_run_fix:
        result = runner.invoke(main, ["fix", str(test_file), "--yes"])
        assert result.exit_code == 0
        mock_run_fix.assert_called_once()


def test_fix_cli_json_dry_run(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("x = 1\n")

    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(test_file), "--dry-run", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "plan" in data
    assert "summary" in data
    assert data["summary"]["files_modified"] == 0


def test_fix_cli_nonexistent_path():
    runner = CliRunner()
    result = runner.invoke(main, ["fix", "nonexistent_file_path_123.yaml"])
    assert result.exit_code != 0
    assert "Target path does not exist" in result.output
