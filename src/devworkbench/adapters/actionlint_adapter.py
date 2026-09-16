"""GitHub Actions workflow adapter utilizing actionlint."""

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


class ActionlintAdapter(BaseAdapter):
    """Adapter for GitHub Actions workflows utilizing actionlint."""

    @property
    def technology(self) -> Technology:
        return Technology.GITHUB_ACTIONS

    @property
    def name(self) -> str:
        return "actionlint"

    def is_available(self) -> Tuple[bool, Optional[ToolWarning]]:
        if self.find_tool("actionlint"):
            return True, None
        return False, ToolWarning(
            technology=Technology.GITHUB_ACTIONS,
            tool_name="actionlint",
            install_hint="Install actionlint (https://github.com/rhysd/actionlint) to enable GitHub Actions workflow linting.",
            documentation_url="https://github.com/rhysd/actionlint",
        )

    def analyze_file(self, file_path: Path, detection: FileDetection) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if not self.find_tool("actionlint"):
            return diagnostics

        rel_path = detection.relative_path

        try:
            proc = subprocess.run(
                ["actionlint", "-format", "{{json .}}", str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if proc.stdout.strip():
                try:
                    items = json.loads(proc.stdout)
                    for item in items:
                        diagnostics.append(
                            Diagnostic(
                                path=rel_path,
                                line=item.get("line"),
                                column=item.get("column"),
                                end_line=item.get("end_line"),
                                end_column=item.get("end_column"),
                                severity=DiagnosticSeverity.ERROR if item.get("kind") == "syntax" else DiagnosticSeverity.WARNING,
                                rule=item.get("kind"),
                                message=item.get("message", "Workflow issue"),
                                source="actionlint",
                                category=DiagnosticCategory.LINT,
                                provider="actionlint",
                                provider_priority=1,
                                provider_type="native",
                                rule_origin="Native CLI: actionlint",
                                documentation_url="https://github.com/rhysd/actionlint",
                            )
                        )
                except Exception:
                    pass
        except Exception:
            pass

        return diagnostics
