"""Unit tests for the Scanner."""

from pathlib import Path
import pytest

from devworkbench.configuration import ScanConfig
from devworkbench.models import Technology
from devworkbench.scanner import Scanner


def test_scanner_on_synthetic_repo() -> None:
    repo_path = Path(__file__).parent / "fixtures" / "synthetic_repo"
    scanner = Scanner()
    result = scanner.scan(str(repo_path))

    assert result.summary.total_files_discovered > 0
    assert result.summary.supported_files > 0
    assert result.summary.modified_files == 0  # CRITICAL invariant

    # Check Helm Chart was found and grouped
    assert len(result.helm_charts) == 1
    chart = result.helm_charts[0]
    assert chart.name == "payment-service"
    assert chart.chart_yaml is not None
    assert len(chart.values_files) >= 1
    assert len(chart.template_files) >= 1

    # Check default ignoring of node_modules
    detected_paths = [d.relative_path.replace("\\", "/") for d in result.detections]
    assert not any("node_modules" in p for p in detected_paths)

    # Check technologies found
    detected_techs = {d.technology for d in result.detections}
    assert Technology.JENKINS in detected_techs
    assert Technology.KUBERNETES in detected_techs
    assert Technology.OPENSHIFT in detected_techs
    assert Technology.HELM in detected_techs
    assert Technology.TERRAFORM in detected_techs
    assert Technology.DOCKERFILE in detected_techs
    assert Technology.DOCKER_COMPOSE in detected_techs
    assert Technology.GITHUB_ACTIONS in detected_techs
    assert Technology.GITLAB_CI in detected_techs
    assert Technology.SHELL in detected_techs
    assert Technology.PYTHON in detected_techs
    assert Technology.JSON in detected_techs
    assert Technology.XML in detected_techs
    assert Technology.SQL in detected_techs
    assert Technology.JAVASCRIPT in detected_techs
    assert Technology.TYPESCRIPT in detected_techs
    assert Technology.JAVA in detected_techs


def test_scanner_custom_ignore(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('app')")
    (tmp_path / "temp").mkdir()
    (tmp_path / "temp" / "temp.py").write_text("print('temp')")

    config = ScanConfig()
    config.add_custom_ignores(["temp/*"])
    scanner = Scanner(config=config)
    result = scanner.scan(str(tmp_path))

    detected_paths = [d.relative_path.replace("\\", "/") for d in result.detections]
    assert any("src/app.py" in p for p in detected_paths)
    assert not any("temp/temp.py" in p for p in detected_paths)


def test_scanner_single_file(tmp_path: Path) -> None:
    single_file = tmp_path / "Dockerfile"
    single_file.write_text("FROM alpine\n")

    scanner = Scanner()
    result = scanner.scan(str(single_file))
    assert result.summary.total_files_discovered == 1
    assert result.summary.supported_files == 1
    assert result.detections[0].technology == Technology.DOCKERFILE


def test_scanner_nonexistent_path() -> None:
    scanner = Scanner()
    with pytest.raises(FileNotFoundError):
        scanner.scan("non_existent_path_xyz_12345")


def test_scanner_empty_directory(tmp_path: Path) -> None:
    scanner = Scanner()
    result = scanner.scan(str(tmp_path))
    assert result.summary.total_files_discovered == 0
    assert result.summary.supported_files == 0
    assert result.summary.unknown_files == 0
    assert len(result.detections) == 0
