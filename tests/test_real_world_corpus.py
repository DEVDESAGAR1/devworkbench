"""Tests verifying DevWorkBench against real-world test corpus and edge cases."""

import json
from pathlib import Path
from click.testing import CliRunner

from devworkbench.cli import main
from devworkbench.scanner import Scanner
from devworkbench.configuration import ScanConfig
from devworkbench.models import DiagnosticSeverity, DiagnosticCategory

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real_world"


def test_real_world_good_corpus_clean_scan():
    """Verify that a compliant, best-practice repository produces 0 errors."""
    good_dir = FIXTURES_DIR / "good"
    scanner = Scanner()
    result = scanner.scan(good_dir)

    errors = [d for d in result.diagnostics if d.severity == DiagnosticSeverity.ERROR]
    assert len(errors) == 0, f"Expected 0 errors in good corpus, got: {errors}"


def test_real_world_bad_corpus_detects_all_expected_issues():
    """Verify that intentional anti-patterns and broken files in bad/ are caught."""
    bad_dir = FIXTURES_DIR / "bad"
    scanner = Scanner()
    result = scanner.scan(bad_dir)

    rules_triggered = {d.rule for d in result.diagnostics if d.rule}

    # Verify key rules triggered
    assert "K8S001" in rules_triggered or "K8S003" in rules_triggered  # latest tag / missing resources
    assert "JENKINS001" in rules_triggered or "JENKINS-SYNTAX-003" in rules_triggered  # Jenkins issues
    assert "HELM001" in rules_triggered  # Helm missing apiVersion/name

    # Check for syntax errors caught
    syntax_errors = [d for d in result.diagnostics if d.category == DiagnosticCategory.SYNTAX]
    assert len(syntax_errors) >= 1  # broken.py or invalid.yaml


def test_real_world_edge_cases_no_crashes():
    """Verify multi-doc yaml, scripted pipelines, comment-only files handle gracefully."""
    edge_dir = FIXTURES_DIR / "edge_cases"
    scanner = Scanner()
    result = scanner.scan(edge_dir)

    # Scanning edge cases must succeed without throwing exceptions
    assert result.summary.total_files_discovered > 0
    assert result.summary.duration_ms >= 0


def test_configuration_rule_disabling(tmp_path):
    """Verify that a .devworkbench.yaml config file can disable specific rules."""
    bad_dir = FIXTURES_DIR / "bad"
    config_file = tmp_path / ".devworkbench.yaml"
    config_file.write_text("""
disabled_rules:
  - K8S001
  - HELM001
""")

    config = ScanConfig.load_from_dir(tmp_path)
    assert "K8S001" in config.disabled_rules
    assert "HELM001" in config.disabled_rules

    scanner = Scanner(config=config)
    result = scanner.scan(bad_dir)

    rules_triggered = {d.rule for d in result.diagnostics if d.rule}
    assert "K8S001" not in rules_triggered
    assert "HELM001" not in rules_triggered


def test_cli_scan_real_world_good_exit_code():
    runner = CliRunner()
    good_dir = FIXTURES_DIR / "good"
    result = runner.invoke(main, ["scan", str(good_dir)])
    assert result.exit_code == 0
    assert "Analysis Summary" in result.output
    assert "No files modified." in result.output
