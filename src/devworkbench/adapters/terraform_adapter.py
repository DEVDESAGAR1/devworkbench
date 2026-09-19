"""Terraform / HCL adapter utilizing Terraform or OpenTofu CLI."""

import functools
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from devworkbench.adapters.base import BaseAdapter
from devworkbench.execution import CommandRunner
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


class TerraformAdapter(BaseAdapter):
    """Adapter for Terraform / OpenTofu HCL configuration files."""

    @property
    def technology(self) -> Technology:
        return Technology.TERRAFORM

    @property
    def name(self) -> str:
        return "Terraform / OpenTofu"

    @functools.lru_cache(maxsize=1)
    def _get_tf_bin(self) -> Optional[str]:
        """Check for terraform or tofu binary."""
        return shutil.which("terraform") or shutil.which("tofu")

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        bin_path = self._get_tf_bin()
        if bin_path:
            return True, None
        return False, ToolWarning(
            technology=Technology.TERRAFORM,
            tool_name="Terraform / OpenTofu",
            install_hint="Install Terraform (https://developer.hashicorp.com/terraform/install) or OpenTofu (https://opentofu.org) to enable HCL analysis.",
            documentation_url="https://developer.hashicorp.com/terraform",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        tf_bin = self._get_tf_bin()
        if not tf_bin:
            return diagnostics

        rel_path = detection.relative_path

        # 1. Format Check (Strictly check-only, never modifies files)
        bin_name = Path(tf_bin).name
        exec_res = CommandRunner.run_command(
            executable=tf_bin,
            args=["fmt", "-check", "-no-color", str(file_path)],
            technology="Terraform",
            capability="terraform_format",
            provider_type="native",
            provider_name=bin_name,
            cwd=file_path.parent,
            timeout_seconds=10.0,
        )
        self.record_execution(exec_res)

        # Exit code 3 or 1 indicates formatting differences
        if exec_res.exit_code != 0 and exec_res.status != "UNAVAILABLE":
            diagnostics.append(
                Diagnostic(
                    path=rel_path,
                    severity=DiagnosticSeverity.INFO,
                    rule="terraform-fmt",
                    message="File is not properly formatted according to standard Terraform style",
                    source=bin_name,
                    category=DiagnosticCategory.FORMAT,
                    fix_available=True,
                    fix_kind=FixKind.NATIVE_ENGINE,
                    fix_source=bin_name,
                    fix_safety=FixSafety.SAFE,
                    fix_description="Terraform fmt standard formatting",
                    provider=bin_name,
                    provider_priority=1,
                    provider_type="native",
                    rule_origin=f"Native CLI: {bin_name} fmt",
                    documentation_url="https://developer.hashicorp.com/terraform/cli/commands/fmt",
                )
            )

        return diagnostics

    def apply_fix(self, file_path: Path, candidate: FixCandidate) -> Tuple[bool, Optional[str]]:
        """Apply native Terraform or OpenTofu fmt formatting."""
        tf_bin = self._get_tf_bin()
        if not tf_bin:
            return False, "Terraform / OpenTofu binary not available"

        try:
            proc = subprocess.run(
                [tf_bin, "fmt", "-no-color", str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or proc.stdout.strip() or "Terraform fmt failed"
                return False, err_msg
            return True, None
        except Exception as e:
            return False, f"Exception executing Terraform fmt: {e}"
