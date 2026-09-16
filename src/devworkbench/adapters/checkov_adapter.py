"""Checkov adapter for Infrastructure as Code (IaC) security and compliance checks."""

import functools
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from devworkbench.adapters.base import BaseAdapter
from devworkbench.models import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticSeverity,
    FileDetection,
    Technology,
    ToolWarning,
)


class CheckovAdapter(BaseAdapter):
    """Adapter for Terraform, Kubernetes, Dockerfile, and GitHub Actions utilizing Checkov."""

    SUPPORTED_TECHS = {
        Technology.TERRAFORM,
        Technology.KUBERNETES,
        Technology.DOCKERFILE,
        Technology.GITHUB_ACTIONS,
    }

    @property
    def technology(self) -> Technology:
        return Technology.TERRAFORM

    @property
    def name(self) -> str:
        return "Checkov"

    def can_handle(self, detection: FileDetection) -> bool:
        return detection.technology in self.SUPPORTED_TECHS

    @functools.lru_cache(maxsize=1)
    def _get_checkov_cmd(self) -> Optional[Tuple[str, ...]]:
        if self.find_tool("checkov"):
            return ("checkov",)
        try:
            res = subprocess.run(
                [sys.executable, "-m", "checkov", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0:
                return (sys.executable, "-m", "checkov")
        except Exception:
            pass
        return None

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        cmd = self._get_checkov_cmd()
        if cmd:
            return True, None
        return False, ToolWarning(
            technology=Technology.TERRAFORM,
            tool_name="Checkov",
            install_hint="Install Checkov via 'pip install checkov' for advanced IaC security and compliance scanning.",
            documentation_url="https://www.checkov.io/",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        cmd = self._get_checkov_cmd()
        if not cmd:
            return diagnostics

        rel_path = detection.relative_path

        try:
            proc = subprocess.run(
                list(cmd) + ["-f", str(file_path), "-o", "json", "--compact", "--quiet"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            if proc.stdout.strip():
                try:
                    data = json.loads(proc.stdout)
                    # Checkov returns dict or list of dicts with {"results": {"failed_checks": [...]}}
                    reports = data if isinstance(data, list) else [data]
                    for report in reports:
                        results = report.get("results", {})
                        for failure in results.get("failed_checks", []):
                            check_id = failure.get("check_id")
                            check_name = failure.get("check_name", "Security check failure")
                            file_lines = failure.get("file_line_range", [1, 1])
                            diagnostics.append(
                                Diagnostic(
                                    path=rel_path,
                                    line=file_lines[0] if file_lines else None,
                                    end_line=file_lines[1] if len(file_lines) > 1 else None,
                                    severity=DiagnosticSeverity.WARNING,
                                    rule=check_id,
                                    message=check_name,
                                    source="checkov",
                                    category=DiagnosticCategory.SECURITY,
                                    help_url=failure.get("guideline"),
                                    provider="checkov",
                                    provider_priority=2,
                                    provider_type="opensource",
                                    rule_origin="OpenSource: checkov",
                                    documentation_url=failure.get("guideline") or "https://www.checkov.io/",
                                )
                            )
                except Exception:
                    pass
        except Exception:
            pass

        return diagnostics
