"""Verification test to strictly enforce that 'scan', 'analyze-build', 'tools', 'rules', and 'fix --dry-run' NEVER modify any file."""

import hashlib
import os
from pathlib import Path
from click.testing import CliRunner

from devworkbench.cli import main
from devworkbench.scanner import Scanner


def _compute_workspace_fingerprint(directory: Path) -> dict:
    fingerprint = {}
    for root, _, files in os.walk(directory):
        for f in files:
            fp = Path(root) / f
            try:
                content = fp.read_bytes()
                fingerprint[str(fp.relative_to(directory))] = hashlib.sha256(content).hexdigest()
            except Exception:
                pass
    return fingerprint


def test_scan_and_analyze_leaves_workspace_strictly_unmodified() -> None:
    repo_path = Path(__file__).parent / "fixtures" / "synthetic_repo"
    real_world_path = Path(__file__).parent / "fixtures" / "real_world"

    # 1. Capture snapshot hashes before operations
    before_synthetic = _compute_workspace_fingerprint(repo_path)
    before_real_world = _compute_workspace_fingerprint(real_world_path)
    assert len(before_synthetic) > 0
    assert len(before_real_world) > 0

    # 2. Run Scanner programmatically
    scanner = Scanner()
    res = scanner.scan(str(repo_path))
    assert res.summary.modified_files == 0

    # 3. Run multi-target CLI scan
    runner = CliRunner()
    cli_res1 = runner.invoke(
        main,
        [
            "scan",
            str(repo_path / "Jenkinsfile"),
            str(repo_path / "k8s"),
            str(repo_path / "helm" / "payment-service"),
            "--verbose",
        ],
    )
    assert cli_res1.exit_code == 0

    # 4. Run analyze-build CLI
    dummy_log = repo_path / "build_test.log"
    dummy_log.write_text("CrashLoopBackOff\nERROR: script returned exit code 1\n")
    try:
        cli_res2 = runner.invoke(main, ["analyze-build", str(dummy_log)])
        assert cli_res2.exit_code == 0
    finally:
        if dummy_log.exists():
            dummy_log.unlink()

    # 5. Run tools and rules CLI
    cli_tools = runner.invoke(main, ["tools"])
    assert cli_tools.exit_code == 0
    cli_rules = runner.invoke(main, ["rules"])
    assert cli_rules.exit_code == 0

    # 6. Run Scanner on real_world fixtures
    scanner.scan(real_world_path / "good")
    scanner.scan(real_world_path / "bad")
    scanner.scan(real_world_path / "edge_cases")

    # 7. Run fix in dry-run mode on real-world fixtures
    cli_fix_dry = runner.invoke(main, ["fix", str(real_world_path / "bad"), "--dry-run"])
    assert cli_fix_dry.exit_code == 0
    assert "No files modified." in cli_fix_dry.output

    # 8. Run fix in interactive mode and input 'n' (user declines)
    cli_fix_no = runner.invoke(main, ["fix", str(real_world_path / "bad")], input="n\n")
    assert cli_fix_no.exit_code == 0
    assert "No files modified." in cli_fix_no.output

    # 9. Capture snapshot hashes after all runs
    after_synthetic = _compute_workspace_fingerprint(repo_path)
    after_real_world = _compute_workspace_fingerprint(real_world_path)

    # 10. Assert 100% byte-for-byte equality
    assert before_synthetic == after_synthetic, "CRITICAL ERROR: Synthetic repo files were modified!"
    assert before_real_world == after_real_world, "CRITICAL ERROR: Real world fixture files were modified!"
