"""Unit and integration tests for the Safe Fix Engine and Fix Planner."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from devworkbench.adapters.registry import AdapterRegistry
from devworkbench.fixes import FixEngine
from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FixCandidate,
    FixKind,
    FixSafety,
    ToolState,
)
from devworkbench.planner import FixPlanner
from devworkbench.scanner import Scanner


def test_fix_planner_classifies_safe_vs_manual():
    diag_safe = Diagnostic(
        path="app.py",
        line=5,
        column=1,
        severity=DiagnosticSeverity.WARNING,
        category=DiagnosticCategory.LINT,
        rule="F401",
        message="`os` imported but unused",
        source="ruff",
        fix_available=True,
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_source="ruff",
        fix_safety=FixSafety.SAFE,
        fix_description="Ruff native fix for F401",
    )
    diag_manual = Diagnostic(
        path="app.py",
        line=10,
        column=1,
        severity=DiagnosticSeverity.ERROR,
        category=DiagnosticCategory.SYNTAX,
        rule="SyntaxError",
        message="invalid syntax",
        source="python-ast",
        fix_available=False,
        fix_kind=FixKind.MANUAL,
        fix_safety=FixSafety.UNSAFE,
    )

    plan = FixPlanner.create_plan([diag_safe, diag_manual], target_paths=["app.py"])

    assert len(plan.safe_candidates) == 1
    assert plan.safe_candidates[0].rule == "F401"
    assert plan.safe_candidates[0].fix_safety == FixSafety.SAFE

    assert len(plan.manual_candidates) == 1
    assert plan.manual_candidates[0].rule == "SyntaxError"
    assert "app.py" in plan.files_to_modify


def test_fix_planner_detects_multi_engine_conflicts(tmp_path: Path):
    test_file = tmp_path / "manifest.yaml"
    test_file.write_text("apiVersion: v1\nkind: ConfigMap\n")

    diag1 = Diagnostic(
        path=str(test_file),
        line=1,
        severity=DiagnosticSeverity.WARNING,
        message="Issue 1",
        source="engine_a",
        fix_available=True,
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_source="engine_a",
        fix_safety=FixSafety.SAFE,
    )
    diag2 = Diagnostic(
        path=str(test_file),
        line=1,
        severity=DiagnosticSeverity.WARNING,
        message="Issue 2",
        source="engine_b",
        fix_available=True,
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_source="engine_b",
        fix_safety=FixSafety.SAFE,
    )

    plan = FixPlanner.create_plan([diag1, diag2], target_paths=[str(test_file)], base_dir=tmp_path)

    # Multi-engine conflict detected -> moved to conflicts and manual candidates
    assert len(plan.conflicts) == 1
    assert "conflicting fix engines" in plan.conflicts[0].reason
    assert len(plan.safe_candidates) == 0
    assert str(test_file) not in plan.files_to_modify


def test_fix_engine_sha256_integrity_precheck(tmp_path: Path):
    test_file = tmp_path / "script.py"
    test_file.write_text("import os\nprint('hello')\n")

    diag = Diagnostic(
        path=str(test_file),
        line=1,
        severity=DiagnosticSeverity.WARNING,
        rule="F401",
        message="Unused import",
        source="ruff",
        fix_available=True,
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_source="ruff",
        fix_safety=FixSafety.SAFE,
    )

    plan = FixPlanner.create_plan([diag], target_paths=[str(test_file)], base_dir=tmp_path)
    assert str(test_file) in plan.file_hashes_before

    # Modify file on disk to simulate concurrent edit after planning
    test_file.write_text("import os\n# user added a comment\nprint('hello')\n")

    registry = AdapterRegistry()
    results, engine_states, modified_count = FixEngine.execute_plan(plan, registry, base_dir=tmp_path)

    # The fix must be safely skipped due to integrity mismatch!
    assert len(results) == 1
    assert results[0].status == "skipped"
    assert "File changed since analysis" in results[0].message
    assert modified_count == 0


def test_fix_engine_applies_safe_native_fix(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("import os\n\nprint('hello')\n")

    cand = FixCandidate(
        path=str(test_file),
        rule="F401",
        message="Unused import",
        source="ruff",
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_safety=FixSafety.SAFE,
        description="Ruff native fix for F401",
    )

    plan = FixPlanner.create_plan([], target_paths=[str(test_file)], base_dir=tmp_path)
    plan.safe_candidates = [cand]
    plan.files_to_modify = [str(test_file)]
    plan.file_hashes_before[str(test_file)] = hashlib.sha256(test_file.read_bytes()).hexdigest()

    registry = AdapterRegistry()
    python_adapter = registry.get_adapter_for_tech(registry.adapters[1].technology)

    with patch.object(python_adapter, "is_available", return_value=(True, None)), \
         patch.object(python_adapter, "apply_fix", return_value=(True, None)):
        results, engine_states, modified_count = FixEngine.execute_plan(plan, registry, base_dir=tmp_path)

        assert len(results) == 1
        assert results[0].status == "applied"
        assert engine_states.get("ruff") == ToolState.FIXED.value


def test_fix_engine_handles_adapter_failure_gracefully(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("print('bad')\n")

    cand = FixCandidate(
        path=str(test_file),
        rule="F401",
        message="Unused import",
        source="ruff",
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_safety=FixSafety.SAFE,
        description="Ruff native fix for F401",
    )

    plan = FixPlanner.create_plan([], target_paths=[str(test_file)], base_dir=tmp_path)
    plan.safe_candidates = [cand]
    plan.files_to_modify = [str(test_file)]
    plan.file_hashes_before[str(test_file)] = hashlib.sha256(test_file.read_bytes()).hexdigest()

    registry = AdapterRegistry()
    python_adapter = registry.get_adapter_for_tech(registry.adapters[1].technology)

    with patch.object(python_adapter, "is_available", return_value=(True, None)), \
         patch.object(python_adapter, "apply_fix", return_value=(False, "Simulated ruff syntax crash")):
        results, engine_states, modified_count = FixEngine.execute_plan(plan, registry, base_dir=tmp_path)

        assert len(results) == 1
        assert results[0].status == "failed"
        assert "Simulated ruff syntax crash" in results[0].message
        assert engine_states.get("ruff") == ToolState.FIX_FAILED.value


def test_fix_engine_restricted_network_unavailable_tool(tmp_path: Path):
    test_file = tmp_path / "Dockerfile"
    test_file.write_text("FROM alpine:latest\n")

    cand = FixCandidate(
        path=str(test_file),
        rule="DL3008",
        message="Pin versions",
        source="hadolint",
        fix_kind=FixKind.NATIVE_ENGINE,
        fix_safety=FixSafety.SAFE,
        description="Hadolint fix",
    )

    plan = FixPlanner.create_plan([], target_paths=[str(test_file)], base_dir=tmp_path)
    plan.safe_candidates = [cand]
    plan.files_to_modify = [str(test_file)]
    plan.file_hashes_before[str(test_file)] = hashlib.sha256(test_file.read_bytes()).hexdigest()

    registry = AdapterRegistry()
    docker_adapter = next(a for a in registry.adapters if a.name == "Hadolint")

    with patch.object(docker_adapter, "is_available", return_value=(False, MagicMock(install_hint="Unavailable"))):
        results, engine_states, modified_count = FixEngine.execute_plan(plan, registry, base_dir=tmp_path)

        assert len(results) == 1
        assert results[0].status == "skipped"
        assert "unavailable" in results[0].message.lower()
        assert engine_states.get("hadolint") == ToolState.NOT_INSTALLED.value


def test_scanner_run_fix_post_fix_validation(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("x = 1\n")

    scanner = Scanner()
    report = scanner.run_fix(
        target_paths=[str(test_file)],
        dry_run=True,
    )

    assert report.summary.files_analyzed >= 1
    assert report.summary.files_modified == 0
    assert report.confirmed is False
