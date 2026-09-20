"""Python adapter utilizing Black, Ruff, and Python AST fallback for linting and formatting diagnostics."""

import ast
import functools
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from devworkbench.adapters.base import BaseAdapter
from devworkbench.execution import CommandRunner
from devworkbench.models import (
    CommandExecution,
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    FixCandidate,
    FixKind,
    FixSafety,
    Technology,
    ToolWarning,
)


class PythonAdapter(BaseAdapter):
    """Adapter for Python files using Black, Ruff, and AST parsing."""

    @property
    def technology(self) -> Technology:
        return Technology.PYTHON

    @property
    def name(self) -> str:
        return "Ruff / Python AST"

    @functools.lru_cache(maxsize=1)
    def _get_ruff_cmd(self) -> tuple[str, ...] | None:
        """Find the executable command to run Ruff."""
        if shutil.which("ruff"):
            return ("ruff",)
        try:
            res = subprocess.run(
                [sys.executable, "-m", "ruff", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
            )
            if res.returncode == 0:
                return (sys.executable, "-m", "ruff")
        except Exception:
            pass
        return None

    @functools.lru_cache(maxsize=1)
    def _get_black_cmd(self) -> tuple[str, ...] | None:
        """Find the executable command to run Black."""
        if shutil.which("black"):
            return ("black",)
        try:
            res = subprocess.run(
                [sys.executable, "-m", "black", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
            )
            if res.returncode == 0:
                return (sys.executable, "-m", "black")
        except Exception:
            pass
        return None

    def is_available(self) -> tuple[bool, ToolWarning | None]:
        ruff_cmd = self._get_ruff_cmd()
        black_cmd = self._get_black_cmd()
        if ruff_cmd or black_cmd:
            return True, None
        return False, ToolWarning(
            technology=Technology.PYTHON,
            tool_name="Ruff / Black",
            install_hint="Install Ruff via 'pip install ruff' or Black via 'pip install black' to enable advanced Python analysis.",
            documentation_url="https://docs.astral.sh/ruff/",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        rel_path = detection.relative_path

        # 1. AST Syntax Check (Native PSF-2.0 fallback)
        t0 = time.perf_counter()
        try:
            code_text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                code_text = file_path.read_text(encoding="latin-1")
            except Exception as e:
                diagnostics.append(
                    Diagnostic(
                        path=rel_path,
                        message=f"Failed to read file: {e}",
                        source="python",
                        severity=DiagnosticSeverity.ERROR,
                        category=DiagnosticCategory.SYNTAX,
                    )
                )
                return diagnostics

        try:
            ast.parse(code_text, filename=str(file_path))
            ast_duration = (time.perf_counter() - t0) * 1000
            self.record_execution(
                CommandExecution(
                    technology="Python",
                    capability="python_syntax",
                    provider_type="native",
                    provider_name="python-ast",
                    tool_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    executable="ast.parse",
                    args=[str(file_path)],
                    command=f"ast.parse({rel_path})",
                    cwd=str(file_path.parent),
                    exit_code=0,
                    status="PASS",
                    duration_ms=round(ast_duration, 2),
                )
            )
        except SyntaxError as e:
            ast_duration = (time.perf_counter() - t0) * 1000
            self.record_execution(
                CommandExecution(
                    technology="Python",
                    capability="python_syntax",
                    provider_type="native",
                    provider_name="python-ast",
                    tool_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    executable="ast.parse",
                    args=[str(file_path)],
                    command=f"ast.parse({rel_path})",
                    cwd=str(file_path.parent),
                    exit_code=1,
                    status="FAIL",
                    duration_ms=round(ast_duration, 2),
                    error_message=str(e),
                )
            )
            diagnostics.append(
                Diagnostic(
                    path=rel_path,
                    line=e.lineno,
                    column=e.offset,
                    end_line=e.end_lineno,
                    end_column=e.end_offset,
                    severity=DiagnosticSeverity.ERROR,
                    rule="SyntaxError",
                    message=e.msg or "Python syntax error",
                    source="python-ast",
                    category=DiagnosticCategory.SYNTAX,
                    details=e.text.strip() if e.text else None,
                    fix_available=False,
                    fix_kind=FixKind.MANUAL,
                    fix_safety=FixSafety.UNSAFE,
                    provider="python-ast",
                    provider_priority=1,
                    provider_type="native",
                    rule_origin="Python standard library",
                )
            )
            # If syntax error exists, don't run further linters
            return diagnostics

        # 2. Run Ruff if available
        ruff_cmd = self._get_ruff_cmd()
        if ruff_cmd:
            cmd_list = list(ruff_cmd)
            exec_res = CommandRunner.run_command(
                executable=cmd_list[0],
                args=cmd_list[1:] + ["check", "--no-cache", "--output-format", "json", str(file_path)],
                technology="Python",
                capability="python_lint",
                provider_type="opensource",
                provider_name="ruff",
                cwd=file_path.parent,
                timeout_seconds=10.0,
            )
            self.record_execution(exec_res)

            if exec_res.stdout.strip():
                try:
                    issues = json.loads(exec_res.stdout)
                    for issue in issues:
                        loc = issue.get("location", {})
                        end_loc = issue.get("end_location", {})
                        fix = issue.get("fix")
                        rule_code = issue.get("code")
                        severity = DiagnosticSeverity.WARNING
                        if rule_code and rule_code.startswith("E9") or rule_code == "F821":
                            severity = DiagnosticSeverity.ERROR

                        has_fix = bool(fix)
                        diagnostics.append(
                            Diagnostic(
                                path=rel_path,
                                line=loc.get("row"),
                                column=loc.get("column"),
                                end_line=end_loc.get("row"),
                                end_column=end_loc.get("column"),
                                severity=severity,
                                rule=rule_code,
                                message=issue.get("message", "Lint warning"),
                                source="ruff",
                                category=DiagnosticCategory.LINT,
                                fix_available=has_fix,
                                fix_kind=FixKind.NATIVE_ENGINE if has_fix else FixKind.MANUAL,
                                fix_source="ruff" if has_fix else None,
                                fix_safety=FixSafety.SAFE if has_fix else FixSafety.REVIEW_REQUIRED,
                                fix_description=f"Ruff native fix for {rule_code}" if has_fix else None,
                                provider="ruff",
                                provider_priority=2,
                                provider_type="opensource",
                                rule_origin="External engine",
                                documentation_url=f"https://docs.astral.sh/ruff/rules/{rule_code}" if rule_code else "https://docs.astral.sh/ruff",
                            )
                        )
                except Exception:
                    pass

        # 3. Run Black for formatting check if available (or Ruff format as alternate)
        black_cmd = self._get_black_cmd()
        if black_cmd:
            cmd_list = list(black_cmd)
            exec_res = CommandRunner.run_command(
                executable=cmd_list[0],
                args=cmd_list[1:] + ["--check", "--diff", str(file_path)],
                technology="Python",
                capability="python_format",
                provider_type="opensource",
                provider_name="black",
                cwd=file_path.parent,
                timeout_seconds=10.0,
            )
            self.record_execution(exec_res)

            if exec_res.exit_code != 0 and exec_res.status != "UNAVAILABLE":
                diagnostics.append(
                    Diagnostic(
                        path=rel_path,
                        message="File is not formatted according to Black code style.",
                        source="black",
                        severity=DiagnosticSeverity.INFO,
                        category=DiagnosticCategory.FORMAT,
                        rule="BLACK_FMT",
                        fix_available=True,
                        fix_kind=FixKind.NATIVE_ENGINE,
                        fix_source="black",
                        fix_safety=FixSafety.SAFE,
                        fix_description="Run 'black' to format the file safely.",
                        provider="black",
                        provider_priority=2,
                        provider_type="opensource",
                        rule_origin="External engine",
                        documentation_url="https://black.readthedocs.io",
                    )
                )
        elif ruff_cmd:
            # Alternate Ruff format check
            cmd_list = list(ruff_cmd)
            exec_res = CommandRunner.run_command(
                executable=cmd_list[0],
                args=cmd_list[1:] + ["format", "--no-cache", "--check", str(file_path)],
                technology="Python",
                capability="python_format",
                provider_type="opensource",
                provider_name="ruff",
                cwd=file_path.parent,
                timeout_seconds=10.0,
            )
            self.record_execution(exec_res)

            if exec_res.exit_code != 0 and exec_res.status != "UNAVAILABLE":
                diagnostics.append(
                    Diagnostic(
                        path=rel_path,
                        message="File is not formatted according to Ruff standard.",
                        source="ruff",
                        severity=DiagnosticSeverity.INFO,
                        category=DiagnosticCategory.FORMAT,
                        rule="RUFF_FMT",
                        fix_available=True,
                        fix_kind=FixKind.NATIVE_ENGINE,
                        fix_source="ruff",
                        fix_safety=FixSafety.SAFE,
                        fix_description="Run 'ruff format' to fix code formatting.",
                        provider="ruff",
                        provider_priority=2,
                        provider_type="opensource",
                        rule_origin="External engine",
                        documentation_url="https://docs.astral.sh/ruff/formatter/",
                    )
                )

        return diagnostics

    def apply_fix(self, file_path: Path, candidate: FixCandidate) -> tuple[bool, str | None]:
        """Apply native Black or Ruff fix (lint or format) to the target file."""
        if candidate.fix_source == "black" or candidate.rule == "BLACK_FMT":
            black_cmd = self._get_black_cmd()
            if not black_cmd:
                return False, "Black executable is not available"
            cmd_list = list(black_cmd)
            try:
                proc = subprocess.run(
                    cmd_list + [str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                if proc.returncode != 0:
                    err_msg = proc.stderr.strip() or proc.stdout.strip() or "Black format failed"
                    return False, err_msg
                return True, None
            except Exception as e:
                return False, f"Exception executing Black fix: {e}"

        ruff_cmd = self._get_ruff_cmd()
        if not ruff_cmd:
            return False, "Ruff executable is not available"

        cmd_list = list(ruff_cmd)
        try:
            if candidate.fix_source == "ruff-format" or candidate.rule in ["format-needed", "RUFF_FMT"]:
                # Execute ruff format
                proc = subprocess.run(
                    cmd_list + ["format", "--no-cache", str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                if proc.returncode != 0:
                    err_msg = proc.stderr.strip() or proc.stdout.strip() or "Ruff format failed"
                    return False, err_msg
                return True, None
            else:
                # Execute ruff check --fix
                proc = subprocess.run(
                    cmd_list + ["check", "--no-cache", "--fix", str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                if proc.returncode != 0 and proc.returncode != 1:
                    err_msg = proc.stderr.strip() or proc.stdout.strip() or "Ruff check --fix failed"
                    return False, err_msg
                return True, None
        except Exception as e:
            return False, f"Exception executing Ruff fix: {e}"
