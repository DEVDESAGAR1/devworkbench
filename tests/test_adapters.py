"""Unit tests for DevWorkBench adapters and diagnostic normalization."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from devworkbench.adapters.helm_adapter import HelmAdapter
from devworkbench.adapters.python_adapter import PythonAdapter
from devworkbench.adapters.shell_adapter import ShellAdapter
from devworkbench.adapters.terraform_adapter import TerraformAdapter
from devworkbench.adapters.yaml_adapter import YamlAdapter
from devworkbench.models import (
    DiagnosticCategory,
    DiagnosticSeverity,
    FileCategory,
    FileDetection,
    HelmChart,
    Technology,
)


def test_python_adapter_ast_syntax_error(tmp_path: Path) -> None:
    bad_py = tmp_path / "broken.py"
    bad_py.write_text("def broken_syntax(\n  x = 1\n")
    detection = FileDetection(
        path=str(bad_py),
        relative_path="broken.py",
        technology=Technology.PYTHON,
        category=FileCategory.DEVELOPER,
    )

    adapter = PythonAdapter()
    diags = adapter.analyze_file(bad_py, detection)

    assert len(diags) >= 1
    syntax_diag = diags[0]
    assert syntax_diag.severity == DiagnosticSeverity.ERROR
    assert syntax_diag.category == DiagnosticCategory.SYNTAX
    assert syntax_diag.line is not None
    assert syntax_diag.source == "python-ast"


def test_python_adapter_valid_file(tmp_path: Path) -> None:
    valid_py = tmp_path / "good.py"
    valid_py.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
    detection = FileDetection(
        path=str(valid_py),
        relative_path="good.py",
        technology=Technology.PYTHON,
        category=FileCategory.DEVELOPER,
    )

    adapter = PythonAdapter()
    diags = adapter.analyze_file(valid_py, detection)
    # Should have no syntax errors
    assert not any(d.category == DiagnosticCategory.SYNTAX for d in diags)


def test_yaml_adapter_syntax_error(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("key: value:\n  nested: [unclosed\n")
    detection = FileDetection(
        path=str(bad_yaml),
        relative_path="bad.yaml",
        technology=Technology.YAML,
        category=FileCategory.CONFIG,
    )

    adapter = YamlAdapter()
    diags = adapter.analyze_file(bad_yaml, detection)

    assert len(diags) == 1
    diag = diags[0]
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.category == DiagnosticCategory.SYNTAX
    assert diag.line is not None
    assert diag.source == "pyyaml"


def test_yaml_adapter_skips_helm_template(tmp_path: Path) -> None:
    helm_tpl = tmp_path / "deployment.yaml"
    helm_tpl.write_text("name: {{ .Values.name }}")
    detection = FileDetection(
        path=str(helm_tpl),
        relative_path="deployment.yaml",
        technology=Technology.HELM,
        category=FileCategory.DEVOPS,
        details="Helm Chart Template",
    )

    adapter = YamlAdapter()
    assert adapter.can_handle(detection) is False


def test_terraform_adapter_missing_tool_warning() -> None:
    adapter = TerraformAdapter()
    with patch("shutil.which", return_value=None):
        is_avail, warning = adapter.is_available()
        assert is_avail is False
        assert warning is not None
        assert warning.technology == Technology.TERRAFORM
        assert "Terraform" in warning.install_hint


def test_terraform_adapter_fmt_check(tmp_path: Path) -> None:
    tf_file = tmp_path / "main.tf"
    tf_file.write_text('resource "aws_s3_bucket" "b" {}\n')
    detection = FileDetection(
        path=str(tf_file),
        relative_path="main.tf",
        technology=Technology.TERRAFORM,
        category=FileCategory.DEVOPS,
    )

    adapter = TerraformAdapter()
    with patch("shutil.which", return_value="terraform"), \
         patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 1  # Indicates fmt needed
        mock_proc.stdout = "main.tf"
        mock_run.return_value = mock_proc

        diags = adapter.analyze_file(tf_file, detection)
        assert len(diags) == 1
        assert diags[0].category == DiagnosticCategory.FORMAT
        assert diags[0].fix_available is True


def test_shell_adapter_missing_tool_warning() -> None:
    adapter = ShellAdapter()
    with patch("shutil.which", return_value=None):
        is_avail, warning = adapter.is_available()
        assert is_avail is False
        assert warning is not None
        assert warning.technology == Technology.SHELL
        assert "ShellCheck" in warning.install_hint


def test_shell_adapter_parses_json(tmp_path: Path) -> None:
    sh_file = tmp_path / "script.sh"
    sh_file.write_text("#!/bin/bash\necho $VAR\n")
    detection = FileDetection(
        path=str(sh_file),
        relative_path="script.sh",
        technology=Technology.SHELL,
        category=FileCategory.DEVOPS,
    )

    sample_shellcheck_json = """[
      {
        "file": "script.sh",
        "line": 2,
        "endLine": 2,
        "column": 6,
        "endColumn": 10,
        "level": "warning",
        "code": 2086,
        "message": "Double quote to prevent globbing and word splitting.",
        "fix": null
      }
    ]"""

    adapter = ShellAdapter()
    with patch("shutil.which", return_value="shellcheck"), \
         patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = sample_shellcheck_json
        mock_run.return_value = mock_proc

        diags = adapter.analyze_file(sh_file, detection)
        assert len(diags) == 1
        d = diags[0]
        assert d.severity == DiagnosticSeverity.WARNING
        assert d.rule == "SC2086"
        assert d.line == 2
        assert d.column == 6
        assert d.source == "shellcheck"


def test_helm_adapter_template_failure_parsing(tmp_path: Path) -> None:
    chart_dir = tmp_path / "mychart"
    chart_dir.mkdir()
    chart = HelmChart(
        name="mychart",
        root_path=str(chart_dir),
        relative_root="mychart",
        chart_yaml="Chart.yaml",
    )

    helm_err_output = "Error: execution error at (mychart/templates/deployment.yaml:14:12): required value 'tag' missing"

    adapter = HelmAdapter()
    with patch("shutil.which", return_value="helm"), \
         patch("subprocess.run") as mock_run:
        # Mock lint (ok) and template (error)
        mock_lint = MagicMock(returncode=0, stdout="", stderr="")
        mock_tmpl = MagicMock(returncode=1, stdout="", stderr=helm_err_output)
        mock_run.side_effect = [mock_lint, mock_tmpl]

        diags = adapter.analyze_project(chart_dir, chart=chart)
        assert len(diags) == 1
        d = diags[0]
        assert d.severity == DiagnosticSeverity.ERROR
        assert d.path == "mychart/templates/deployment.yaml"
        assert d.line == 14
        assert d.column == 12
        assert "required value 'tag' missing" in d.message
