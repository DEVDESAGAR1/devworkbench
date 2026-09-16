"""Tests for the diagnostic deduplication engine."""

from devworkbench.deduplication import DiagnosticDeduplicator
from devworkbench.models import Diagnostic, DiagnosticCategory, DiagnosticSeverity


def test_deduplicate_empty_list():
    assert DiagnosticDeduplicator.deduplicate([]) == []


def test_deduplicate_single_diagnostic():
    diag = Diagnostic(
        path="app.py",
        line=10,
        column=5,
        severity=DiagnosticSeverity.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="Invalid syntax",
        source="python-ast",
    )
    result = DiagnosticDeduplicator.deduplicate([diag])
    assert len(result) == 1
    assert result[0] == diag


def test_deduplicate_overlapping_tools_prefers_higher_priority():
    diag_ast = Diagnostic(
        path="app.py",
        line=10,
        column=None,
        severity=DiagnosticSeverity.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="SyntaxError: invalid syntax",
        source="python-ast",
    )
    diag_ruff = Diagnostic(
        path="app.py",
        line=10,
        column=5,
        severity=DiagnosticSeverity.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="SyntaxError: invalid syntax",
        source="ruff",
        rule="E999",
    )

    # When both report the same syntax error on the same line
    result = DiagnosticDeduplicator.deduplicate([diag_ast, diag_ruff])
    assert len(result) == 1
    assert result[0].source == "ruff"
    assert result[0].rule == "E999"
    assert result[0].column == 5


def test_deduplicate_preserves_distinct_issues_on_same_line():
    diag_lint = Diagnostic(
        path="app.py",
        line=10,
        column=1,
        severity=DiagnosticSeverity.WARNING,
        category=DiagnosticCategory.LINT,
        message="Unused variable 'x'",
        source="ruff",
        rule="F841",
    )
    diag_fmt = Diagnostic(
        path="app.py",
        line=10,
        column=1,
        severity=DiagnosticSeverity.INFO,
        category=DiagnosticCategory.FORMAT,
        message="Line too long (95 > 88 characters)",
        source="ruff",
        rule="E501",
    )

    result = DiagnosticDeduplicator.deduplicate([diag_lint, diag_fmt])
    assert len(result) == 2


def test_deduplicate_file_level_diagnostics():
    diag_pyyaml = Diagnostic(
        path="config.yaml",
        line=None,
        column=None,
        severity=DiagnosticSeverity.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="YAML parsing error: unexpected end of stream",
        source="pyyaml",
    )
    diag_yamllint = Diagnostic(
        path="config.yaml",
        line=None,
        column=None,
        severity=DiagnosticSeverity.ERROR,
        category=DiagnosticCategory.SYNTAX,
        message="YAML parsing error: unexpected end of stream",
        source="yamllint",
        rule="syntax",
    )

    result = DiagnosticDeduplicator.deduplicate([diag_pyyaml, diag_yamllint])
    assert len(result) == 1
    assert result[0].source == "yamllint"
