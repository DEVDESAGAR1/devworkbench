"""TFLint adapter for advanced Terraform / HCL linting."""

import json
import shutil
import subprocess
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


class TFLintAdapter(BaseAdapter):
    """Adapter for Terraform / HCL configurations utilizing TFLint."""

    @property
    def technology(self) -> Technology:
        return Technology.TERRAFORM

    @property
    def name(self) -> str:
        return "TFLint"

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        if self.find_tool("tflint"):
            return True, None
        return False, ToolWarning(
            technology=Technology.TERRAFORM,
            tool_name="TFLint",
            install_hint="Install TFLint (https://github.com/terraform-linters/tflint) for advanced Terraform rule checking.",
            documentation_url="https://github.com/terraform-linters/tflint",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if not self.find_tool("tflint"):
            return diagnostics

        rel_path = detection.relative_path

        try:
            proc = subprocess.run(
                ["tflint", "--format", "json", str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if proc.stdout.strip():
                try:
                    data = json.loads(proc.stdout)
                    # TFLint format: {"issues": [{"rule": {"name": "..."}, "message": "...", "range": {"start": {"line": 1, "column": 1}}}]}
                    for issue in data.get("issues", []):
                        rule_name = issue.get("rule", {}).get("name")
                        msg = issue.get("message", "TFLint warning")
                        start_pos = issue.get("range", {}).get("start", {})
                        diagnostics.append(
                            Diagnostic(
                                path=rel_path,
                                line=start_pos.get("line"),
                                column=start_pos.get("column"),
                                severity=DiagnosticSeverity.WARNING,
                                rule=rule_name,
                                message=msg,
                                source="tflint",
                                category=DiagnosticCategory.LINT,
                                provider="tflint",
                                provider_priority=2,
                                provider_type="opensource",
                                rule_origin="OpenSource: tflint",
                                documentation_url=f"https://github.com/terraform-linters/tflint/blob/master/docs/rules/{rule_name}.md" if rule_name else "https://github.com/terraform-linters/tflint",
                            )
                        )
                except Exception:
                    pass
        except Exception:
            pass

        return diagnostics
