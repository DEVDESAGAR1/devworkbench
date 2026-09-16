"""Python adapter utilizing Ruff (and Python AST fallback) for linting and formatting diagnostics."""

import ast
import functools
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from devworkbench.adapters.base import BaseAdapter
from devworkbench.models import (
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
    """Adapter for Python files using Ruff and AST parsing."""

    @property
    def technology(self) -> Technology:
        return Technology.PYTHON

    @property
    def name(self) -> str:
        return "Ruff / Python AST"

    @functools.lru_cache(maxsize=1)
    def _get_ruff_cmd(self) -> Optional[Tuple[str, ...]]:
        """Find the executable command to run Ruff."""
        if shutil.which("ruff"):
            return ("ruff",)
        # Try python -m ruff
        try:
            res = subprocess.run(
                [sys.executable, "-m", "ruff", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0:
                return (sys.executable, "-m", "ruff")
        except Exception:
            pass
        return None

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        cmd = self._get_ruff_cmd()
        if cmd:
            return True, None
        return False, ToolWarning(
            technology=Technology.PYTHON,
            tool_name="Ruff",
            install_hint="Install Ruff via 'pip install ruff' to enable advanced Python linting.",
            documentation_url="https://docs.astral.sh/ruff/",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        rel_path = detection.relative_path

        # 1. AST Syntax Check (Always reliable, fast, zero subprocess overhead)
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
        except SyntaxError as e:
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
            # Run ruff check (linting)
            try:
                lint_proc = subprocess.run(
                    cmd_list + ["check", "--output-format", "json", str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if lint_proc.stdout.strip():
                    try:
                        issues = json.loads(lint_proc.stdout)
                        for issue in issues:
                            loc = issue.get("location", {})
                            end_loc = issue.get("end_location", {})
                            fix = issue.get("fix")
                            rule_code = issue.get("code")
                            # Decide severity based on rule prefix
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
            except Exception:
                pass

            # Run ruff format --check (format check only - NEVER modifies file!)
            try:
                fmt_proc = subprocess.run(
                    cmd_list + ["format", "--check", str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if fmt_proc.returncode != 0:
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
            except Exception:
                pass

        return diagnostics

    def apply_fix(self, file_path: Path, candidate: FixCandidate) -> Tuple[bool, Optional[str]]:
        """Apply native Ruff fix (lint or format) to the target file."""
        ruff_cmd = self._get_ruff_cmd()
        if not ruff_cmd:
            return False, "Ruff executable is not available"

        cmd_list = list(ruff_cmd)
        try:
            if candidate.fix_source == "ruff-format" or candidate.rule == "format-needed":
                # Execute ruff format
                proc = subprocess.run(
                    cmd_list + ["format", str(file_path)],
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
                    cmd_list + ["check", "--fix", str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                if proc.returncode != 0 and proc.returncode != 1:  # ruff check exit 1 can mean remaining unfixable issues
                    err_msg = proc.stderr.strip() or proc.stdout.strip() or "Ruff check --fix failed"
                    return False, err_msg
                return True, None
        except Exception as e:
            return False, f"Exception executing Ruff fix: {e}"
